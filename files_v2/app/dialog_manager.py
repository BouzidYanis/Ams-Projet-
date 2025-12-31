"""
app/dialog_manager.py
Dialog manager that uses LLMClient to generate assistant replies and
maintains per-session message history (user/assistant).
Falls back to simple rule-based replies if LLM fails.
"""
from typing import Tuple, Dict, Any, List
from app.sessions import SessionStore
from app.llm import LLMClient, LLMError
import os
import json
import random

DEFAULT_SYSTEM_PROMPT = (
    "Tu es l'assistant conversationnel d'un robot d'accueil dans une salle multisports. "
    "Tu dois TOUJOURS répondre en français, de façon polie, chaleureuse, concise et utile. "
    "Tu peux aider pour : informations (horaires, tarifs, activités), orientation dans le bâtiment "
    "(vestiaires, terrains, salle de musculation, piscine, etc.), inscriptions et réservations. "
    "Si l'utilisateur demande une réservation, demande toujours l'activité précise et le créneau "
    "si ces informations sont manquantes. "
    "Si la question est très simple (par exemple juste 'bonjour'), réponds par un message de bienvenue "
    "en expliquant clairement ce que tu peux faire pour l'utilisateur. "
    "Ne donne jamais d'informations personnelles sur d'autres personnes. "
    "Si tu ne comprends pas, demande une clarification courte."
)


# Simple rule-based fallback (kept minimal)
RULES = {
    "greeting": [
        "Bonjour ! Je peux vous aider pour les horaires, les inscriptions, les réservations ou pour vous orienter. Que souhaitez‑vous ?",
        "Salut ! Comment puis-je vous aider aujourd'hui ?",
        "Bonjour ! En quoi puis-je vous être utile pour votre visite à la salle multisports ?"
    ],
    "ask_hours": "La salle est ouverte du lundi au vendredi de 8h à 22h, et le weekend de 9h à 18h.",
    "ask_activities": "Nous proposons fitness, basket, natation, tennis, futsal et yoga. Laquelle vous intéresse ?",
}

llm_openai = "llm_openai_config.json"

class DialogManager:
    def __init__(self, sessions: SessionStore, llm_config_path: str = None):
        self.sessions = sessions
        cfg_path = llm_config_path or os.path.join(os.path.dirname(__file__), "..", "configs", llm_openai)
        self.llm = LLMClient(cfg_path)
        # system prompt can be overridden in config file (optional)
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                self.system_prompt = cfg.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
        except Exception:
            self.system_prompt = DEFAULT_SYSTEM_PROMPT

    def _append_message(self, session_id: str, role: str, content: str) -> None:
        session = self.sessions.get(session_id)
        history = session.setdefault("history", [])
        history.append({"role": role, "content": content})
        # limit history length to avoid huge prompts (keep last N pairs)
        max_msgs = 20
        if len(history) > max_msgs:
            # keep the last max_msgs entries
            session["history"] = history[-max_msgs:]
        self.sessions.update(session_id, session)

    def handle(self, session_id: str, parse_result: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """
        parse_result should contain at least {"intent": str, "entities": {...}} and original text under 'raw_text'
        The robot should pass the user's raw text in parse_result['raw_text'] or we use last user message in session.
        """

        # --- BLOC DE DEBUG AJOUTÉ ---
        print("\n" + "="*40)
        print("[DEBUG DM] Entrée dans handle()")
        print("[DEBUG DM] Session ID: {}".format(session_id))
        print("[DEBUG DM] parse_result complet: {}".format(json.dumps(parse_result, indent=2)))
        # ----------------------------

        intent = parse_result.get("intent", "unknown")
        entities = parse_result.get("entities", {})
        user_text = parse_result.get("raw_text") or parse_result.get("text") or ""
        # store user message in history
        if user_text:
            self._append_message(session_id, "user", user_text)

        session = self.sessions.get(session_id)
        history: List[Dict[str, str]] = session.get("history", [])

        # Try LLM generation
        try:
            print("[DialogManager] calling LLM with intent:", intent)

            # System pront in modelfile for ollama models -> ici on passe une chaîne vide
            # assistant_text = self.llm.generate_chat(self.system_prompt, history)
            assistant_text = self.llm.generate_chat("", history)
            
            
            # append assistant message to history
            self._append_message(session_id, "assistant", assistant_text)
            # Basic post-processing or action extraction can be done here (simple heuristics)
            actions = {}
            # If parse_result intent is book_activity and entities provided, echo action
            if intent == "book_activity":
                activity = entities.get("activity")
                time = entities.get("time")
                if activity and time:
                    # record booking in a simple file-based store (reuse previous mechanism)
                    actions["booking"] = {"activity": activity, "time": time}
            return assistant_text, actions
        except LLMError as e:
            print("[DialogManager] LLMError:", e)
            # fallback to rule-based answers
            rule_val = RULES.get(intent)
            if rule_val:
                # si c'est une liste de phrases, on en choisit une au hasard
                if isinstance(rule_val, list):
                    tmpl = random.choice(rule_val)
                else:
                    tmpl = rule_val

                # appliquer .format si la phrase contient des variables {…}
                if "{" in tmpl:
                    resp = tmpl.format(**entities)
                else:
                    resp = tmpl

                # store fallback assistant reply
                self._append_message(session_id, "assistant", resp)
                return resp, {}

            # default fallback message
            default = "Désolé, le système de dialogue n'est pas disponible pour le moment. Pouvez-vous reformuler ?"
            self._append_message(session_id, "assistant", default)
            return default, {}
        
if __name__ == "__main__":
    import time
    
    # 1. Initialize the storage and manager
    # In production, this persists as long as the robot's process is running
    store = SessionStore(ttl_seconds=3600)
    dm = DialogManager(store)
    
    # 2. Simulate a unique session ID (e.g., generated when a person is detected)
    sid = "robot_session_xyz"
    
    print("--- STEP 1: Initial State ---")
    # This creates the entry in SessionStore
    initial_sid = store.create_session() 
    print("Store after creation:", store.get(initial_sid))

    print("\n--- STEP 2: First Interaction (Greeting) ---")
    # Simulation of what the NLU (Natural Language Understanding) would pass to the manager
    parse_1 = {
        "intent": "greeting",
        "raw_text": "Bonjour, comment tu t'appelles ?"
    }
    
    # The 'handle' method will: 
    #   1. Call _append_message (User) -> updates _store
    #   2. Call LLMClient -> gets response
    #   3. Call _append_message (Assistant) -> updates _store
    response, actions = dm.handle(sid, parse_1)
    
    print("Robot Response:", response)
    print("Updated History:", store.get(sid)["history"])

    print("\n--- STEP 3: Second Interaction (Contextual) ---")
    parse_2 = {
        "intent": "ask_activities",
        "raw_text": "Quelles sont les activités ?"
    }
    dm.handle(sid, parse_2)
    
    # Let's look at the SessionStore one last time
    final_state = store.get(sid)
    print("Final 'history' length:", len(final_state["history"]))
    for turn in final_state["history"]:
        print("  {0}: {1}".format(turn['role'], turn['content']))