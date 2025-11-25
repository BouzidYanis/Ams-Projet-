from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import uvicorn
from app.nlu import NLU
from app.dialog_manager import DialogManager
from app.sessions import SessionStore

app = FastAPI(title="Serveur de dialogue - Robot d'accueil")

nlu = NLU()
sessions = SessionStore()
dialog = DialogManager(sessions)

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

@app.post("/v1/parse", response_model=ParseResponse)
def parse(req: ParseRequest):
    result = nlu.parse(req.text, req.lang)
    return ParseResponse(intent=result["intent"], confidence=result["confidence"], entities=result["entities"])

@app.post("/v1/respond", response_model=RespondResponse)
def respond(req: RespondRequest):
    # ensure session
    session_id = req.session_id or sessions.create_session()
    parse_result = nlu.parse(req.text, req.lang)
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