import os
from pymongo import MongoClient

# --- Configuration ---
MONGODB_URI = os.getenv(
    "MONGODB_URI",
    "mongodb+srv://byanismci_db_user:ciFm8mSSBfSB6GOh@cluster0.tdoyk6j.mongodb.net/multisport"
)
MONGODB_DB = os.getenv("MONGODB_DB", "multisport")
MONGODB_COLLECTION = os.getenv("MONGODB_COLLECTION", "utilisateurs")

FACE_TOLERANCE = float(os.getenv("FACE_TOLERANCE", "0.6"))
PHOTO_FETCH_TIMEOUT_SECONDS = float(os.getenv("PHOTO_FETCH_TIMEOUT_SECONDS", "5"))
PHOTO_USER_AGENT = os.getenv("PHOTO_USER_AGENT", "FaceVerificationAPI/1.0")


class DatabaseConnection:
    """Gère la connexion MongoDB."""
    _client = None

    @classmethod
    def get_client(cls):
        if cls._client is None:
            cls._client = MongoClient(MONGODB_URI)
        return cls._client

    @classmethod
    def get_collection(cls):
        client = cls.get_client()
        return client[MONGODB_DB][MONGODB_COLLECTION]

    @classmethod
    def close(cls):
        if cls._client:
            cls._client.close()
            cls._client = None
