from fastapi import FastAPI, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect
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
            "Reservation": "/reservation.html",
            "WebSocket": "/ws/reservation/{session_id}"
        }
    }


@app.get("/reservation.html")
async def get_reservation_page():
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
        response_text, actions = dialog.handle(session_id, parse_result)
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