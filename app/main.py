from fastapi import FastAPI, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from typing import Optional, Dict, Any, Set
import uvicorn
import shutil
import os
import json
from datetime import datetime

from app.nlu import NLU
from app.dialog_manager import DialogManager
from app.sessions import SessionStore
from app.DB_access import DatabaseMongo
from app.speech import ASRModule

from app.face import verify_endpoint, VerifyResponse
from app.reservation import reserver_salle
from app.navigation import InstructionGenerator

app = FastAPI(title="Serveur de dialogue - Robot d'accueil")

# CORS support pour les connexions WebSocket depuis la tablette
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gestionnaire de connexions WebSocket
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = set()
        self.active_connections[session_id].add(websocket)
        print(f"[WS] Client connecté: {session_id}")
    
    def disconnect(self, session_id: str, websocket: WebSocket):
        if session_id in self.active_connections:
            self.active_connections[session_id].discard(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
        print(f"[WS] Client déconnecté: {session_id}")
    
    async def broadcast_slots(self, session_id: str, slots: Dict[str, Any], message: str = ""):
        """Envoie les données des slots à tous les clients WebSocket connectés"""
        if session_id in self.active_connections:
            payload = {
                "slots": slots,
                "message": message or "Formulaire mis à jour"
            }
            disconnected = set()
            for connection in self.active_connections[session_id]:
                try:
                    await connection.send_json(payload)
                except Exception as e:
                    print(f"[WS] Erreur envoi: {e}")
                    disconnected.add(connection)
            
            # Nettoyage des connexions mortes
            for conn in disconnected:
                self.active_connections[session_id].discard(conn)

manager = ConnectionManager()

# Montage des fichiers statiques (HTML, CSS, JS)
static_dir = os.path.join(os.path.dirname(__file__), "..")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    print(f"[INFO] Fichiers statiques montés depuis: {static_dir}")

nlu = NLU()
sessions = SessionStore()
dialog = DialogManager(sessions)
asr  = ASRModule(model_size="medium")
db = DatabaseMongo()

class ParseRequest(BaseModel):
    text: str
    lang: Optional[str] = "fr"
    session_id: Optional[str] = None

class ParseResponse(BaseModel):
    intent: str
    confidence: float
    entities: Dict[str, Any]

class RespondResponse(BaseModel):
    text: str
    actions: Dict[str, Any]
    session_id: str


class RespondRequest(BaseModel):
    text: str
    lang: Optional[str] = "fr"
    session_id: Optional[str] = None
    user_name: Optional[str] = None  # Nom reconnu par la caméra
    user_role: Optional[str] = None   # Rôle de l'utilisateur (coach, admin, etc.)


class Creneau(BaseModel):
    jour: str
    heure_debut: str
    heure_fin: str

class ReservationRequest(BaseModel):
    utilisateur_id: str 
    salle: str
    creneau: Creneau

class NLUCorrectionItem(BaseModel):
    original_text: str
    predicted_intent: str
    corrected_intent: Optional[str] = None
    corrected_entities: Optional[Dict[str, Any]] = None

class SurveySubmitRequest(BaseModel):
    session_id: str
    ease_of_use: int  # 1-5
    response_quality: int  # 1-5
    interaction_comfort: int  # 1-5
    additional_comments: Optional[str] = None
    nlu_corrections: Optional[list[NLUCorrectionItem]] = []



@app.get("/")
def root():
    """Page d'accueil du serveur"""
    return {
        "title": "Serveur de dialogue - Robot d'accueil",
        "version": "1.0",
        "endpoints": {
            "ASR": "/v1/asr",
            "Parse": "/v1/parse",
            "Respond": "/v1/respond",
            "Navigation Map": "/carte_navigation.html",
            "Satisfaction Survey": "/satisfaction.html",
            "Reservation": "/reservation.html",
            "WebSocket": "/ws/reservation/{session_id}"
        }
    }


@app.api_route("/reservation.html", methods=["GET", "HEAD"])
async def get_reservation_page(request: Request):
    """Retourne la page HTML de réservation"""
    reservation_path = os.path.join(os.path.dirname(__file__), "..", "reservation.html")
    if not os.path.exists(reservation_path):
        raise HTTPException(status_code=404, detail="reservation.html not found")
    
    try:
        with open(reservation_path, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.api_route("/satisfaction.html", methods=["GET", "HEAD"])
async def get_satisfaction_page(request: Request):
    """Retourne la page HTML du questionnaire de satisfaction"""
    satisfaction_path = os.path.join(os.path.dirname(__file__), "..", "satisfaction.html")
    if not os.path.exists(satisfaction_path):
        raise HTTPException(status_code=404, detail="satisfaction.html not found")
    
    try:
        with open(satisfaction_path, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.api_route("/carte_navigation.html", methods=["GET", "HEAD"])
async def get_navigation_map_page(request: Request):
    """Retourne la page HTML de la carte de navigation"""
    carte_path = os.path.join(os.path.dirname(__file__), "..", "carte_navigation.html")
    if not os.path.exists(carte_path):
        raise HTTPException(status_code=404, detail="carte_navigation.html not found")
    
    try:
        with open(carte_path, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/asr")
async def transcribe_audio(file: UploadFile = File(...)):
    """ Endpoint pour envoyer l'audio Pepper et renvoyer le texte transcrit """
    temp_path = f"temp_{file.filename}"
    print(f"\n[DEBUG] Requête ASR reçue. Fichier: {file.filename}")

    try :
        #1 Sauvegarde temporaire du flix audio reçu
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Vérification de la taille après écriture
        file_size = os.path.getsize(temp_path)
        print(f"[DEBUG] Fichier sauvegardé: {temp_path} | Taille: {file_size} octets")

        if file_size < 100:
            print("[WARNING] Fichier reçu extrêmement petit, risque de corruption.")

        #Transcription via Faster-Whisper (GPU)
        result = asr.process_audio(temp_path)

        if "error" in result:
            print(f"[ERROR] Erreur retournée par asr.process_audio: {result['error']}")
            raise HTTPException(status_code=500, detail=result["error"])

        return result

    except Exception as e:
        print(f"[CRITICAL] Crash serveur ASR: {str(e)}")
        import traceback
        traceback.print_exc() # Affiche la stacktrace complète dans le terminal
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.post("/v1/verify", response_model=VerifyResponse)
def verify(image: UploadFile = File(...)):
    return verify_endpoint(image)

@app.post("/v1/parse", response_model=ParseResponse)
def parse(req: ParseRequest):
    result = nlu.parse(req.text, req.lang or "fr")
    return ParseResponse(intent=result["intent"], confidence=result["confidence"], entities=result["entities"])
@app.post("/v1/parse_all_inents", response_model=Dict[str, Any])
def parse_all_intents(req: ParseRequest):
    return nlu.parse_intents_confidences(req.text, req.lang or "fr")

@app.post("/v1/respond", response_model=RespondResponse)
async def respond(req: RespondRequest):
    print(f"\n[RESPOND] Nouvelle requête de dialogue")
    print(f"[RESPOND] Données reçues: {req.dict()}")
    print(f"[RESPOND] Session ID recue: {req.session_id}")
    
    session_id = req.session_id or sessions.create_session()
    print(f"[RESPOND] Session ID utilisée: {session_id}")
    print(f"[RESPOND] Texte: {req.text}")
    
    parse_result = nlu.parse(req.text, req.lang or "fr")
    print(f"[RESPOND] NLU Résultat: intent={parse_result['intent']}, confidence={parse_result['confidence']}")

    # Charger la session existante
    session_data = sessions.get(session_id)
    
    # --- GESTION DU USER_NAME ET ROLE ---
    # Priorité: 1) Reconnaissance faciale (req.user_name) 2) Session sauvegardée
    if req.user_name:
        # Nouvelle reconnaissance faciale
        parse_result["user_name"] = req.user_name
        session_data["user_name"] = req.user_name  # SAUVEGARDER !
        print(f"[RESPOND] ✓ Reconnaissance faciale: {req.user_name}")
    elif session_data.get("user_name"):
        # Utiliser l'utilisateur déjà reconnu dans la session
        parse_result["user_name"] = session_data["user_name"]
        print(f"[RESPOND] ✓ Utilisateur reconnu (sauvegardé): {session_data['user_name']}")
    
    if req.user_role:
        parse_result["user_role"] = req.user_role
        session_data["user_role"] = req.user_role
    elif session_data.get("user_role"):
        parse_result["user_role"] = session_data["user_role"]
    
    # Sauvegarder la session avec le user_name persistant
    sessions.update(session_id, session_data)
    
    booking_in_progress = "booking_slots" in session_data
    # if parse_result["intent"] == "unknown" and not booking_in_progress:
    #     response_text = "Désolé, je n'ai pas compris votre demande. Pouvez-vous reformuler ?"
    #     return RespondResponse(text=response_text, actions={}, session_id=session_id)

    try:
        response_text, actions = dialog.handle(session_id, parse_result, lang=req.lang or "fr")
        print(f"[RESPOND] Dialog réponse: {response_text}")
        print(f"[RESPOND] Actions: {actions}")
    except Exception as e:
        print(f"[RESPOND] ✗ ERREUR Dialog: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
    # Envoyer les slots mis à jour au frontend via WebSocket (TOUJOURS, pas seulement s'il y en a)
    try:
        updated_session = sessions.get(session_id)
        booking_slots = updated_session.get("booking_slots", {})
        print(f"[RESPOND] Slots dans la session: {booking_slots}")
        
        # Ajouter les informations utilisateur
        if req.user_name:
            booking_slots["user_name"] = req.user_name
        
        print(f"[WEBSOCKET] Envoi des slots via broadcast_slots:")
        print(f"  - Session ID: {session_id}")
        print(f"  - Slots: {booking_slots}")
        
        # Envoyer les slots même s'il y en a aucun (pour synchroniser le frontend)
        await manager.broadcast_slots(session_id, booking_slots, message="Mise à jour du formulaire")
        print(f"[WEBSOCKET] ✓ Slots envoyés au frontend avec succès")
        
    except Exception as e:
        print(f"[RESPOND] ✗ Erreur envoi slots WebSocket: {e}")
        import traceback
        traceback.print_exc()
    
    return RespondResponse(text=response_text, actions=actions, session_id=session_id)

@app.get("/v1/session/{session_id}/reset")
def reset_session(session_id: str):
    """Réinitialise une session pour mode veille: nettoie user_name, slots, historique"""
    ok = sessions.reset(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="session not found")
    return {"status": "ok", "session_id": session_id, "message": "Mode veille activé - utilisateur oublié"}


@app.post("/v1/sleep_mode")
def sleep_mode(session_id: Optional[str] = None):
    """
    Entre en mode veille: réinitialise complètement la session (user_name, rôle, réservation, etc.)
    Usage: POST /v1/sleep_mode?session_id=xyz
    """
    if not session_id:
        return {"status": "error", "message": "session_id requis en paramètre"}
    
    ok = sessions.reset(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="session not found")
    
    return {
        "status": "ok", 
        "session_id": session_id,
        "message": "Mode veille activé",
        "user_cleared": True,
        "ready_for_next_user": True
    }


@app.get("/v1/session/{session_id}/slots")
def get_session_slots(session_id: str):
    """Récupère les slots de réservation actuels pour une session"""
    try:
        session_data = sessions.get(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="session not found")
        
        booking_slots = session_data.get("booking_slots", {})
        return {
            "session_id": session_id,
            "slots": booking_slots,
            "in_progress": bool(booking_slots)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/reserver_salle")
def reserver_salle_endpoint(req: ReservationRequest):
    try:
        reservation_id = reserver_salle(req.dict())
        return {"status": "success", "reservation_id": str(reservation_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/cancel_reservation/{reservation_id}")
def cancel_reservation_endpoint(reservation_id: str, user_name: Optional[str] = None):
    """Annule une réservation par son ID"""
    from bson import ObjectId
    try:
        # Vérifier que la réservation appartient à l'utilisateur (optionnel mais recommandé)
        reservation = db.get_collection("reservations").find_one({"_id": ObjectId(reservation_id)})
        
        if not reservation:
            raise HTTPException(status_code=404, detail="Réservation non trouvée")
        
        # Vérifier l'utilisateur si fourni
        if user_name and reservation.get("user_name") != user_name:
            raise HTTPException(status_code=403, detail="Vous n'avez pas accès à cette réservation")
        
        # Vérifier que la réservation n'est pas déjà annulée
        if reservation.get("statut") == "annulee":
            raise HTTPException(status_code=400, detail="Cette réservation est déjà annulée")
        
        # Effectuer l'annulation
        result = db.get_collection("reservations").update_one(
            {"_id": ObjectId(reservation_id)},
            {"$set": {"statut": "annulee", "date_annulation": datetime.now()}}
        )
        
        if result.modified_count > 0:
            return {
                "status": "success",
                "message": "Réservation annulée avec succès",
                "reservation_id": reservation_id
            }
        else:
            raise HTTPException(status_code=500, detail="Erreur lors de l'annulation")
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Erreur annulation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/nlu-metadata")
def get_nlu_metadata():
    """
    Récupère les intentions disponibles avec leurs descriptions
    et les types d'entités possibles pour le formulaire de satisfaction
    """
    try:
        # Récupérer les intentions depuis NLU
        intent_map = nlu._INTENT_MAP
        # Extraire les valeurs uniques (les intentions API)
        api_intents = sorted(set(intent_map.values()))
        
        # Mapping des intentions vers leurs descriptions
        intent_descriptions = {
            "greeting": "Saluer le robot",
            "ask_hours": "Demander les horaires",
            "ask_activities": "Demander les activités",
            "navigate": "Demander la navigation",
            "book_activity": "Réserver une activité",
            "who_are_you": "Qui es-tu?",
            "ask_available_slots": "Demander les créneaux disponibles",
            "ask_my_reservations": "Demander mes réservations",
            "ask_pricing": "Demander les tarifs",
            "cancel_booking": "Annuler une réservation",
            "ask_registered_activity_schedule": "Demander l'horaire de mon activité",
            "ask_special_events": "Demander les événements spéciaux",
            "unknown": "Intention inconnue"
        }
        
        intents_list = []
        for intent in api_intents:
            description = intent_descriptions.get(intent, intent.replace("_", " ").capitalize())
            intents_list.append({
                "value": intent,
                "label": description
            })
        
        # Types d'entités correctes
        entity_types = [
            {"value": "SPORT", "label": "Sport"},
            {"value": "LIEU", "label": "Lieu"},
            {"value": "DATE", "label": "Date"},
            {"value": "HEURE", "label": "Heure"},
            {"value": "NOMBRE", "label": "Nombre"}
        ]
        
        return {
            "intents": intents_list,
            "entity_types": entity_types
        }
    except Exception as e:
        print(f"[ERROR] Erreur retrieval NLU metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/survey/submit")
def submit_survey(req: SurveySubmitRequest):
    """
    Endpoint pour soumettre le questionnaire de satisfaction post-session.
    
    Valide les scores Likert (1-5), enregistre les corrections NLU,
    stocke tout dans MongoDB et ferme la session proprement.
    """
    try:
        # Validation des scores
        if not (1 <= req.ease_of_use <= 5):
            raise HTTPException(status_code=400, detail="ease_of_use doit être entre 1 et 5")
        if not (1 <= req.response_quality <= 5):
            raise HTTPException(status_code=400, detail="response_quality doit être entre 1 et 5")
        if not (1 <= req.interaction_comfort <= 5):
            raise HTTPException(status_code=400, detail="interaction_comfort doit être entre 1 et 5")
        
        # Préparer les corrections NLU
        nlu_corrections = []
        if req.nlu_corrections:
            for correction in req.nlu_corrections:
                nlu_corrections.append({
                    "original_text": correction.original_text,
                    "predicted_intent": correction.predicted_intent,
                    "corrected_intent": correction.corrected_intent or correction.predicted_intent,
                    "corrected_entities": correction.corrected_entities or {}
                })
        
        # Préparer les données de feedback
        feedback_data = {
            "ease_of_use": req.ease_of_use,
            "response_quality": req.response_quality,
            "interaction_comfort": req.interaction_comfort,
            "additional_comments": req.additional_comments or "",
            "nlu_corrections": nlu_corrections
        }
        
        # Enregistrer le feedback
        success = dialog.record_satisfaction_feedback(req.session_id, feedback_data)
        
        if not success:
            raise HTTPException(status_code=500, detail="Erreur lors de l'enregistrement du questionnaire")
        
        # Réinitialiser la session pour le prochain utilisateur
        sessions.reset(req.session_id)
        
        return {
            "status": "success",
            "message": "Questionnaire enregistré avec succès",
            "session_id": req.session_id,
            "session_reset": True,
            "ready_for_next_user": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Erreur lors de la soumission du questionnaire: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/session/{session_id}/history")
def get_session_history(session_id: str):
    """Récupère l'historique de conversation pour affichage dans le formulaire de satisfaction"""
    try:
        session_data = sessions.get(session_id)
        if not session_data:
            # Retourner une liste vide au lieu de 404
            return {
                "session_id": session_id,
                "history": [],
                "turn_count": 0
            }
        
        history = session_data.get("history", [])
        
        # Formater l'historique pour le frontend
        formatted_history = []
        for msg in history:
            formatted_history.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
                "timestamp": msg.get("timestamp", datetime.now().isoformat())
            })
        
        return {
            "session_id": session_id,
            "history": formatted_history,
            "turn_count": len([m for m in history if m.get("role") == "user"])
        }
    except Exception as e:
        print(f"[ERROR] Erreur retrieval conversation history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/session/{session_id}/nlu-data")
def get_session_nlu_data(session_id: str):
    """
    Récupère les données NLU (intents prédits) pour chaque énoncé utilisateur
    pour affichage dans le formulaire de satisfaction
    """
    try:
        session_data = sessions.get(session_id)
        if not session_data:
            # Retourner une liste vide au lieu de 404
            return {
                "session_id": session_id,
                "nlu_items": [],
                "total_items": 0
            }
        
        history = session_data.get("history", [])
        nlu_items = session_data.get("nlu_log", [])  # Log NLU stocké dans la session
        
        # Si pas de log NLU, créer à partir de l'historique
        if not nlu_items and history:
            nlu_items = []
            for msg in history:
                if msg.get("role") == "user":
                    # Récupérer l'intent associé (si disponible dans metadata)
                    nlu_items.append({
                        "original_text": msg.get("content", ""),
                        "predicted_intent": msg.get("intent", "unknown"),
                        "entities": msg.get("entities", {})
                    })
        
        return {
            "session_id": session_id,
            "nlu_items": nlu_items,
            "total_items": len(nlu_items)
        }
    except Exception as e:
        print(f"[ERROR] Erreur retrieval NLU data: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@app.websocket("/ws/reservation/{session_id}")
async def websocket_reservation(websocket: WebSocket, session_id: str):
    """
    WebSocket pour la synchronisation des slots de réservation.
    Le frontend se connecte à cet endpoint pour recevoir les mises à jour en temps réel.
    """
    await manager.connect(session_id, websocket)
    
    try:
        # Envoyer les slots actuels au client dès la connexion
        session_data = sessions.get(session_id)
        booking_slots = session_data.get("booking_slots", {})
        if booking_slots:
            await websocket.send_json({
                "slots": booking_slots,
                "message": "Connexion établie - chargement des données"
            })
        else:
            await websocket.send_json({
                "slots": {},
                "message": "Connexion établie"
            })
        
        # Garder la connexion ouverte et écouter les messages
        while True:
            data = await websocket.receive_text()
            print(f"[WS] Message reçu de {session_id}: {data}")
            # On peut traiter d'autres types de messages si nécessaire
            
    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)
    except Exception as e:
        print(f"[WS] Erreur: {e}")
        manager.disconnect(session_id, websocket)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=True)