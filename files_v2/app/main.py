from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional, Dict, Any
import uvicorn
import shutil
import os

from app.nlu import NLU
from app.dialog_manager import DialogManager
from app.sessions import SessionStore
from app.speech import ASRModule


app = FastAPI(title="Serveur de dialogue - Robot d'accueil")

nlu = NLU()
sessions = SessionStore()
dialog = DialogManager(sessions)
asr  = ASRModule(model_size="small")
class ParseRequest(BaseModel):
    text: str
    lang: Optional[str] = "fr"
    session_id: Optional[str] = None

class ParseResponse(BaseModel):
    intent: str
    confidence: float
    entities: Dict[str, Any]

class RespondRequest(BaseModel):
    text: str
    lang: Optional[str] = "fr"
    session_id: Optional[str] = None

class RespondResponse(BaseModel):
    text: str
    actions: Dict[str, Any]
    session_id: str

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


@app.post("/v1/parse", response_model=ParseResponse)
def parse(req: ParseRequest):
    # result = nlu.parse(req.text, req.lang)
    result = nlu.parse(req.text)
    return ParseResponse(intent=result["intent"], confidence=result["confidence"], entities=result["entities"])

@app.post("/v1/respond", response_model=RespondResponse)
def respond(req: RespondRequest):
    # ensure session
    print(f"[DEBUG] Session ID recue du client: {req.session_id}")
    session_id = req.session_id or sessions.create_session()
    print(f"[DEBUG] Session ID utilisee: {session_id}")
    # parse_result = nlu.parse(req.text, req.lang)
    parse_result = nlu.parse(req.text)
    
    try:
        response_text, actions = dialog.handle(session_id, parse_result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return RespondResponse(text=response_text, actions=actions, session_id=session_id)

@app.get("/v1/session/{session_id}/reset")
def reset_session(session_id: str):
    ok = sessions.reset(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="session not found")
    return {"status": "ok", "session_id": session_id}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)