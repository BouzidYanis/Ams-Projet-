from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import PyMongoError
import time
import uuid
from .DB_access import DatabaseMongo


class SessionStoreMongo:
    def __init__(self, ttl_seconds=3600):
        self.db = DatabaseMongo()
        self.collection = self.db.get_collection("sessions")
        self.ttl = ttl_seconds

        # TTL index sur last_touched pour nettoyer automatiquement les sessions anciennes.
        self.collection.create_index(
            [("last_touched", ASCENDING)],
            expireAfterSeconds=self.ttl
        )

    def create_session(self):
        sid = str(uuid.uuid4())
        now = time.time()
        session_doc = {
            "_id": sid,
            "created_at": now,
            "last_intent": None,
            "fallbacks": 0,
            "status": "active",
            "last_touched": now,
        }
        try:
            self.collection.insert_one(session_doc)
        except PyMongoError as e:
            print(f"Erreur création session: {e}")
            return None
        return sid

    def get(self, session_id):
        now = time.time()
        session = self.collection.find_one_and_update(
            {"_id": session_id},
            {"$set": {"last_touched": now}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

        # Si la session n'existait pas encore, upsert la crée avec des champs minimaux.
        if not session:
            self.collection.update_one(
                {"_id": session_id},
                {
                    "$set": {
                        "created_at": now,
                        "last_intent": None,
                        "fallbacks": 0,
                        "status": "active",
                        "last_touched": now,
                    }
                },
                upsert=True,
            )
            session = self.collection.find_one({"_id": session_id})

        return session

    def update(self, session_id, data):
        data = dict(data or {})
        data["last_touched"] = time.time()
        result = self.collection.update_one(
            {"_id": session_id},
            {"$set": data},
            upsert=True,
        )
        return result.modified_count > 0 or result.upserted_id is not None

    def mark_sleep(self, session_id, user_name=None):
        now = time.time()
        session = self.get(session_id)
        if not session:
            return False

        if user_name:
            session["user_name"] = user_name

        session["status"] = "sleep"
        session["sleep_at"] = now
        session["last_touched"] = now
        result = self.collection.update_one(
            {"_id": session_id},
            {"$set": session},
            upsert=True,
        )
        return result.modified_count > 0 or result.upserted_id is not None

    def reset(self, session_id):
        now = time.time()
        result = self.collection.update_one(
            {"_id": session_id},
            {
                "$set": {
                    "created_at": now,
                    "last_intent": None,
                    "fallbacks": 0,
                    "status": "active",
                    "last_touched": now,
                }
            },
            upsert=True,
        )
        return result.modified_count > 0 or result.upserted_id is not None

    def cleanup(self):
        # Optionnel: MongoDB gère déjà la suppression via l'index TTL.
        expire_before = time.time() - self.ttl
        result = self.collection.delete_many({"last_touched": {"$lt": expire_before}})
        print(f"Nettoyage automatique : {result.deleted_count} sessions supprimées")