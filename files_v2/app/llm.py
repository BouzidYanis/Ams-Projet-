"""
app/llm.py
LLM client wrapper with support for:
 - FastChat-like / OpenAI-compatible chat completions endpoint (/v1/chat/completions)
 - OpenAI officiel (https://api.openai.com/v1/chat/completions)
 - HuggingFace Text-Generation-Inference (TGI) /generate endpoint
 - Google Gemini REST API (v1beta/models/*:generateContent)

Configure which backend to use in configs/llm_config.json.
"""

import requests
from typing import List, Dict, Any
import json
import os
from dotenv import load_dotenv

load_dotenv()
llm_openai = "llm_openai_config.json"
DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "configs", llm_openai)


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        # "fastchat", "hf_tgi", "openai", "gemini"
        self.backend = cfg.get("backend", "fastchat")
        self.endpoint = cfg.get("endpoint", "http://localhost:8000")
        self.model = cfg.get("model", "")
        self.timeout = cfg.get("timeout", 30)
        # optional headers (api keys, etc.). For Gemini, we pass the key in query param, but headers can still be used.
        self.headers = cfg.get("headers", {})
        
        # optional: API key for Gemini (can be in headers or in this field)
        # PRIORITÉ : On regarde d'abord dans le fichier .env, sinon dans le JSON
        env_key = os.getenv("GEMINI_API_KEY")
        if env_key:
            self.api_key = env_key
            # Si ton backend Gemini utilise les headers, on met à jour aussi
            self.headers["x-goog-api-key"] = env_key
        else:
            self.api_key = cfg.get("api_key")
    # ---------- Backends type chat-completions (OpenAI-like) ----------

    def _DEBUG_call_chat_completions(self, messages):
        import time
        import requests
        
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.3
            }
        }
        
        # Correction : on utilise self.endpoint et on s'assure du chemin complet
        # Si ton endpoint est déjà http://localhost:11434/v1, vérifie la concaténation
        url = "{0}/chat/completions".format(self.endpoint.rstrip('/'))
        
        print("\n--- [DEBUG OLLAMA START] ---")
        print("URL cible: {0}".format(url))
        
        start_time = time.time()
        try:
            r = requests.post(url, json=payload, headers=self.headers, timeout=self.timeout)
            duration = time.time() - start_time
            
            print("Status Code: {0} | Time: {1:.2f}s".format(r.status_code, duration))
            
            if r.status_code != 200:
                print("SERVER ERROR BODY: {0}".format(r.text))
                return ""

            data = r.json()
            # On essaie d'extraire le contenu selon le format standard OpenAI/Ollama
            choices = data.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
            else:
                # Fallback si Ollama répond au format direct /api/chat au lieu de /v1
                content = data.get("message", {}).get("content", "")
                
            print("Done Reason: {0}".format(data.get("choices", [{}])[0].get("finish_reason", "unknown")))
            print("Content: '{0}'".format(content))
            print("--- [DEBUG OLLAMA END] ---\n")
            
            return content

        except Exception as e:
            print("!!! CRITICAL EXCEPTION: {0}".format(str(e)))
            return ""
        
    def _call_chat_completions(self, messages: List[Dict[str, str]]) -> str:
        """
        Call an endpoint /v1/chat/completions compatible with OpenAI format.
        Works for:
        - FastChat (self.backend == "fastchat")
        - OpenAI (self.backend == "openai")
        """
        url = self.endpoint.rstrip("/") + "/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "temperature": 0.2,
            "max_tokens": 150
        }
        r = requests.post(url, json=payload, headers=self.headers, timeout=self.timeout)
        if r.status_code != 200:
            raise LLMError(f"Chat-completions call failed: {r.status_code} {r.text}")
        data = r.json()
        try:
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            raise LLMError(f"Unexpected chat-completions response format: {e} - {data}")

    # ---------- HuggingFace TGI /generate ----------

    def _call_hf_tgi(self, prompt: str) -> str:
        """
        Call HuggingFace Text-Generation-Inference /generate endpoint.
        Endpoint example: http://localhost:8080
        Payload example: {"inputs": prompt, "parameters": {"max_new_tokens": 512}}
        """
        url = self.endpoint.rstrip("/") + "/generate"
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 512,
                "temperature": 0.2,
            },
        }
        r = requests.post(url, json=payload, headers=self.headers, timeout=self.timeout)
        if r.status_code != 200:
            raise LLMError(f"HuggingFace TGI call failed: {r.status_code} {r.text}")
        data = r.json()
        try:
            if isinstance(data, list):
                return data[0].get("generated_text", "")
            return data.get("generated_text", "")
        except Exception as e:
            raise LLMError(f"Unexpected HF-TGI response format: {e} - {data}")

    # ---------- Gemini REST API ----------

    def _call_gemini(self, system_prompt: str, history: List[Dict[str, str]]) -> str:
        """
        Call Google Gemini API (REST).

        Expected config:
        - endpoint: "https://generativelanguage.googleapis.com"
        - model: e.g. "gemini-1.5-flash" or "gemini-1.5-pro"
          (the model name will be used in URL: /v1beta/models/{model}:generateContent)
        - api_key: your Gemini API key (string) in config, or in headers["x-goog-api-key"].

        We convert (system + history) into 'contents' as required by Gemini.
        """

        base_url = self.endpoint.rstrip("/")
        model_name = self.model  # e.g., "gemini-1.5-flash"
        url = f"{base_url}/v1beta/models/{model_name}:generateContent"

        # Determine API key location
        api_key = self.api_key or self.headers.get("x-goog-api-key")
        if not api_key:
            raise LLMError("Gemini API key not provided. Set 'api_key' or 'headers.x-goog-api-key' in llm_config.json.")

        params = {"key": api_key}

        # Build contents:
        # We create one content with multiple parts for system + messages
        parts = []
        if system_prompt:
            parts.append({"text": f"SYSTEM: {system_prompt.strip()}"})
        for msg in history:
            role = msg.get("role", "user")
            content_text = msg.get("content", "").strip()
            parts.append({"text": f"{role.upper()}: {content_text}"})

        body = {
            "contents": [
                {
                    "parts": parts
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 2048
            }
        }

        r = requests.post(url, params=params, json=body, headers=self.headers, timeout=self.timeout)
        if r.status_code != 200:
            raise LLMError(f"Gemini call failed: {r.status_code} {r.text}")

        data = r.json()
        try:
            # Typical Gemini response: candidates[0].content.parts[0].text
            candidates = data.get("candidates", [])
            if not candidates:
                raise LLMError(f"No candidates in Gemini response: {data}")
            content = candidates[0].get("content", {})
            parts_out = content.get("parts", [])
            if not parts_out:
                raise LLMError(f"No parts in Gemini candidate: {data}")
            text = parts_out[0].get("text", "")
            return text
        except Exception as e:
            raise LLMError(f"Unexpected Gemini response format: {e} - {data}")

    # ---------- Public API ----------

    def generate_chat(self, system_prompt: str, history: List[Dict[str, str]]) -> str:
        """
        Build an LLM request from system prompt and history and return assistant text.
        """
        # Backends type chat completions (messages[])
        if self.backend in ("fastchat", "openai"):
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            for msg in history:
                messages.append({"role": msg["role"], "content": msg["content"]})
            
            # --- DEBUG 1: CE QUE NOUS ENVOYONS ---
            print(f"\n[LLM DEBUG] Prompt envoyé au backend {self.backend}:")
            for m in messages:
                print(f"  {m['role'].upper()}: {m['content'][:100]}...") # Tronqué pour lisibilité
            
            try:
                # Appel effectif
                response_text = self._DEBUG_call_chat_completions(messages)
                
                # --- DEBUG 2: CE QUE NOUS RECEVONS ---
                print(f"[LLM DEBUG] Réponse brute reçue: '{response_text}'")
                
                return response_text
            except Exception as e:
                print(f"[LLM ERROR] Crash pendant l'appel LLM: {str(e)}")
                raise

        # Backend TGI (prompt concaténé)
        elif self.backend == "hf_tgi":
            parts = []
            if system_prompt:
                parts.append("System: " + system_prompt.strip())
            for msg in history:
                role = msg["role"].capitalize()
                parts.append(f"{role}: {msg['content'].strip()}")
            parts.append("Assistant:")
            prompt = "\n".join(parts)
            return self._call_hf_tgi(prompt)

        # Backend Gemini (REST)
        elif self.backend == "gemini":
            return self._call_gemini(system_prompt, history)

        else:
            raise LLMError(f"Unsupported backend: {self.backend}")