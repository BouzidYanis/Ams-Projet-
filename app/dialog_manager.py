"""
app/dialog_manager.py
Dialog manager that uses LLMClient to generate assistant replies and
maintains per-session message history (user/assistant).
Falls back to simple rule-based replies if LLM fails.
"""
from typing import Tuple, Dict, Any, List
from app.sessions import SessionStore
from app.llm import LLMClient, LLMError
from app.navigation import get_navigation_instructions
import os
import json
import random
import re
from datetime import datetime, timedelta
from .tools import parse_heure_to_minutes, parse_minutes_to_heure
from app.DB_access import DatabaseMongo
from app.reservation import (
    get_available_slots, 
    get_alternative_slots, 
    get_available_slots_for_activity,
    parse_time_to_minutes,
    get_user_future_reservations,
)

db = DatabaseMongo()

DEFAULT_SYSTEM_PROMPT = (
    "Tu es l'assistant conversationnel d'un robot d'accueil dans une salle multisports. "
    "Tu dois TOUJOURS répondre en français, de façon polie, chaleureuse, concise et utile. "
    "Tu peux aider pour : informations (horaires, tarifs, activités), orientation dans le bâtiment "
    "(vestiaires, terrains, salle de musculation, piscine, etc.), inscriptions et réservations. "
    "Si l'utilisateur demande une réservation, demande toujours l'activité précise et le créneau "
    "si ces informations sont manquantes. "
    "Si la question est très simple (par exemple juste 'bonjour'), réponds par un message de bienvenue "
    "en expliquant clairement ce que tu peux faire pour l'utilisateur. "
    "Ne donne jamais d'informations personnelles sur d'autres personnes. "
    "Si tu ne comprends pas la demande (intention inconnue), essaie d'être utile en proposant les services "
    "que je peux t'offrir, ou demande une clarification sur ce que tu peux faire. "
    "Sois toujours bienveillant et oriente l'utilisateur vers ce que je peux vraiment faire."
)


# Simple rule-based fallback (kept minimal)
RULES = {
    "greeting": [
        "Bonjour ! Je peux vous aider pour les horaires, les inscriptions, les réservations ou pour vous orienter. Que souhaitez‑vous ?",
        "Salut ! Comment puis-je vous aider aujourd'hui ?",
        "Bonjour ! En quoi puis-je vous être utile pour votre visite à la salle multisports ?"
    ],
    "ask_hours": "La salle est ouverte du lundi au vendredi de 8h à 22h, et le weekend de 9h à 18h.",
    "ask_activities": "Nous proposons fitness, basket, natation, tennis, futsal et yoga. Laquelle vous intéresse ?",
}

llm_openai = "llm_openai_config.json"


def convert_to_date(date_str: str) -> str:
    """
    Convertit une chaîne de texte en date au format YYYY-MM-DD.
    
    Supporte les formats suivants:
    - Jour de semaine: "lundi", "mardi", etc. → prochaine date de ce jour
    - Relatif: "demain", "aujourd'hui", "après-demain"
    - Date textuelle: "21 avril 2026", "21 avril", "17 mars", "17 marse" (avec fautes orthographe)
    - Formats numériques: "21/04/2026", "21-04-2026", "21/4/2026"
    - Format ISO: "2026-04-21" (retourné tel quel)
    
    Tous les formats sont convertis en YYYY-MM-DD pour assurer l'uniformité.
    
    Args:
        date_str: Chaîne de date/jour à convertir
        
    Returns:
        Date au format YYYY-MM-DD, ou la chaîne originale si impossible à convertir
    """
    if not date_str:
        return date_str
    
    date_str = str(date_str).strip().lower()
    today = datetime.now().date()
    
    # === Format ISO YYYY-MM-DD (déjà correct)
    try:
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            datetime.strptime(date_str, '%Y-%m-%d')
            return date_str
    except ValueError:
        pass
    
    # === Aujourd'hui
    if date_str in ["aujourd'hui", "aujourd hui", "aujd", "today"]:
        return today.isoformat()
    
    # === Demain
    if date_str == "demain":
        tomorrow = today + timedelta(days=1)
        return tomorrow.isoformat()
    
    # === Après-demain
    if re.search(r'après[- ]?demain', date_str):
        after_tomorrow = today + timedelta(days=2)
        return after_tomorrow.isoformat()
    
    # === Jour de la semaine (lundi, mardi, etc.)
    days_of_week = {
        'lundi': 0, 'lun': 0,
        'mardi': 1, 'mar': 1,
        'mercredi': 2, 'mer': 2,
        'jeudi': 3, 'jeu': 3,
        'vendredi': 4, 'ven': 4,
        'samedi': 5, 'sam': 5,
        'dimanche': 6, 'dim': 6
    }
    
    for day_name, day_num in days_of_week.items():
        if date_str == day_name or date_str.startswith(day_name):
            current_weekday = today.weekday()
            days_ahead = day_num - current_weekday
            
            if days_ahead <= 0:
                days_ahead += 7
            
            next_date = today + timedelta(days=days_ahead)
            return next_date.isoformat()
    
    # === Formats de date textuels: "21 avril 2026", "21 avril", "17 mars", etc.
    # Accepte aussi les variantes et fautes orthographe (marse, avril, etc.)
    month_map = {
        'janvier': 1, 'février': 2, 'fevrier': 2,
        'mars': 3, 'marse': 3, 'marse': 3,  # accepte la faute "marse"
        'avril': 4, 'avri': 4,
        'mai': 5,
        'juin': 6, 'juin': 6,
        'juillet': 7, 'juill': 7,
        'août': 8, 'aout': 8,
        'septembre': 9, 'sept': 9,
        'octobre': 10, 'oct': 10,
        'novembre': 11, 'nov': 11,
        'décembre': 12, 'decembre': 12, 'déc': 12, 'dec': 12
    }
    
    # Pattern: "21 avril 2026" ou "21 avril" ou toute variante
    # La regex accepte n'importe quelle séquence de lettres comme mois
    match = re.search(r'(\d{1,2})\s+([a-zàâäéèêëïîôöùûüœæçñ]+)(?:\s+(\d{4}))?', date_str)
    if match:
        day = int(match.group(1))
        month_str = match.group(2).lower()
        year = int(match.group(3)) if match.group(3) else today.year
        
        # Chercher le mois dans la map
        month = month_map.get(month_str)
        
        # Si pas trouvé exactement, essayer une correspondance partielle
        if month is None:
            for month_name, month_num in month_map.items():
                if month_str.startswith(month_name[:3]) or month_name.startswith(month_str[:3]):
                    month = month_num
                    break
        
        if month:
            try:
                parsed_date = datetime(year, month, day).date()
                return parsed_date.isoformat()
            except (ValueError, TypeError):
                pass
    
    # === Formats numériques: "21/04/2026", "21-04-2026", "21/4/2026"
    match = re.match(r'(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?', date_str)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3)) if match.group(3) else today.year
        
        # Gérer les années à 2 chiffres
        if year < 100:
            year = 2000 + year if year < 50 else 1900 + year
        
        try:
            parsed_date = datetime(year, month, day).date()
            return parsed_date.isoformat()
        except (ValueError, TypeError):
            pass
    
    # === Cas non-reconnus : retourner la chaîne originale
    return date_str


class DialogManager:
    def __init__(self, sessions: SessionStore, llm_config_path: str = None):
        self.sessions = sessions
        cfg_path = llm_config_path or os.path.join(os.path.dirname(__file__), "..", "configs", llm_openai)
        self.llm = LLMClient(cfg_path)
        # system prompt can be overridden in config file (optional)
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                self.system_prompt = cfg.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
        except Exception:
            self.system_prompt = DEFAULT_SYSTEM_PROMPT

    def _append_message(self, session_id: str, role: str, content: str) -> None:
        session = self.sessions.get(session_id)
        history = session.setdefault("history", [])
        history.append({"role": role, "content": content})
        # limit history length to avoid huge prompts (keep last N pairs)
        max_msgs = 10
        if len(history) > max_msgs:
            # keep the last max_msgs entries
            session["history"] = history[-max_msgs:]
        self.sessions.update(session_id, session)
    
    def _get_booking_slots(self, session_id: str) -> Dict[str, Any]:
        session = self.sessions.get(session_id)
        return session.get("booking_slots", {})
    
    def _set_booking_slots(self, session_id: str, slots: Dict[str, Any]) -> None:
        """Sauvegarde les slots de réservation dans la session."""
        session = self.sessions.get(session_id)
        session["booking_slots"] = slots
        self.sessions.update(session_id, session)

    def _clear_booking_slots(self, session_id: str) -> None:
        """Supprime les slots de réservation (fin du flux)."""
        session = self.sessions.get(session_id)
        session.pop("booking_slots", None)
        self.sessions.update(session_id, session)

    def _get_user_reservations(self, user_name: str) -> List[Dict[str, Any]]:
        """Récupère toutes les réservations actives de l'utilisateur"""
        try:
            reservations = list(db.get_collection("reservations").find({
                "user_name": user_name,
                "statut": {"$ne": "annulee"}
            }))
            return reservations
        except Exception as e:
            print(f"[ERROR] Erreur lors de la récupération des réservations: {e}")
            return []

    def _cancel_booking(self, reservation_id: str) -> bool:
        """Annule une réservation en mettant à jour son statut"""
        from bson import ObjectId
        try:
            result = db.get_collection("reservations").update_one(
                {"_id": ObjectId(reservation_id)},
                {"$set": {"statut": "annulee", "date_annulation": datetime.now()}}
            )
            if result.modified_count > 0:
                print(f"[CANCEL] Réservation {reservation_id} annulée avec succès")
                return True
            else:
                print(f"[CANCEL] Aucune réservation trouvée avec l'ID {reservation_id}")
                return False
        except Exception as e:
            print(f"[ERROR] Erreur lors de l'annulation: {e}")
            return False

    def _is_cancellation_in_progress(self, session_id: str) -> bool:
        """Vérifie si une annulation est en cours"""
        session = self.sessions.get(session_id)
        return "cancellation_flow" in session

    def _set_cancellation_flow(self, session_id: str, data: Dict[str, Any]) -> None:
        """Marque qu'une annulation est en cours"""
        session = self.sessions.get(session_id)
        session["cancellation_flow"] = data
        self.sessions.update(session_id, session)

    def _clear_cancellation_flow(self, session_id: str) -> None:
        """Efface le flux d'annulation"""
        session = self.sessions.get(session_id)
        session.pop("cancellation_flow", None)
        self.sessions.update(session_id, session)

    def _get_center_hours(self) -> Dict[str, Any]:
        """Récupère les horaires d'ouverture du centre depuis MongoDB"""
        try:
            # Chercher le document des horaires du centre (type: "horaires")
            horaires = db.get_collection("config").find_one({"type": "horaires"})
            
            if horaires:
                horaire_ouverture = horaires.get("horaire_ouverture", "08:00")
                horaire_fermeture = horaires.get("horaire_fermeture", "18:00")
                return {
                    "ouverture": horaire_ouverture,
                    "fermeture": horaire_fermeture,
                    "ouverture_heure": horaire_ouverture[:2] + "h" + horaire_ouverture[3:],  # "08:00" → "08h00"
                    "fermeture_heure": horaire_fermeture[:2] + "h" + horaire_fermeture[3:],  # "18:00" → "18h00"
                }
        except Exception as e:
            print(f"[ERROR] Erreur lors de la récupération des horaires: {e}")
            # Horaires par défaut en cas d'erreur
            return {
                "ouverture": "08:00",
                "fermeture": "18:00",
                "ouverture_heure": "08h00",
                "fermeture_heure": "18h00",
            }

    def _get_activity_pricing(self, activite_name: str = None) -> Dict[str, Any]:
        """Récupère les tarifs des activités depuis MongoDB"""
        try:
            if activite_name:
                # Chercher une activité spécifique
                activite = db.get_collection("activite").find_one(
                    {"nom": {"$regex": f"^{activite_name}$", "$options": "i"}},
                    {"nom": 1, "tarif": 1, "description": 1}
                )
                if activite:
                    return {
                        "activite": activite.get("nom", ""),
                        "tarif": activite.get("tarif", "Non spécifié"),
                        "description": activite.get("description", "")
                    }
                else:
                    return None
            else:
                # Récupérer tous les tarifs
                activites = list(db.get_collection("activite").find(
                    {},
                    {"nom": 1, "tarif": 1}
                ))
                
                if activites:
                    return {
                        "all_activities": [
                            {"nom": a.get("nom"), "tarif": a.get("tarif", "Non spécifié")}
                            for a in activites
                        ]
                    }
                else:
                    return None
        except Exception as e:
            print(f"[ERROR] Erreur lors de la récupération des tarifs: {e}")
            return None

    def _is_room_booked(self, salle: str, jour: str, heure_debut: str,heure_fin:str) -> bool:
        """Vérifie dans la base de données si la salle est déjà réservée pour le créneau donné."""
        acitivites_planinng = db.get_collection("activite").find_one(
            {
                "planning": {"$elemMatch": {"salle": salle, "jour": jour,
                                             "$or": [
                                                        {"heure_debut": {"$lt": heure_fin, "$gte": heure_debut}},
                                                        {"heure_fin": {"$gt": heure_debut, "$lte": heure_fin}},
                                                        {"$and": [{"heure_debut": {"$lte": heure_debut}}, {"heure_fin": {"$gte": heure_fin}}]},
                                                     ]
            }}})
        if acitivites_planinng:
            return True
        db_query = {
            "salle": salle,
            "jour": jour,
            "$or": [
                {"heure_debut": {"$lt": heure_fin, "$gte": heure_debut}},
                {"heure_fin": {"$gt": heure_debut, "$lte": heure_fin}},
                {"heure_debut":heure_debut, "heure_fin":heure_fin},
                {"$and": [{"heure_debut": {"$lte": heure_debut}}, {"heure_fin": {"$gte": heure_fin}}]},
            ]
        }
        existing = db.get_collection("reservations").find_one(db_query)
        return existing is not None

    def _is_booking_in_progress(self, session_id: str) -> bool:
        session = self.sessions.get(session_id)
        return "booking_slots" in session

    def _extract_booking_entities(self, entities: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
        """
        Extrait les valeurs de slots depuis les entities NLU et le texte brut.
        Retourne un dict avec les clés : salle, activite, jour, heure (celles trouvées).
        """
        found = {}

        # --- Salle ---
        locations = entities.get("location", [])
        if locations:
            # Filtrer les locations génériques (pas des vrais noms de salles)
            generic_terms = ['salle', 'room', 'terrain', 'piscine', 'vestiaire', 'salle de sport', "salle d'accueil", 'accueil']
            
            for loc in locations:
                loc_lower = loc.lower().strip()
                # Ignorer si c'est juste un terme générique
                if loc_lower not in generic_terms and len(loc_lower) > 1:
                    # Vérifier que ce n'est pas juste un numéro sans identifiant
                    if not loc.isdigit():
                        found["salle"] = loc
                        break
            
            # Si aucune location valide trouvée, chercher les vrais noms de salle dans le texte
            if "salle" not in found:
                salle_patterns = [
                    r'\b(salle\s+[a-zA-Z0-9])\b',  # "Salle A", "Salle 1"
                    r'\b([a-zA-Z]\s*(?:pour|de)?\s*(?:yoga|fitness|natation|tennis|basketball|futsal))\b',
                ]
                for pattern in salle_patterns:
                    m = re.search(pattern, raw_text, re.IGNORECASE)
                    if m:
                        found["salle"] = m.group(1)
                        break

        # --- Activité (sport) ---
        activities = entities.get("activity", [])
        if activities:
            found["activite"] = activities[0]

        # --- Jour / Date ---
        times = entities.get("time", [])
        # On essaie aussi de détecter une date dans le texte brut
        date_patterns = [
            r'\b(\d{1,2})\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\b',
            r'\b(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?\b',
            r'\b(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\b',
            r'\b(demain|après[- ]demain|aujourd\'?hui)\b',
        ]
        for pattern in date_patterns:
            m = re.search(pattern, raw_text, re.IGNORECASE)
            if m:
                found["jour"] = m.group(0)
                break
        # si spaCy a trouvé un temps et qu'on n'a pas encore de jour
        if "jour" not in found and times:
            for t in times:
                # vérifier si ça ressemble à une date plutôt qu'une heure
                if re.search(r'(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre|lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|demain)', t, re.IGNORECASE):
                    found["jour"] = t
                    break

        # --- Heure ---
        hour_patterns = [
            r'\b(\d{1,2})\s*:\s*(\d{2})\b',                # 10:00, 18:30
            r'\b(\d{1,2})\s*[hH]\s*(\d{1,2})\b',            # 19h30, 19H00
            r'\b(\d{1,2})\s*[hH]\b',                         # 19h (sans minutes)
            r'\bà\s+(\d{1,2})\b',                            # à 19
        ]
        for pattern in hour_patterns:
            m = re.search(pattern, raw_text, re.IGNORECASE)
            if m:
                h = int(m.group(1))
                mins = 0
                if m.lastindex >= 2 and m.group(2) and m.group(2).strip():
                    mins = int(m.group(2))
                found["heure"] = "{:02d}:{:02d}".format(h, mins)
                break
        # si spaCy a trouvé un temps et qu'on n'a pas encore d'heure
        if "heure" not in found and times:
            for t in times:
                if re.search(r'\d{1,2}\s*[hH:]', t):
                    # Normaliser aussi
                    m2 = re.search(r'(\d{1,2})\s*[hH:]\s*(\d{1,2})?', t)
                    if m2:
                        h = int(m2.group(1))
                        mins = int(m2.group(2)) if m2.group(2) else 0
                        found["heure"] = "{:02d}:{:02d}".format(h, mins)
                    else:
                        found["heure"] = t
                    break

        # === Convertir le jour en date YYYY-MM-DD ===
        if "jour" in found and found["jour"]:
            found["jour"] = convert_to_date(found["jour"])
            print(f"[BOOKING] Jour converti en date: {found['jour']}")

        return found

    def _ask_next_missing_slot(self, slots: Dict[str, Any]) -> Tuple[str, str]:
        """
        Détermine le prochain slot manquant et retourne (slot_name, question).
        Si tous les slots nécessaires sont remplis, retourne (None, None).

        On a besoin de : salle OU activite, jour, heure.
        Si on a une activité mais pas de salle, on cherchera les salles disponibles.
        """
        has_salle = bool(slots.get("salle"))
        has_activite = bool(slots.get("activite"))
        has_jour = bool(slots.get("jour"))
        has_heure = bool(slots.get("heure"))

        # Il faut au moins une salle ou une activité
        if not has_salle and not has_activite:
            return "salle_or_activite", "Quelle salle ou quelle activite souhaitez-vous reserver ?"
        
        if not has_jour:
            return "jour", "Pour quel jour souhaitez-vous reserver ?"

        if not has_heure:
            return "heure", "A quelle heure souhaitez-vous reserver ?"

        return None, None

    def _find_salles_for_activity(self, activite: str, jour: str, heure: str) -> List[Dict[str, Any]]:
        """
        Cherche les salles disponibles pour une activité, un jour et une heure donnés.
        Retourne une liste de salles disponibles depuis MongoDB.
        """
        # Chercher les salles associées à cette activité
        activite_cap = activite.capitalize()
        salles = list(db.get_collection("salle").find(
            {"activites_supportees": {"$regex": activite_cap, "$options": "i"}},
            {"_id": 0}
        ))

        if not salles:
            # Fallback : chercher toutes les salles
            salles = list(db.get_collection("salle").find({}, {"_id": 0}))

        # TODO: filtrer par disponibilité réelle (vérifier les réservations existantes)
        # Pour l'instant, on retourne toutes les salles qui correspondent à l'activité
        return salles

    def _handle_booking_flow(self, session_id: str, intent: str, entities: Dict[str, Any], raw_text: str, user_name: str = None) -> Tuple[str, Dict[str, Any]]:
        """
        Gère tout le flux de slot filling pour la réservation.
        Retourne (text, actions).
        
        Args:
            session_id: ID de la session
            intent: L'intention détectée
            entities: Les entités NLU extraites
            raw_text: Le texte brut de l'utilisateur
            user_name: Le nom de l'utilisateur reconnu par reconnaissance faciale
        """
        # Vérifier que l'utilisateur est reconnu (adhérent)
        if not user_name:
            text = "Désolé, je ne vous ai pas reconnu. Vous devez d'abord vous inscrire comme adhérent avant de pouvoir réserver. Veuillez vous inscrire et revenir ensuite."
            self._append_message(session_id, "assistant", text)
            return text, {"type": "booking_error", "reason": "user_not_recognized"}
        
        slots = self._get_booking_slots(session_id)
        
        # Sauvegarder le nom d'utilisateur dans les slots dès le départ
        if "user_name" not in slots:
            slots["user_name"] = user_name
            self._set_booking_slots(session_id, slots)
            print(f"[BOOKING] Utilisateur reconnu: {user_name}")

        # Extraire les nouveaux slots depuis le message courant
        new_slots = self._extract_booking_entities(entities, raw_text)
        print("[BookingFlow] Nouveaux slots extraits:", new_slots)

        # Fusionner : les nouveaux slots écrasent les anciens
        slots.update(new_slots)
        self._set_booking_slots(session_id, slots)

        print("[BookingFlow] Slots actuels:", slots)

        # Vérifier s'il manque des slots
        missing_slot, question = self._ask_next_missing_slot(slots)

        if missing_slot:
            # Il manque encore des informations
            self._append_message(session_id, "assistant", question)
            actions = {
                "type": "booking_slot_filling",
                "missing_slot": missing_slot,
                "current_slots": slots,
            }
            return question, actions

        # Tous les slots sont remplis !
        # Cas spécial : on a une activité mais pas de salle → chercher les salles disponibles
        if slots.get("activite") and not slots.get("salle"):
            salles_dispo = self._find_salles_for_activity(
                slots["activite"], slots["jour"], slots["heure"]
            )

            if not salles_dispo:
                # Chercher les alternatives en terme de créneaux disponibles
                available_slots_dict = get_available_slots_for_activity(slots["activite"], slots["jour"])
                
                if available_slots_dict:
                    # Il y a des salles disponibles mais à d'autres horaires
                    text_parts = ["Désolé, aucune salle n'est disponible pour {} le {} à {}.".format(
                        slots["activite"], slots["jour"], slots["heure"]
                    )]
                    text_parts.append("Voici les créneaux disponibles pour cette activité ce jour :")
                    for salle_nom, slots_list in list(available_slots_dict.items())[:3]:  # Montrer max 3 salles
                        times = ", ".join([f"{s['heure_debut']}-{s['heure_fin']}" for s in slots_list[:3]])
                        text_parts.append(f"  • {salle_nom}: {times}")
                    text_parts.append("Voulez-vous choisir un de ces créneaux, ou essayer un autre jour ?")
                    text = " ".join(text_parts)
                    
                    actions = {
                        "type": "booking_alternatives",
                        "available_slots": available_slots_dict,
                        "current_slots": slots,
                        "reason": "no_room_available_at_requested_time"
                    }
                    self._append_message(session_id, "assistant", text)
                    return text, actions
                else:
                    # Aucune disponibilité du tout
                    text = "Désolé, aucune salle n'est disponible pour {} le {}. Voulez-vous essayer à un autre moment ou une autre date ?".format(
                        slots["activite"], slots["jour"]
                    )
                    self._clear_booking_slots(session_id)
                    self._append_message(session_id, "assistant", text)
                    return text, {"type": "booking_no_availability"}

            if len(salles_dispo) == 1:
                salle_choisie = salles_dispo[0]
                slots["salle"] = salle_choisie.get("nom", salle_choisie.get("salle_id", "inconnue"))
                self._set_booking_slots(session_id, slots)
                # Confirmer directement
                return self._confirm_booking(session_id, slots)

            # Plusieurs salles disponibles → demander à l'utilisateur de choisir
            noms_salles = [s.get("nom", s.get("salle_id", "?")) for s in salles_dispo]
            text = "Il y a {} salles disponibles pour {} le {} à {} : {}. Laquelle préférez-vous ?".format(
                len(salles_dispo),
                slots["activite"],
                slots["jour"],
                slots["heure"],
                ", ".join(noms_salles),
            )
            # On garde le flow ouvert, il manque juste le choix de la salle
            # Marquer qu'on attend un choix de salle
            slots["_awaiting_salle_choice"] = True
            slots["_salles_proposees"] = noms_salles
            self._set_booking_slots(session_id, slots)
            self._append_message(session_id, "assistant", text)
            actions = {
                "type": "booking_choose_salle",
                "salles_disponibles": [json.loads(json.dumps(s, default=str)) for s in salles_dispo],
                "current_slots": slots,
            }
            return text, actions

        # On a la salle (et éventuellement l'activité), le jour et l'heure → confirmer
        return self._confirm_booking(session_id, slots)

    def _resolve_salle(self, salle_key: str):
        """
        Résout une clé de salle normalisée (ex: 'salle_a', 'salle_b') 
        vers le document MongoDB (ex: {"nom": "Salle A", "_id": ObjectId(...)}).
        """
        # "salle_a" → "salle a" → chercher "Salle A" en case-insensitive
        search_name = salle_key.replace("_", " ")
        salle_doc = db.get_collection("salle").find_one({
            "$or": [
                {"nom": {"$regex": "^" + search_name + "$", "$options": "i"}},
                {"nom": {"$regex": "^" + salle_key + "$", "$options": "i"}},
            ]
        })
        return salle_doc

    def _confirm_booking(self, session_id: str, slots: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Confirme la réservation et nettoie les slots."""
        salle_key = slots.get("salle", "?")
        activite = slots.get("activite", "")
        jour = slots.get("jour", "?")
        heure = slots.get("heure", "?")
        user_name = slots.get("user_name", "Utilisateur inconnu")
        
        heure_fin = parse_heure_to_minutes(heure) + 60
        heure_fin = parse_minutes_to_heure(heure_fin)

        # Résoudre la salle vers son document MongoDB
        salle_doc = self._resolve_salle(salle_key)

        if not salle_doc:
            text = "Désolé, je ne trouve pas la salle '{}' dans notre système. Pouvez-vous vérifier le nom ?".format(salle_key)
            self._clear_booking_slots(session_id)
            self._append_message(session_id, "assistant", text)
            return text, {"type": "booking_error", "reason": "salle_not_found"}

        salle_id = salle_doc["_id"]
        salle_nom = salle_doc["nom"]  # "Salle A", "Salle B", etc.

        activite_str = " pour l'activité {}".format(activite) if activite else ""

        if self._is_room_booked(salle_id, jour, heure, heure_fin):
            # La salle n'est pas disponible → proposer des alternatives intelligentes
            return self._handle_booking_unavailable(session_id, salle_id, salle_nom, jour, heure, activite)

        text = "Parfait {} ! Je confirme votre réservation de la salle {}{} le {} de {} à {}. Souhaitez-vous autre chose ?".format(
            user_name, salle_nom, activite_str, jour, heure, heure_fin
        )

        actions = {
            "type": "booking_confirmed",
            "booking": {
                "user_name": user_name,
                "salle_id": str(salle_id),
                "salle_nom": salle_nom,
                "activite": activite,
                "jour": jour,
                "heure_debut": heure,
                "heure_fin": heure_fin
            }
        }

        # Enregistrer avec l'ObjectId de la salle
        try:
            user_name = slots.get("user_name", "Inconnu")
            reservation_data = {
                "user_name": user_name,
                "salle": salle_id,
                "activite": activite,
                "jour": jour,
                "heure_debut": heure,
                "heure_fin": heure_fin,
                "statut": "confirmee",
                "date_reservation": datetime.now(),  # Ajouter la date/heure de création
            }
            db.get_collection("reservations").insert_one(reservation_data)
            print("[BookingFlow] Réservation enregistrée pour l'utilisateur '{}': {}".format(user_name, reservation_data))
        except Exception as e:
            print("[BookingFlow] Erreur lors de l'enregistrement:", e)

        self._clear_booking_slots(session_id)
        self._append_message(session_id, "assistant", text)
        return text, actions

    def _handle_booking_unavailable(self, session_id: str, salle_id: str, salle_nom: str, jour: str, heure: str, activite: str = "") -> Tuple[str, Dict[str, Any]]:
        """
        Gère le cas où une salle n'est pas disponible à l'horaire demandé.
        Propose des alternatives intelligentes :
        1. Créneaux alternatifs dans la même salle
        2. Autres salles disponibles au même créneau
        """
        heure_fin = parse_heure_to_minutes(heure) + 60
        heure_fin = parse_minutes_to_heure(heure_fin)
        
        # Récupérer les alternatives pour la même salle
        alternatives_meme_salle = get_alternative_slots(salle_id, jour, heure, duree=60, max_alternatives=2)
        
        # Récupérer les autres salles disponibles
        activite_cap = activite.capitalize() if activite else ""
        db_client = DatabaseMongo()
        salle_col = db_client.get_collection("salle")
        other_salles = []
        
        if activite_cap:
            other_salles = list(salle_col.find(
                {
                    "$and": [
                        {"activites_supportees": {"$regex": activite_cap, "$options": "i"}},
                        {"_id": {"$ne": salle_id}}
                    ]
                },
                {"_id": 1, "nom": 1}
            ))
        else:
            other_salles = list(salle_col.find(
                {"_id": {"$ne": salle_id}},
                {"_id": 1, "nom": 1}
            ))
        
        # Vérifier la disponibilité des autres salles
        salles_disponibles = []
        for salle in other_salles[:3]:  # Limiter à 3 alternatives
            if not self._is_room_booked(salle["_id"], jour, heure, heure_fin):
                salles_disponibles.append(salle["nom"])
        
        db_client.close()
        
        # Construire le message avec les alternatives
        parts = ["Désolé, la salle {} est déjà réservée le {} de {} à {}.".format(
            salle_nom, jour, heure, heure_fin
        )]
        
        actions = {
            "type": "booking_no_availability",
            "original_room": salle_nom,
            "original_time": heure,
            "date": jour,
            "alternatives": {}
        }
        
        # Proposer les créneaux alternatifs pour la même salle
        if alternatives_meme_salle:
            parts.append("Créneaux disponibles dans la même salle {} :".format(salle_nom))
            for alt in alternatives_meme_salle:
                parts.append("  • {} à {}".format(alt["heure_debut"], alt["heure_fin"]))
            actions["alternatives"]["same_room"] = alternatives_meme_salle
        
        # Proposer les autres salles disponibles
        if salles_disponibles:
            parts.append("Autres salles disponibles à cet horaire : {}.".format(", ".join(salles_disponibles)))
            actions["alternatives"]["other_rooms"] = salles_disponibles
        
        # Message final de question
        options = []
        if alternatives_meme_salle:
            options.append("un autre créneau dans la même salle")
        if salles_disponibles:
            options.append("une autre salle")
        
        if options:
            parts.append("Voulez-vous {} ?".format(" ou ".join(options)))
        else:
            parts.append("Malheureusement, il n'y a pas d'alternatives disponibles pour ce jour.")
        
        text = " ".join(parts)
        
        # Sauvegarder les alternatives dans la session pour la suite du dialogue
        slots = self._get_booking_slots(session_id)
        slots["_alternatives"] = {
            "same_room": alternatives_meme_salle,
            "other_rooms": salles_disponibles
        }
        self._set_booking_slots(session_id, slots)
        
        self._append_message(session_id, "assistant", text)
        return text, actions

    def handle(self, session_id: str, parse_result: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """
        parse_result should contain at least {"intent": str, "entities": {...}} and original text under 'raw_text'
        """

        # --- BLOC DE DEBUG ---
        print("\n" + "="*40)
        print("[DEBUG DM] Entrée dans handle()")
        print("[DEBUG DM] Session ID: {}".format(session_id))
        print("[DEBUG DM] parse_result complet: {}".format(json.dumps(parse_result, indent=2)))
        # ---------------------

        intent = parse_result.get("intent", "unknown")
        entities = parse_result.get("entities", {})
        user_text = parse_result.get("raw_text") or parse_result.get("text") or ""
        user_name = parse_result.get("user_name", None)  # Nom issu de la reconnaissance faciale
        user_role = parse_result.get("user_role", None)  # Rôle issu de la reconnaissance faciale

        # store user message in history
        if user_text:
            self._append_message(session_id, "user", user_text)

        session = self.sessions.get(session_id)
        history: List[Dict[str, str]] = session.get("history", [])

        actions = {}

        # ─── SLOT FILLING : si une réservation est en cours, on continue le flux ───
        if self._is_booking_in_progress(session_id):
            slots = self._get_booking_slots(session_id)
            print("[DEBUG DM] Réservation en cours, slots actuels:", slots)
            
            # Vérifier que l'utilisateur est toujours reconnu
            stored_user_name = slots.get("user_name")
            if not stored_user_name:
                text = "Erreur: l'utilisateur n'est pas défini pour cette réservation. Veuillez recommencer."
                self._append_message(session_id, "assistant", text)
                self._clear_booking_slots(session_id)
                return text, {"type": "booking_error", "reason": "user_not_found"}

            # Si on attend un choix de salle
            if slots.get("_awaiting_salle_choice"):
                salles_proposees = slots.get("_salles_proposees", [])
                # Essayer de trouver la salle choisie dans le texte
                chosen = None
                text_lower = user_text.lower()
                for salle_nom in salles_proposees:
                    if salle_nom.lower() in text_lower:
                        chosen = salle_nom
                        break
                # Essayer aussi avec les locations extraites
                if not chosen:
                    locs = entities.get("location", [])
                    for loc in locs:
                        for salle_nom in salles_proposees:
                            if loc in salle_nom.lower() or salle_nom.lower() in loc:
                                chosen = salle_nom
                                break
                        if chosen:
                            break

                if chosen:
                    slots["salle"] = chosen
                    slots.pop("_awaiting_salle_choice", None)
                    slots.pop("_salles_proposees", None)
                    self._set_booking_slots(session_id, slots)
                    return self._confirm_booking(session_id, slots)
                else:
                    text = "Je n'ai pas compris votre choix. Les salles disponibles sont : {}. Laquelle choisissez-vous ?".format(
                        ", ".join(salles_proposees)
                    )
                    self._append_message(session_id, "assistant", text)
                    return text, {"type": "booking_choose_salle", "current_slots": slots}

            # Sinon, continuer le slot filling normal (l'utilisateur donne le jour, l'heure, etc.)
            return self._handle_booking_flow(session_id, intent, entities, user_text, user_name)

        # ─── NOUVELLE RÉSERVATION ───
        if intent == "book_activity":
            # Initialiser les slots et démarrer le flux
            self._set_booking_slots(session_id, {})
            return self._handle_booking_flow(session_id, intent, entities, user_text, user_name)
        
        # ─── ANNULATION DE RÉSERVATION ───
        if intent == "cancel_booking":
            # Vérifier que l'utilisateur est reconnu
            if not user_name:
                text = "Désolé, je ne vous ai pas reconnu. Je ne peux pas annuler votre réservation sans confirmation d'identité."
                self._append_message(session_id, "assistant", text)
                return text, {"type": "cancel_error", "reason": "user_not_recognized"}
            
            # Récupérer les réservations actives de l'utilisateur
            reservations = self._get_user_reservations(user_name)
            
            if not reservations:
                text = "Vous n'avez pas de réservations actives à annuler."
                self._append_message(session_id, "assistant", text)
                return text, {"type": "no_reservation_to_cancel"}
            
            if len(reservations) == 1:
                # Une seule réservation : demander confirmation
                reservation = reservations[0]
                salle_id = reservation.get("salle")
                salle_doc = db.get_collection("salle").find_one({"_id": salle_id}) if salle_id else {}
                salle_nom = salle_doc.get("nom", "inconnue") if salle_doc else "inconnue"
                
                jour = reservation.get("jour", "?")
                heure_debut = reservation.get("heure_debut", "?")
                heure_fin = reservation.get("heure_fin", "?")
                activite = reservation.get("activite", "")
                
                activite_str = " ({})".format(activite) if activite else ""
                
                text = "Je vais annuler votre réservation de la salle {}{} le {} de {} à {}. Confirmez-vous ?".format(
                    salle_nom, activite_str, jour, heure_debut, heure_fin
                )
                
                # Marquer qu'une annulation est en attente de confirmation
                self._set_cancellation_flow(session_id, {
                    "user_name": user_name,
                    "reservation_id": str(reservation.get("_id")),
                    "awaiting_confirmation": True,
                    "salle_nom": salle_nom,
                    "jour": jour,
                    "heure_debut": heure_debut,
                    "heure_fin": heure_fin,
                    "activite": activite
                })
                
                self._append_message(session_id, "assistant", text)
                return text, {
                    "type": "cancel_confirmation",
                    "reservation": {
                        "salle": salle_nom,
                        "jour": jour,
                        "heure_debut": heure_debut,
                        "heure_fin": heure_fin,
                        "activite": activite
                    }
                }
            else:
                # Plusieurs réservations : demander laquelle annuler
                reservation_list = []
                for r in reservations:
                    salle_id = r.get("salle")
                    salle_doc = db.get_collection("salle").find_one({"_id": salle_id}) if salle_id else {}
                    salle_nom = salle_doc.get("nom", "inconnue") if salle_doc else "inconnue"
                    jour = r.get("jour", "?")
                    heure_debut = r.get("heure_debut", "?")
                    reservation_list.append({
                        "id": str(r.get("_id")),
                        "salle": salle_nom,
                        "jour": jour,
                        "heure_debut": heure_debut
                    })
                
                # Préparer la question
                res_descriptions = [
                    "{} ({} à {})".format(r["salle"], r["jour"], r["heure_debut"])
                    for r in reservation_list
                ]
                
                text = "Vous avez {} réservations actives : {}. Laquelle voulez-vous annuler ?".format(
                    len(reservations), ", ".join(res_descriptions)
                )
                
                # Marquer qu'on attend le choix
                self._set_cancellation_flow(session_id, {
                    "user_name": user_name,
                    "awaiting_choice": True,
                    "reservations": reservation_list
                })
                
                self._append_message(session_id, "assistant", text)
                return text, {
                    "type": "cancel_choose_reservation",
                    "reservations": reservation_list
                }
        
        # ─── CONTINUATION DU FLUX D'ANNULATION ───
        if self._is_cancellation_in_progress(session_id):
            session = self.sessions.get(session_id)
            cancellation_flow = session.get("cancellation_flow", {})
            
            if cancellation_flow.get("awaiting_confirmation"):
                # L'utilisateur doit confirmer l'annulation
                user_text_lower = user_text.lower()
                
                # Chercher une confirmation (oui, confirme, etc.) ou une annulation (non, non merci)
                if re.search(r'\b(oui|ouais|d\'accord|ok|c\'est bon|confirme|annule|valide|yes)\b', user_text_lower):
                    # Confirmation reçue : procéder à l'annulation
                    reservation_id = cancellation_flow.get("reservation_id")
                    if self._cancel_booking(reservation_id):
                        salle = cancellation_flow.get("salle_nom")
                        jour = cancellation_flow.get("jour")
                        heure = cancellation_flow.get("heure_debut")
                        
                        text = "Votre réservation pour la salle {} le {} à {} a été annulée avec succès.".format(
                            salle, jour, heure
                        )
                        self._clear_cancellation_flow(session_id)
                        self._append_message(session_id, "assistant", text)
                        return text, {"type": "cancel_success"}
                    else:
                        text = "Une erreur s'est produite lors de l'annulation. Veuillez réessayer."
                        self._clear_cancellation_flow(session_id)
                        self._append_message(session_id, "assistant", text)
                        return text, {"type": "cancel_error", "reason": "database_error"}
                
                elif re.search(r'\b(non|pas|annule pas|annuler pas|ne.*pas|n\'annule)\b', user_text_lower):
                    # Annulation du flux
                    text = "D'accord, la réservation n'a pas été annulée."
                    self._clear_cancellation_flow(session_id)
                    self._append_message(session_id, "assistant", text)
                    return text, {"type": "cancel_aborted"}
                else:
                    # Réponse non comprise
                    text = "Je n'ai pas compris votre réponse. Confirmez-vous l'annulation ? (oui/non)"
                    self._append_message(session_id, "assistant", text)
                    return text, {"type": "cancel_confirmation", "awaiting_answer": True}
            
            elif cancellation_flow.get("awaiting_choice"):
                # L'utilisateur doit choisir quelle réservation annuler
                reservations = cancellation_flow.get("reservations", [])
                user_text_lower = user_text.lower()
                
                # Chercher une correspondance avec les réservations (salle, jour, heure)
                chosen_reservation = None
                for res in reservations:
                    salle = res["salle"].lower()
                    jour = res["jour"].lower()
                    if salle in user_text_lower or jour in user_text_lower:
                        chosen_reservation = res
                        break
                
                if chosen_reservation:
                    # Demander confirmation
                    text = "Je vais annuler votre réservation pour la salle {} le {} à {}. Confirmez-vous ?".format(
                        chosen_reservation["salle"], chosen_reservation["jour"], chosen_reservation["heure_debut"]
                    )
                    
                    cancellation_flow["awaiting_confirmation"] = True
                    cancellation_flow["reservation_id"] = chosen_reservation["id"]
                    cancellation_flow["salle_nom"] = chosen_reservation["salle"]
                    cancellation_flow["jour"] = chosen_reservation["jour"]
                    cancellation_flow["heure_debut"] = chosen_reservation["heure_debut"]
                    cancellation_flow.pop("awaiting_choice", None)
                    
                    self._set_cancellation_flow(session_id, cancellation_flow)
                    self._append_message(session_id, "assistant", text)
                    return text, {"type": "cancel_confirmation"}
                else:
                    text = "Je n'ai pas compris votre choix. Quelle réservation souhaitez-vous annuler ?"
                    self._append_message(session_id, "assistant", text)
                    return text, {"type": "cancel_choose_reservation"}
        
        # --- Greeting ---
        if intent == "greeting":
            if user_name:
                # Personne reconnue → inclure le rôle dans le contexte
                if user_role and user_role != "utilisateur":
                    context_msg = "L'utilisateur s'appelle '{}' et c'est un {}. Il/elle me salue. Je dois lui répondre chaleureusement en mentionnant son rôle.".format(user_name, user_role)
                else:
                    context_msg = "L'utilisateur s'appelle '{}' et me salue. Je dois lui répondre chaleureusement de façon personnalisée.".format(user_name)
            else:
                # Personne inconnue → laisser le LLM générer une présentation appropriée
                context_msg = "L'utilisateur me salue. Je dois me présenter et expliquer ce que je peux faire."
            
            self._append_message(session_id, "assistant", context_msg)
            try:
                print("[DialogManager] greeting: Appel LLM pour générer une réponse adaptée")
                assistant_text = self.llm.generate_chat(self.system_prompt, history)
                if assistant_text and assistant_text.strip():
                    # Remplacer le message context par la vraie réponse LLM
                    session = self.sessions.get(session_id)
                    session["history"][-1] = {"role": "assistant", "content": assistant_text}
                    self.sessions.update(session_id, session)
                    return assistant_text, {}
            except Exception as e:
                print("[DialogManager] LLM error for greeting:", e)
            
            # Fallback si LLM échoue
            if user_name:
                if user_role and user_role != "utilisateur":
                    text = "Bonjour {} {} ! Comment puis-je vous aider aujourd'hui ?".format(user_role, user_name)
                else:
                    text = "Bonjour {} ! Comment puis-je vous aider aujourd'hui ?".format(user_name)
            else:
                text = (
                    "Bonjour ! Je suis Pepper, le robot d'accueil de la salle multisports. "
                    "Je peux vous aider pour les horaires, les activités, "
                    "les réservations ou pour vous orienter. Que souhaitez-vous ?"
                )
            self._append_message(session_id, "assistant", text)
            return text, {}
        
        # --- Horaires du centre ---
        if intent == "demander_heure":
            horaires = self._get_center_hours()
            
            # Construire le message avec les horaires
            ouverture = horaires["ouverture_heure"]
            fermeture = horaires["fermeture_heure"]
            horaires_text = "Le centre est ouvert de {} à {}.".format(ouverture, fermeture)
            
            # Laisser le LLM reformuler les horaires
            context_msg = "L'utilisateur demande les horaires d'ouverture du centre. Horaires: {}".format(horaires_text)
            self._append_message(session_id, "assistant", context_msg)
            
            try:
                print("[DialogManager] demander_heure: Appel LLM pour reformuler les horaires")
                assistant_text = self.llm.generate_chat(self.system_prompt, history)
                if assistant_text and assistant_text.strip():
                    # Remplacer le message context par la vraie réponse LLM
                    session = self.sessions.get(session_id)
                    session["history"][-1] = {"role": "assistant", "content": assistant_text}
                    self.sessions.update(session_id, session)
                    actions = {
                        "type": "provide_hours",
                        "hours": horaires
                    }
                    return assistant_text, actions
            except Exception as e:
                print("[DialogManager] LLM error for hours:", e)
            
            # Fallback si LLM échoue
            text = horaires_text
            self._append_message(session_id, "assistant", text)
            actions = {
                "type": "provide_hours",
                "hours": horaires
            }
            return text, actions
        
        # --- Tarifs des activités ---
        if intent == "ask_pricing":
            # Essayer d'extraire le nom de l'activité
            activities = entities.get("activity", [])
            activite_name = activities[0] if activities else None
            
            if activite_name:
                # Récupérer le tarif d'une activité spécifique
                pricing_info = self._get_activity_pricing(activite_name)
                
                if pricing_info:
                    activite = pricing_info.get("activite", "")
                    tarif = pricing_info.get("tarif", "Non spécifié")
                    description = pricing_info.get("description", "")
                    
                    # Passer les données exactes au LLM pour qu'il les reformule
                    # Format strict pour éviter les hallucinations
                    context_msg = (
                        "TARIF D'INSCRIPTION POUR L'ANNÉE:\n"
                        "Activité: {}\n"
                        "Tarif annuel: {} euros par an\n"
                        "Description: {}\n"
                        "\n"
                        "L'utilisateur demande le tarif pour cette activité. "
                        "Réponds en communiquant EXACTEMENT ce tarif annuel, pas d'autres chiffres ou périodes. "
                        "Sois clair que c'est pour une année d'adhésion."
                    ).format(activite, tarif, description)
                    
                    self._append_message(session_id, "assistant", context_msg)
                    try:
                        print("[DialogManager] ask_pricing: Appel LLM pour reformuler le tarif")
                        assistant_text = self.llm.generate_chat(self.system_prompt, history)
                        if assistant_text and assistant_text.strip():
                            session = self.sessions.get(session_id)
                            session["history"][-1] = {"role": "assistant", "content": assistant_text}
                            self.sessions.update(session_id, session)
                            actions = {
                                "type": "provide_pricing",
                                "activity": activite,
                                "pricing": pricing_info
                            }
                            return assistant_text, actions
                    except Exception as e:
                        print("[DialogManager] LLM error for pricing:", e)
                    
                    # Si LLM échoue, générer une réponse simple
                    text = "Le tarif d'adhésion annuelle pour {} est de {} euros par an.".format(activite, tarif)
                    if description:
                        text += " ({})".format(description)
                    self._append_message(session_id, "assistant", text)
                    actions = {
                        "type": "provide_pricing",
                        "activity": activite,
                        "pricing": pricing_info
                    }
                    return text, actions
                else:
                    text = "Désolé, je n'ai pas trouvé l'activité '{}'.".format(activite_name)
                    self._append_message(session_id, "assistant", text)
                    return text, {"type": "pricing_not_found"}
            else:
                # Afficher tous les tarifs
                pricing_info = self._get_activity_pricing()
                
                if pricing_info and pricing_info.get("all_activities"):
                    all_activities = pricing_info.get("all_activities", [])
                    
                    # Format strict avec toutes les données
                    activities_list = "\n".join([
                        "- {}: {} euros par an".format(a["nom"], a["tarif"]) for a in all_activities
                    ])
                    
                    context_msg = (
                        "TARIFS D'INSCRIPTION ANNUELS:\n{}\n\n"
                        "L'utilisateur demande les tarifs d'adhésion aux activités. "
                        "Réponds en communiquant EXACTEMENT ces tarifs annuels dans ta réponse, pas d'autres chiffres. "
                        "Sois clair que c'est pour une année d'adhésion complète."
                    ).format(activities_list)
                    
                    self._append_message(session_id, "assistant", context_msg)
                    try:
                        print("[DialogManager] ask_pricing (all): Appel LLM pour reformuler les tarifs")
                        assistant_text = self.llm.generate_chat(self.system_prompt, history)
                        if assistant_text and assistant_text.strip():
                            session = self.sessions.get(session_id)
                            session["history"][-1] = {"role": "assistant", "content": assistant_text}
                            self.sessions.update(session_id, session)
                            actions = {
                                "type": "provide_all_pricing",
                                "activities": all_activities
                            }
                            return assistant_text, actions
                    except Exception as e:
                        print("[DialogManager] LLM error for all pricing:", e)
                    
                    # Si LLM échoue, générer une réponse simple
                    text = "Voici nos tarifs d'adhésion annuels:\n" + "\n".join([
                        "• {}: {} euros par an".format(a["nom"], a["tarif"]) for a in all_activities
                    ])
                    self._append_message(session_id, "assistant", text)
                    actions = {
                        "type": "provide_all_pricing",
                        "activities": all_activities
                    }
                    return text, actions
                else:
                    text = "Désolé, les tarifs ne sont pas disponibles pour le moment."
                    self._append_message(session_id, "assistant", text)
                    return text, {"type": "pricing_error"}
        
        # --- Navigate ---
        if intent == "navigate":
            locations = entities.get("location", [])
            if locations:
                dest_key = locations[0]
                nav = get_navigation_instructions(dest_key)

                if nav:
                    steps = nav["instructions"]
                    destination = nav["destination"]
                    # Concaténer les instructions en un texte lisible
                    instructions_text = " ".join(steps)
                    
                    # Laisser le LLM reformuler les instructions de navigation
                    context_msg = "L'utilisateur demande comment aller à '{}'. Voici les instructions: {}".format(
                        destination, instructions_text
                    )
                    self._append_message(session_id, "assistant", context_msg)
                    try:
                        print("[DialogManager] navigate: Appel LLM pour reformuler les instructions")
                        assistant_text = self.llm.generate_chat(self.system_prompt, history)
                        if assistant_text and assistant_text.strip():
                            # Remplacer le message context par la vraie réponse LLM
                            session = self.sessions.get(session_id)
                            session["history"][-1] = {"role": "assistant", "content": assistant_text}
                            self.sessions.update(session_id, session)
                            actions = {
                                "type": "navigate",
                                "destination": destination,
                                "destination_key": nav["destination_key"],
                                "path": nav["path"],
                                "instructions": steps,
                            }
                            return assistant_text, actions
                    except Exception as e:
                        print("[DialogManager] LLM error for navigate:", e)
                    
                    # Fallback si LLM échoue
                    intro = "Je vais vous guider vers {}. ".format(destination)
                    text = intro + instructions_text
                    actions = {
                        "type": "navigate",
                        "destination": destination,
                        "destination_key": nav["destination_key"],
                        "path": nav["path"],
                        "instructions": steps,
                    }
                    self._append_message(session_id, "assistant", text)
                    return text, actions
                else:
                    text = "Désolé, je ne connais pas cet endroit. Pouvez-vous reformuler ?"
                    self._append_message(session_id, "assistant", text)
                    return text, {"type": "navigate_error"}
            else:
                text = "Où souhaitez-vous aller ? Vous pouvez me dire par exemple : salle A, salle B, natation..."
                self._append_message(session_id, "assistant", text)
                return text, {"type": "navigate"}

        elif intent == "ask_activities":
            activity = entities.get("activity", [""])[0]
            if not activity:
                cursor = db.get_collection("activite").find({}, {"_id": 0, "nom": 1})
                names = list(sport["nom"] for sport in cursor)
                print(names)
                # Laisser le LLM reformuler la liste d'activités
                activities_list = ", ".join(names) if names else "plusieurs activités"
                # Ajouter un message système pour guider le LLM
                context_msg = "Voici la liste de nos activités: {}. L'utilisateur m'a demandé quelles activités nous proposons.".format(activities_list)
                self._append_message(session_id, "assistant", context_msg)
                # Laisser le LLM générer sa propre réponse
                try:
                    print("[DialogManager] ask_activities: Appel LLM pour reformuler la liste")
                    assistant_text = self.llm.generate_chat(self.system_prompt, history)
                    if assistant_text and assistant_text.strip():
                        # Remplacer le message context par la vraie réponse LLM
                        session = self.sessions.get(session_id)
                        session["history"][-1] = {"role": "assistant", "content": assistant_text}
                        self.sessions.update(session_id, session)
                        actions = {"type": "ask_activity"}
                        return assistant_text, actions
                except Exception as e:
                    print("[DialogManager] LLM error for ask_activities:", e)
                
                # Fallback si LLM échoue
                text = "Nous proposons les activités suivantes : {}. Laquelle vous intéresse ?".format(activities_list)
                actions = {"type": "ask_activity"}
                return text, actions
            else:
                activity = activity.capitalize()
                print("[DialogManager] User asked about activity:", activity)
                info = db.get_collection("activite").find_one({"nom": activity}, {"_id": 0})
                print(info)
                if info:
                    # Passer les infos au LLM pour qu'il reformule
                    description = info.get("description", "")
                    context_msg = "L'utilisateur a demandé des infos sur l'activité '{}'. Voici les détails: {}".format(
                        activity, description
                    )
                    self._append_message(session_id, "assistant", context_msg)
                    try:
                        print("[DialogManager] ask_activities (spécific): Appel LLM pour reformuler")
                        assistant_text = self.llm.generate_chat(self.system_prompt, history)
                        if assistant_text and assistant_text.strip():
                            # Remplacer le message context par la vraie réponse LLM
                            session = self.sessions.get(session_id)
                            session["history"][-1] = {"role": "assistant", "content": assistant_text}
                            self.sessions.update(session_id, session)
                            info_serializable = json.loads(json.dumps(info, default=str))
                            actions = {
                                "type": "provide_activity_info",
                                "activity": activity,
                                "info": info_serializable,
                            }
                            return assistant_text, actions
                    except Exception as e:
                        print("[DialogManager] LLM error for activity info:", e)
                    
                    # Fallback si LLM échoue
                    text = "L'activité {} est disponible. {}".format(activity, description)
                    info_serializable = json.loads(json.dumps(info, default=str))
                    actions = {
                        "type": "provide_activity_info",
                        "activity": activity,
                        "info": info_serializable,
                    }
                    self._append_message(session_id, "assistant", text)
                    return text, actions
                else:
                    text = "Désolé, je n'ai pas trouvé d'informations sur l'activité {}.".format(activity)
                    self._append_message(session_id, "assistant", text)
                    return text, actions

        elif intent == "ask_available_slots":
            # L'utilisateur demande les créneaux disponibles
            entities_list = entities.get("activity", [])
            activity = entities_list[0] if entities_list else None
            
            locations_list = entities.get("location", [])
            location = locations_list[0] if locations_list else None
            
            times_list = entities.get("time", [])
            date_requested = times_list[0] if times_list else None
            
            # Si on a une activité, montrer les créneaux pour cette activité
            if activity:
                activity = activity.capitalize()
                # Par défaut, on cherche pour aujourd'hui/demain
                if not date_requested:
                    from datetime import datetime, timedelta
                    date_requested = datetime.now().strftime("%Y-%m-%d")
                
                # Obtenir les créneaux disponibles
                try:
                    slots_dict = get_available_slots_for_activity(activity, date_requested)
                    
                    if slots_dict:
                        text_parts = ["Voici les créneaux disponibles pour {} le {} :".format(activity, date_requested)]
                        for salle_nom, slots_list in slots_dict.items():
                            times = ", ".join([f"{s['heure_debut']}-{s['heure_fin']}" for s in slots_list])
                            text_parts.append(f"  • {salle_nom}: {times}")
                        text = "\n".join(text_parts)
                        
                        actions = {
                            "type": "show_available_slots",
                            "activity": activity,
                            "date": date_requested,
                            "slots": slots_dict
                        }
                    else:
                        text = "Désolé, il n'y a pas de créneaux disponibles pour {} le {}. Voulez-vous essayer un autre jour ?".format(
                            activity, date_requested
                        )
                        actions = {"type": "no_slots_available"}
                except Exception as e:
                    print("[DialogManager] Erreur lors de la récupération des créneaux:", e)
                    text = "Désolé, je n'ai pas pu récupérer les créneaux disponibles. Pouvez-vous préciser l'activité et la date ?"
                    actions = {"type": "error"}
                
                self._append_message(session_id, "assistant", text)
                return text, actions
            
            elif location:
                # Si on a une location (salle), montrer les créneaux pour cette salle
                location_normalized = location.replace("_", " ").title()
                db_client = DatabaseMongo()
                salle_doc = db_client.get_collection("salle").find_one(
                    {"nom": {"$regex": location_normalized, "$options": "i"}},
                    {"_id": 1, "nom": 1, "horaire_ouverture": 1, "horaire_fermeture": 1}
                )
                db_client.close()
                
                if salle_doc:
                    if not date_requested:
                        from datetime import datetime
                        date_requested = datetime.now().strftime("%Y-%m-%d")
                    
                    try:
                        opening = salle_doc.get("horaire_ouverture", "08:00")
                        closing = salle_doc.get("horaire_fermeture", "22:00")
                        slots_available = get_available_slots(
                            salle_doc["_id"], date_requested, opening, closing
                        )
                        
                        if slots_available:
                            times = ", ".join([f"{s['heure_debut']}-{s['heure_fin']}" for s in slots_available])
                            text = "Les créneaux disponibles dans {} le {} sont : {}".format(
                                salle_doc["nom"], date_requested, times
                            )
                            actions = {
                                "type": "show_available_slots_for_room",
                                "salle_nom": salle_doc["nom"],
                                "date": date_requested,
                                "slots": slots_available
                            }
                        else:
                            text = "Désolé, la salle {} n'a pas de créneaux disponibles le {}. Voulez-vous essayer un autre jour ?".format(
                                salle_doc["nom"], date_requested
                            )
                            actions = {"type": "no_slots_available"}
                    except Exception as e:
                        print("[DialogManager] Erreur lors de la récupération des créneaux:", e)
                        text = "Désolé, je n'ai pas pu récupérer les créneaux disponibles."
                        actions = {"type": "error"}
                else:
                    text = "Désolé, je n'ai pas trouvé la salle '{}' dans notre système.".format(location)
                    actions = {"type": "error", "reason": "room_not_found"}
                
                self._append_message(session_id, "assistant", text)
                return text, actions
            
            else:
                # Pas d'activité ni de salle spécifiée, demander plus de précisions
                text = "Voulez-vous connaître les créneaux disponibles pour une activité spécifique ou pour une salle en particulier ? Dites-moi quelle activité ou quelle salle vous intéresse."
                self._append_message(session_id, "assistant", text)
                return text, {"type": "ask_available_slots_clarification"}

        elif intent == "ask_my_reservations":
            # L'utilisateur demande ses réservations
            
            # Vérifier si l'utilisateur est authentifié ou s'il a fourni son nom dans la session
            current_user_name = user_name
            
            # Essayer de récupérer le nom depuis la session s'il n'est pas dans la requête
            if not current_user_name:
                session = self.sessions.get(session_id)
                current_user_name = session.get("reservation_user_name")
            
            # Si toujours pas de nom, demander à l'utilisateur
            if not current_user_name:
                # Message pour demander le nom
                text = "Pouvez-vous me donner votre nom s'il vous plaît ? Cela m'aidera à localiser vos réservations dans notre base de données."
                
                # Marquer qu'on attend le nom pour les réservations
                session = self.sessions.get(session_id)
                session["awaiting_user_name_for_reservations"] = True
                self.sessions.update(session_id, session)
                
                self._append_message(session_id, "assistant", text)
                return text, {"type": "ask_user_name_for_reservations"}
            
            # Vérifier si l'utilisateur a donné son nom suite à la demande
            if "awaiting_user_name_for_reservations" in self.sessions.get(session_id):
                # Le user_text devrait contenir le nom
                current_user_name = user_text.strip()
                
                # Sauvegarder le nom dans la session
                session = self.sessions.get(session_id)
                session["reservation_user_name"] = current_user_name
                session.pop("awaiting_user_name_for_reservations", None)
                self.sessions.update(session_id, session)
                
                print(f"[DialogManager] Nom utilisateur sauvegardé pour réservations: {current_user_name}")
            
            try:
                # Récupérer les réservations futures de l'utilisateur
                reservations = get_user_future_reservations(current_user_name, include_past=False)
                
                if not reservations:
                    # Pas de réservations futures
                    text = f"Vous n'avez pas de réservations à venir, {current_user_name}. Voulez-vous en faire une ?"
                    actions = {
                        "type": "no_future_reservations",
                        "user_name": current_user_name
                    }
                    self._append_message(session_id, "assistant", text)
                    return text, actions
                else:
                    # Formater les réservations pour le LLM
                    reservations_info = []
                    for res in reservations:
                        res_info = {
                            "salle": res.get("salle"),
                            "date": res.get("jour"),
                            "heure": f"{res.get('heure_debut')}-{res.get('heure_fin')}",
                            "activite": res.get("activite"),
                            "statut": res.get("statut")
                        }
                        reservations_info.append(res_info)
                    
                    # Préparer un contexte pour le LLM
                    reservations_text = "Voici les réservations de l'utilisateur:\n"
                    for i, res in enumerate(reservations, 1):
                        reservations_text += f"{i}. {res.get('salle')} le {res.get('jour')} de {res.get('heure_debut')} à {res.get('heure_fin')}"
                        if res.get("activite") and res.get("activite") != "Non spécifiée":
                            reservations_text += f" ({res.get('activite')})"
                        reservations_text += f" - Statut: {res.get('statut')}\n"
                    
                    reservations_text += f"\nL'utilisateur '{current_user_name}' m'a demandé ses réservations. Je dois lui présenter cette information de manière conviviale et claire."
                    
                    # Ajouter le contexte au historique pour le LLM
                    self._append_message(session_id, "assistant", reservations_text)
                    
                    try:
                        # Laisser le LLM générer une réponse naturelle
                        print("[DialogManager] ask_my_reservations: Calling LLM to format reservations")
                        assistant_text = self.llm.generate_chat(self.system_prompt, history)
                        
                        if assistant_text and assistant_text.strip():
                            # Remplacer le message context par la réponse du LLM
                            session = self.sessions.get(session_id)
                            session["history"][-1] = {"role": "assistant", "content": assistant_text}
                            self.sessions.update(session_id, session)
                            
                            actions = {
                                "type": "show_reservations",
                                "user_name": current_user_name,
                                "reservations_count": len(reservations),
                                "reservations": [json.loads(json.dumps(r, default=str)) for r in reservations_info]
                            }
                            return assistant_text, actions
                    except LLMError as e:
                        print(f"[DialogManager] LLM error for ask_my_reservations: {e}")
                    
                    # Fallback si LLM échoue : générer une réponse simple
                    if len(reservations) == 1:
                        res = reservations[0]
                        text = "Vous avez une réservation : {} le {} de {} à {}.".format(
                            res.get("salle"), res.get("jour"), res.get("heure_debut"), res.get("heure_fin")
                        )
                    else:
                        text = f"Vous avez {len(reservations)} réservations à venir :\n"
                        for i, res in enumerate(reservations, 1):
                            text += f"{i}. {res.get('salle')} le {res.get('jour')} de {res.get('heure_debut')} à {res.get('heure_fin')}\n"
                    
                    actions = {
                        "type": "show_reservations",
                        "user_name": current_user_name,
                        "reservations_count": len(reservations),
                        "reservations": [json.loads(json.dumps(r, default=str)) for r in reservations_info]
                    }
                    self._append_message(session_id, "assistant", text)
                    return text, actions
            
            except Exception as e:
                print(f"[DialogManager] Erreur lors de la récupération des réservations: {e}")
                text = "Désolé, je n'ai pas pu récupérer vos réservations. Veuillez réessayer plus tard."
                self._append_message(session_id, "assistant", text)
                return text, {"type": "error", "reason": "reservation_retrieval_failed"}

        # --- Unknown Intent ---
        # Quand l'intention n'est pas reconnue, laisser le LLM générer une réponse
        # avec un contexte d'aide
        if intent == "unknown":
            context_msg = (
                "L'utilisateur a dit quelque chose que je n'ai pas bien compris. "
                "Voici ce qu'il a dit: '{}'. "
                "Je dois répondre poliment et proposer comment je peux l'aider dans la salle multisports."
            ).format(user_text)
            self._append_message(session_id, "assistant", context_msg)
            try:
                print("[DialogManager] unknown intent: Calling LLM with helpful context")
                assistant_text = self.llm.generate_chat(self.system_prompt, history)
                if assistant_text and assistant_text.strip():
                    # Remplacer le message context par la vraie réponse LLM
                    session = self.sessions.get(session_id)
                    session["history"][-1] = {"role": "assistant", "content": assistant_text}
                    self.sessions.update(session_id, session)
                    return assistant_text, {}
            except Exception as e:
                print("[DialogManager] LLM error for unknown intent:", e)
            
            # Fallback amélioré pour unknown
            fallback_text = (
                "Je n'ai pas bien compris votre demande. Je suis ici pour vous aider avec : "
                "les horaires, les activités disponibles, les réservations ou l'orientation dans le bâtiment. "
                "Pouvez-vous me dire ce qui vous intéresse ?"
            )
            self._append_message(session_id, "assistant", fallback_text)
            return fallback_text, {}

        # Try LLM generation
        try:
            print("[DialogManager] calling LLM with intent:", intent)
            print("[DialogManager] System prompt length:", len(self.system_prompt))
            print("[DialogManager] History length:", len(history))

            assistant_text = self.llm.generate_chat(self.system_prompt, history)
            
            if not assistant_text or not assistant_text.strip():
                print("[DialogManager] WARNING: LLM returned empty response, using fallback")
                raise LLMError("Empty response from LLM")
            
            print("[DialogManager] LLM response length:", len(assistant_text))
            
            self._append_message(session_id, "assistant", assistant_text)
            return assistant_text, actions
        except LLMError as e:
            print("[DialogManager] LLMError:", e)
            rule_val = RULES.get(intent)
            if rule_val:
                if isinstance(rule_val, list):
                    tmpl = random.choice(rule_val)
                else:
                    tmpl = rule_val

                if "{" in tmpl:
                    resp = tmpl.format(**entities)
                else:
                    resp = tmpl

                self._append_message(session_id, "assistant", resp)
                return resp, {}

            default = "Désolé, le système de dialogue n'est pas disponible pour le moment. Pouvez-vous reformuler ?"
            self._append_message(session_id, "assistant", default)
            return default, {}

        
if __name__ == "__main__":
    import time
    
    # 1. Initialize the storage and manager
    # In production, this persists as long as the robot's process is running
    store = SessionStore(ttl_seconds=3600)
    dm = DialogManager(store)
    
    # 2. Simulate a unique session ID (e.g., generated when a person is detected)
    sid = "robot_session_xyz"
    
    print("--- STEP 1: Initial State ---")
    # This creates the entry in SessionStorejj
    initial_sid = store.create_session() 
    print("Store after creation:", store.get(initial_sid))

    print("\n--- STEP 2: First Interaction (Greeting) ---")
    # Simulation of what the NLU (Natural Language Understanding) would pass to the manager
    parse_1 = {
        "intent": "greeting",
        "raw_text": "Bonjour, comment tu t'appelles ?"
    }
    
    # The 'handle' method will: 
    #   1. Call _append_message (User) -> updates _store
    #   2. Call LLMClient -> gets response
    #   3. Call _append_message (Assistant) -> updates _store
    response, actions = dm.handle(sid, parse_1)
    
    print("Robot Response:", response)
    print("Updated History:", store.get(sid)["history"])

    print("\n--- STEP 3: Second Interaction (Contextual) ---")
    parse_2 = {
        "intent": "ask_activities",
        "raw_text": "Quelles sont les activités ?"
    }
    dm.handle(sid, parse_2)
    
    # Let's look at the SessionStore one last time
    final_state = store.get(sid)
    print("Final 'history' length:", len(final_state["history"]))
    for turn in final_state["history"]:
        print("  {0}: {1}".format(turn['role'], turn['content']))