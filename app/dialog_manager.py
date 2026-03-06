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
from .tools import parse_heure_to_minutes, parse_minutes_to_heure
from app.DB_access import DatabaseMongo

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
    "Si tu ne comprends pas, demande une clarification courte."
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
        max_msgs = 20
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
            found["salle"] = locations[0]

        # --- Activité (sport) ---
        activities = entities.get("activity", [])
        if activities:
            found["activite"] = activities[0]

        # --- Jour / Date ---
        times = entities.get("time", [])
        # On essaie aussi de détecter une date dans le texte brut
        import re
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

    def _handle_booking_flow(self, session_id: str, intent: str, entities: Dict[str, Any], raw_text: str) -> Tuple[str, Dict[str, Any]]:
        """
        Gère tout le flux de slot filling pour la réservation.
        Retourne (text, actions).
        """
        slots = self._get_booking_slots(session_id)

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
                text = "Désolé, aucune salle n'est disponible pour {} le {} à {}. Voulez-vous essayer un autre créneau ?".format(
                    slots["activite"], slots["jour"], slots["heure"]
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
            text = "Désolé, la salle {} est déjà réservée le {} de {} à {}. Voulez-vous essayer un autre créneau ou une autre salle ?".format(
                salle_nom, jour, heure, heure_fin
            )
            self._clear_booking_slots(session_id)
            self._append_message(session_id, "assistant", text)
            return text, {"type": "booking_no_availability"}

        text = "Parfait ! Je confirme votre réservation de la salle {}{} le {} de {} à {}. Souhaitez-vous autre chose ?".format(
            salle_nom, activite_str, jour, heure, heure_fin
        )

        actions = {
            "type": "booking_confirmed",
            "booking": {
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
            reservation_data = {
                "salle": salle_id,
                "activite": activite,
                "jour": jour,
                "heure_debut": heure,
                "heure_fin": heure_fin,
                "statut": "confirmee",
            }
            db.get_collection("reservations").insert_one(reservation_data)
            print("[BookingFlow] Réservation enregistrée:", reservation_data)
        except Exception as e:
            print("[BookingFlow] Erreur lors de l'enregistrement:", e)

        self._clear_booking_slots(session_id)
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
            return self._handle_booking_flow(session_id, intent, entities, user_text)

        # ─── NOUVELLE RÉSERVATION ───
        if intent == "book_activity":
            # Initialiser les slots et démarrer le flux
            self._set_booking_slots(session_id, {})
            return self._handle_booking_flow(session_id, intent, entities, user_text)

        # --- Navigate ---
        if intent == "navigate":
            locations = entities.get("location", [])
            if locations:
                dest_key = locations[0]
                nav = get_navigation_instructions(dest_key)

                if nav:
                    steps = nav["instructions"]
                    intro = "Je vais vous guider vers {}. ".format(nav["destination"])
                    body = " ".join(steps)
                    text = intro + body

                    actions = {
                        "type": "navigate",
                        "destination": nav["destination"],
                        "destination_key": nav["destination_key"],
                        "path": nav["path"],
                        "instructions": nav["instructions"],
                    }
                    self._append_message(session_id, "assistant", text)
                    return text, actions
                else:
                    text = "Désolé, je ne connais pas cet endroit. Pouvez-vous reformuler ?"
                    self._append_message(session_id, "assistant", text)
                    return text, actions
            else:
                text = "Où souhaitez-vous aller ? Vous pouvez me dire par exemple : salle A, salle B, natation..."
                self._append_message(session_id, "assistant", text)
                return text, actions

        elif intent == "ask_activities":
            activity = entities.get("activity", [""])[0]
            if not activity:
                cursor = db.get_collection("activite").find({}, {"_id": 0, "nom": 1})
                names = list(sport["nom"] for sport in cursor)
                print(names)
                text = "Nous proposons les activités suivantes : {}. Laquelle vous intéresse ?".format(", ".join(names)) if names else "Nous proposons plusieurs activités. Laquelle vous intéresse ?"
                self._append_message(session_id, "assistant", text)
                actions = {
                    "type": "ask_activity",
                }
                return text, actions
            else:
                activity = activity.capitalize()
                print("[DialogManager] User asked about activity:", activity)
                info = db.get_collection("activite").find_one({"nom": activity}, {"_id": 0})
                print(info)
                if info:
                    text = "L'activité {} est disponible. {}".format(activity, info.get("description", ""))
                    info_serializable = json.loads(json.dumps(info, default=str))
                    actions = {
                        "type": "provide_activity_info",
                        "activity": activity,
                        "info": info_serializable,
                    }
                else:
                    text = "Désolé, je n'ai pas trouvé d'informations sur l'activité {}.".format(activity)
                self._append_message(session_id, "assistant", text)
                return text, actions

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