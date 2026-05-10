import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env.local"))

# --- Configuration ---
MONGODB_URI = os.getenv("MONGODB_URI") or os.getenv("MONGODB_URL")
if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI is not set. Define it in your .env file.")
MONGODB_DB = os.getenv("MONGODB_DB", "multisport")


class DatabaseMongo:
    def __init__(self) -> None:
        self.client = MongoClient(MONGODB_URI)
        self.db = self.client[MONGODB_DB]
    
    def get_collection(self, collection_name):
        return self.db[collection_name]
    
    def close(self):
        self.client.close()
