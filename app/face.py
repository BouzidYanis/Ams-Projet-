import os
import io
from typing import List, Optional, Tuple

import numpy as np
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import face_recognition
from pymongo import MongoClient

# --- NEW: for fetching images by URL ---
from urllib.request import Request, urlopen
from urllib.parse import urlparse

# --- Configuration (env) ---
MONGODB_URI = "mongodb+srv://byanismci_db_user:ciFm8mSSBfSB6GOh@cluster0.tdoyk6j.mongodb.net/multisport"
MONGODB_DB = "multisport"
MONGODB_COLLECTION = "utilisateurs"

# Seuil par défaut de face_recognition.compare_faces = 0.6
FACE_TOLERANCE = float(os.getenv("FACE_TOLERANCE", "0.6"))

# --- NEW: config for remote photo fetching ---
PHOTO_FETCH_TIMEOUT_SECONDS = float(os.getenv("PHOTO_FETCH_TIMEOUT_SECONDS", "5"))
PHOTO_USER_AGENT = os.getenv("PHOTO_USER_AGENT", "FaceVerificationAPI/1.0")

app = FastAPI(title="Face Verification API")


class Match(BaseModel):
    id: str
    distance: float
    nom: Optional[str] = None
    prenom: Optional[str] = None


class VerifyResponse(BaseModel):
    matched: bool
    best_match: Optional[Match] = None
    candidates_checked: int


def _get_collection():
    client = MongoClient(MONGODB_URI)
    return client[MONGODB_DB][MONGODB_COLLECTION]


def _load_image_from_upload(upload: UploadFile):
    content = upload.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Image vide")
    try:
        # face_recognition (PIL) supporte un file-like
        return face_recognition.load_image_file(io.BytesIO(content))
    except Exception:
        raise HTTPException(status_code=400, detail="Format d'image invalide")


def _load_image_from_photo_ref(ref: str) -> np.ndarray:
    """Charge une image depuis une référence `photo`.

    - URL http(s): téléchargée
    - Chemin local: lu depuis le disque
    """
    if not ref or not isinstance(ref, str):
        raise ValueError("Référence photo invalide")

    parsed = urlparse(ref)
    if parsed.scheme in ("http", "https"):
        req = Request(ref, headers={"User-Agent": PHOTO_USER_AGENT})
        with urlopen(req, timeout=PHOTO_FETCH_TIMEOUT_SECONDS) as resp:
            content = resp.read()
        if not content:
            raise ValueError("Image distante vide")
        return face_recognition.load_image_file(io.BytesIO(content))

    # Sinon, on considère un chemin local
    if not os.path.exists(ref):
        raise FileNotFoundError(f"Photo introuvable: {ref}")
    return face_recognition.load_image_file(ref)


def _encode_first_face(image: np.ndarray) -> np.ndarray:
    encodings = face_recognition.face_encodings(image)
    if not encodings:
        raise HTTPException(status_code=422, detail="Aucun visage détecté dans l'image")
    return encodings[0]


def _best_match(
    known: List[Tuple[str, np.ndarray, Optional[str], Optional[str]]],
    unknown_encoding: np.ndarray,
) -> Optional[Match]:
    if not known:
        return None

    ids = [kid for kid, *_ in known]
    encs = [kenc for _, kenc, *_ in known]

    distances = face_recognition.face_distance(encs, unknown_encoding)
    best_idx = int(np.argmin(distances))
    best_distance = float(distances[best_idx])

    if best_distance <= FACE_TOLERANCE:
        best_id, _, best_nom, best_prenom = known[best_idx]
        return Match(id=best_id, distance=best_distance, nom=best_nom, prenom=best_prenom)
    return None


@app.post("/verify", response_model=VerifyResponse)
def verify(image: UploadFile = File(...)):
    # 1) Encoder l'image envoyée
    img = _load_image_from_upload(image)
    unknown_encoding = _encode_first_face(img)

    # 2) Charger uniquement le lien 'photo' depuis MongoDB
    col = _get_collection()
    cursor = col.find({}, {"photo": 1, "nom": 1, "prenom": 1})

    known: List[Tuple[str, np.ndarray, Optional[str], Optional[str]]] = []
    checked = 0
    skipped = 0

    for doc in cursor:
        checked += 1
        doc_id = str(doc.get("_id"))
        photo_ref = doc.get("photo")
        nom = doc.get("nom")
        prenom = doc.get("prenom")
        if not photo_ref:
            skipped += 1
            continue
        try:
            ref_img = _load_image_from_photo_ref(photo_ref)
            # Pour les photos de référence, si pas de visage, on ignore juste
            encodings = face_recognition.face_encodings(ref_img)
            if not encodings:
                skipped += 1
                continue
            ref_enc = encodings[0]
            if ref_enc.shape[0] == 128:
                known.append((doc_id, ref_enc, nom, prenom))
            else:
                skipped += 1
        except Exception:
            skipped += 1
            continue

    if not known:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Aucune photo exploitable trouvée dans MongoDB. "
                f"Docs analysés: {checked}, ignorés: {skipped}. "
                "Vérifiez que le champ 'photo' contient une URL http(s) ou un chemin local existant, "
                "et que l'image contient un visage."
            ),
        )

    # 3) Comparer et renvoyer le meilleur match
    best = _best_match(known, unknown_encoding)

    return VerifyResponse(
        matched=best is not None,
        best_match=best,
        candidates_checked=checked,
    )


@app.get("/health")
def health():
    return JSONResponse({"status": "ok"})
