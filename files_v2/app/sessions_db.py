from pymongo import MongoClient, ASCENDING
from pymongo.errors import PyMongoError
import time
import uuid

class SessionStoreMongo:
    def __init__(self, mongo_uri="mongodb://localhost:27017/", db_name="pepperdb", collection_name="sessions", ttl_seconds=3600):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]
        self.ttl = ttl_seconds
        
        # Index TTL sur le champ 'last_touched' pour nettoyage automatique
        # Mongo supprime automatiquement les documents dont 'last_touched' est trop vieux
        self.collection.create_index(
            [("last_touched", ASCENDING)],
            expireAfterSeconds=self.ttl
        )

    def create_session(self) -> str:
        sid = str(uuid.uuid4())
        now = time.time()
        session_doc = {
            "_id": sid,
            "created_at": now,
            "last_intent": None,
            "fallbacks": 0,
            "last_touched": now
        }
        try:
            self.collection.insert_one(session_doc)
        except PyMongoError as e:
            print(f"Erreur création session: {e}")
            return None
        return sid

    def get(self, session_id: str) -> dict:
        now = time.time()
        session = self.collection.find_one_and_update(
            {"_id": session_id},
            {"$set": {"last_touched": now}},
            upsert=True,
            return_document=True
        )
        # Si la session n'existait pas, upsert=True la crée sans les champs par défaut, on corrige ça:
        if not session:
            # Création explicite avec champs par défaut
            self.collection.update_one(
                {"_id": session_id},
                {"$set": {
                    "created_at": now,
                    "last_intent": None,
                    "fallbacks": 0,
                    "last_touched": now
                }},
                upsert=True
            )
            session = self.collection.find_one({"_id": session_id})
        return session

    def update(self, session_id: str, data: dict) -> bool:
        data["last_touched"] = time.time()
        result = self.collection.update_one(
            {"_id": session_id},
            {"$set": data},
            upsert=True
        )
        return result.modified_count > 0 or result.upserted_id is not None

    def reset(self, session_id: str) -> bool:
        now = time.time()
        result = self.collection.update_one(
            {"_id": session_id},
            {"$set": {
                "created_at": now,
                "last_intent": None,
                "fallbacks": 0,
                "last_touched": now
            }}
        )
        return result.modified_count > 0

    def cleanup(self):
        # Cette fonction est optionnelle car MongoDB supprime automatiquement grâce à TTL index
        expire_before = time.time() - self.ttl
        result = self.collection.delete_many({"last_touched": {"$lt": expire_before}})
        print(f"Nettoyage automatique : {result.deleted_count} sessions supprimées")