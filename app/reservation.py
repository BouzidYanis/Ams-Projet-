from app.DB_access import DatabaseMongo


def reserver_salle(infos_reservation):
    db = DatabaseMongo()
    reservations_collection = db.get_collection("reservation")
    salle_collection = db.get_collection("salle")
    salle_doc = salle_collection.find_one({"nom": infos_reservation.get("salle")})
    infos_reservation = {
        "utilisateur_id": infos_reservation.get("utilisateur_id"),
        "salle": salle_doc.get("_id"),
        "creneau": {
            "jour": infos_reservation.get("creneau", {}).get("jour"),
            "heure_debut": infos_reservation.get("creneau", {}).get("heure_debut"),
            "heure_fin": infos_reservation.get("creneau", {}).get("heure_fin"),
        }
    }
    # Insérer les informations de réservation dans la collection
    result = reservations_collection.insert_one(infos_reservation)
    
    db.close()
    return result.inserted_id


def parse_time_to_minutes(time_str: str) -> int:
    """Convertit une heure au format 'HH:MM' en minutes depuis minuit."""
    if not time_str or ":" not in str(time_str):
        return 0
    parts = str(time_str).split(":")
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    return h * 60 + m


def parse_minutes_to_time(minutes: int) -> str:
    """Convertit les minutes depuis minuit en format 'HH:MM'."""
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


def get_reserved_slots(salle_id, jour: str) -> list:
    """
    Récupère tous les créneaux réservés pour une salle et un jour donnés.
    
    Returns:
        Liste des créneaux réservés: [{"heure_debut": "09:00", "heure_fin": "10:00"}, ...]
    """
    db = DatabaseMongo()
    reservations_collection = db.get_collection("reservations")
    
    query = {
        "salle": salle_id,
        "creneau.jour": jour
    }
    
    reservations = list(reservations_collection.find(
        query,
        {"creneau.heure_debut": 1, "creneau.heure_fin": 1}
    ))
    
    db.close()
    
    slots = []
    for res in reservations:
        creneau = res.get("creneau", {})
        slots.append({
            "heure_debut": creneau.get("heure_debut"),
            "heure_fin": creneau.get("heure_fin")
        })
    
    return slots


def get_available_slots(salle_id, jour: str, horaire_ouverture: str = "08:00", horaire_fermeture: str = "22:00", duree_creneau: int = 60) -> list:
    """
    Calcule les créneaux disponibles pour une salle.
    
    Args:
        salle_id: ID de la salle MongoDB
        jour: Date au format 'YYYY-MM-DD'
        horaire_ouverture: Format 'HH:MM' (défaut 08:00)
        horaire_fermeture: Format 'HH:MM' (défaut 22:00)
        duree_creneau: Durée minimale d'un créneau en minutes (défaut 60)
    
    Returns:
        Liste des créneaux disponibles: [{"heure_debut": "09:00", "heure_fin": "10:00"}, ...]
    """
    # Récupérer les créneaux réservés
    reserved = get_reserved_slots(salle_id, jour)
    
    # Convertir les horaires en minutes
    opening = parse_time_to_minutes(horaire_ouverture)
    closing = parse_time_to_minutes(horaire_fermeture)
    
    # Créer une liste des "non-disponibilités"
    occupied_ranges = []
    for slot in reserved:
        start = parse_time_to_minutes(slot["heure_debut"])
        end = parse_time_to_minutes(slot["heure_fin"])
        occupied_ranges.append((start, end))
    
    # Trier les ranges occupés
    occupied_ranges.sort()
    
    # Calculer les créneaux disponibles
    available = []
    current_time = opening
    
    for start, end in occupied_ranges:
        # S'il y a de l'espace avant ce créneau occupé
        if current_time < start:
            gap_duration = start - current_time
            if gap_duration >= duree_creneau:
                available.append({
                    "heure_debut": parse_minutes_to_time(current_time),
                    "heure_fin": parse_minutes_to_time(start)
                })
        current_time = max(current_time, end)
    
    # Vérifier s'il y a de l'espace après le dernier créneau
    if current_time < closing:
        gap_duration = closing - current_time
        if gap_duration >= duree_creneau:
            available.append({
                "heure_debut": parse_minutes_to_time(current_time),
                "heure_fin": parse_minutes_to_time(closing)
            })
    
    return available


def get_available_slots_for_activity(activite: str, jour: str) -> dict:
    """
    Récupère les salles et les créneaux disponibles pour une activité à une date donnée.
    
    Returns:
        Dict: {
            "salle_nom": [{"heure_debut": "09:00", "heure_fin": "10:00"}, ...],
            ...
        }
    """
    db = DatabaseMongo()
    salle_collection = db.get_collection("salle")
    
    # Trouver les salles qui supportent cette activité
    salles = list(salle_collection.find(
        {"activites_supportees": {"$regex": activite, "$options": "i"}},
        {"_id": 1, "nom": 1, "horaire_ouverture": 1, "horaire_fermeture": 1}
    ))
    
    db.close()
    
    result = {}
    for salle in salles:
        salle_id = salle["_id"]
        salle_nom = salle.get("nom", "Inconnue")
        opening = salle.get("horaire_ouverture", "08:00")
        closing = salle.get("horaire_fermeture", "22:00")
        
        slots = get_available_slots(salle_id, jour, opening, closing)
        if slots:
            result[salle_nom] = slots
    
    return result


def get_alternative_slots(salle_id, jour: str, heure_demandee: str, duree: int = 60, max_alternatives: int = 3) -> list:
    """
    Récupère les créneaux alternatifs pour une salle quand le créneau demandé n'est pas disponible.
    
    Args:
        salle_id: ID de la salle MongoDB
        jour: Date au format 'YYYY-MM-DD'
        heure_demandee: Heure demandée au format 'HH:MM'
        duree: Durée du créneau en minutes
        max_alternatives: Nombre max d'alternatives à retourner
    
    Returns:
        Liste des créneaux alternatifs proches de l'heure demandée
    """
    available = get_available_slots(salle_id, jour)
    if not available:
        return []
    
    heure_minutes = parse_time_to_minutes(heure_demandee)
    
    # Trier par proximité à l'heure demandée
    alternatives = sorted(
        available,
        key=lambda slot: abs(parse_time_to_minutes(slot["heure_debut"]) - heure_minutes)
    )
    
    return alternatives[:max_alternatives]


def get_user_future_reservations(user_name: str, include_past: bool = False) -> list:
    """
    Récupère toutes les réservations futures d'un utilisateur.
    
    Args:
        user_name: Nom de l'utilisateur
        include_past: Si True, inclut aussi les réservations passées
    
    Returns:
        Liste des réservations formatées pour la présentation au LLM
    """
    from datetime import datetime, timedelta
    
    db = DatabaseMongo()
    reservations_col = db.get_collection("reservations")
    salle_col = db.get_collection("salle")
    
    # Récupérer les réservations de cet utilisateur
    query = {"user_name": user_name}
    reservations = list(reservations_col.find(query))
    
    # Filtrer et formater les réservations
    formatted = []
    today = datetime.now().date()
    
    for res in reservations:
        try:
            # Extraire les données
            jour_str = res.get("jour", "")
            heure_debut = res.get("heure_debut", "")
            heure_fin = res.get("heure_fin", "")
            salle_id = res.get("salle")
            activite = res.get("activite", "")
            statut = res.get("statut", "confirmée")
            
            # Convertir la date
            try:
                jour_date = datetime.strptime(jour_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                jour_date = None
            
            # Filtrer les réservations
            if jour_date:
                # Vérifier si la réservation est future ou passée
                if jour_date < today and not include_past:
                    continue  # Ignorer les réservations passées
                
                # Récupérer le nom de la salle
                salle_nom = "Salle inconnue"
                if salle_id:
                    try:
                        salle_doc = salle_col.find_one({"_id": salle_id})
                        if salle_doc:
                            salle_nom = salle_doc.get("nom", "Salle inconnue")
                    except:
                        pass
                
                # Formater pour la présentation
                formatted.append({
                    "salle": salle_nom,
                    "jour": jour_str,
                    "heure_debut": heure_debut,
                    "heure_fin": heure_fin,
                    "activite": activite if activite else "Non spécifiée",
                    "statut": statut,
                    "jour_date": jour_date  # Pour tri
                })
        except Exception as e:
            print(f"[ERROR] Erreur lors du traitement d'une réservation: {e}")
            continue
    
    db.close()
    
    # Trier par date croissante
    formatted.sort(key=lambda x: x.get("jour_date", datetime.now().date()))
    
    return formatted

