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

from app.nlu import NLU
from app.dialog_manager import DialogManager
from app.sessions import SessionStore
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
    user_name: Optional[str] = None  # Nouveau champ : nom reconnu par la caméra


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
    # result = nlu.parse(req.text, req.lang)
    result = nlu.parse(req.text)
    return ParseResponse(intent=result["intent"], confidence=result["confidence"], entities=result["entities"])
@app.post("/v1/parse_all_inents", response_model=Dict[str, Any])
def parse_all_intents(req: ParseRequest):
    result = nlu.parse_intents_confidences(req.text)
    return result

@app.post("/v1/respond", response_model=RespondResponse)
async def respond(req: RespondRequest):
    print(f"[DEBUG] Session ID recue du client: {req.session_id}")
    session_id = req.session_id or sessions.create_session()
    print(f"[DEBUG] Session ID utilisee: {session_id}")
    parse_result = nlu.parse(req.text)

    # Injecter le nom dans le parse_result si fourni
    if req.user_name:
        parse_result["user_name"] = req.user_name

    session_data = sessions.get(session_id)
    booking_in_progress = "booking_slots" in session_data
    if parse_result["intent"] == "unknown" and not booking_in_progress:
        response_text = "Désolé, je n'ai pas compris votre demande. Pouvez-vous reformuler ?"
        return RespondResponse(text=response_text, actions={}, session_id=session_id)

    try:
        response_text, actions = dialog.handle(session_id, parse_result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    # Envoyer les slots mis à jour au frontend via WebSocket
    try:
        updated_session = sessions.get(session_id)
        booking_slots = updated_session.get("booking_slots", {})
        if booking_slots:
            # Ajouter les informations utilisateur
            if req.user_name:
                booking_slots["user_name"] = req.user_name
            await manager.broadcast_slots(session_id, booking_slots)
            print(f"[DEBUG] Slots envoyés au frontend: {booking_slots}")
    except Exception as e:
        print(f"[DEBUG] Erreur envoi slots WebSocket: {e}")
    
    return RespondResponse(text=response_text, actions=actions, session_id=session_id)

@app.get("/v1/session/{session_id}/reset")
def reset_session(session_id: str):
    ok = sessions.reset(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="session not found")
    return {"status": "ok", "session_id": session_id}


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
        reservation_id = reserver_salle(req.model_dump())
        return {"status": "success", "reservation_id": str(reservation_id)}
    except Exception as e:
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