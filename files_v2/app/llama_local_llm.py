# -*- coding: utf-8 -*-
import requests
import time
import json
import sys

class LLMManager:
    def __init__(self, model_name="phi3.5:latest"):
        self.base_url = "http://localhost:11434"
        self.model_name = model_name

    def is_ready(self):
        """ Vérifie si Ollama tourne et charge le modèle """
        try:
            requests.get(self.base_url, timeout=2)
            print(u"[LLM] Chargement de {0}...".format(self.model_name))
            r = requests.post(
                "{0}/api/generate".format(self.base_url),
                json={"model": self.model_name, "prompt": "", "keep_alive": "1h"},
                timeout=5
            )
            return r.status_code == 200
        except:
            print(u"[LLM] Erreur: Ollama n'est pas lancé sur 11434.")
            return False

    def check_gpu_usage(self):
        """ Vérifie si le modèle utilise le GPU (VRAM) """
        try:
            r = requests.get("{0}/api/ps".format(self.base_url))
            if r.status_code == 200:
                data = r.json()
                for model in data.get("models", []):
                    if self.model_name in model['name']:
                        vram = model.get('size_vram', 0)
                        proc = "GPU" if vram > 0 else "CPU"
                        print(u"[LLM] {0} est chargé sur {1}".format(self.model_name, proc))
                        return True
            print(u"[LLM] Modèle non détecté en mémoire.")
            return False
        except: return False

    def chat(self, user_text, system_prompt="Tu es Pepper, un robot d'accueil amical. Réponds brièvement."):
        """ Envoi un message et récupère la réponse complète """
        url = "{0}/v1/chat/completions".format(self.base_url)
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            "stream": False
        }
        
        try:
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code == 200:
                content = r.json()["choices"][0]["message"]["content"]
                if not content or content.strip() == "":
                    return u"[ERREUR] Le modèle a renvoyé une réponse vide."
                return content
            return u"Erreur HTTP {0}".format(r.status_code)
        except Exception as e:
            return u"Exception: {0}".format(str(e))

if __name__ == "__main__":
    print(u"--- MODE CHAT TERMINAL : PEPPER ---")
    llm = LLMManager()
    
    if llm.is_ready():
        llm.check_gpu_usage()
        print(u"\n(Tapez 'exit' ou 'quit' pour arrêter)")
        
        while True:
            try:
                # Compatible Python 2.7 et 3 pour l'input
                if sys.version_info[0] < 3:
                    user_input = raw_input("\nVous: ")
                else:
                    user_input = input("\nVous: ")

                if user_input.lower() in ['exit', 'quit']:
                    print("Bye bye!")
                    break

                if not user_input.strip():
                    continue

                print("Pepper réfléchit...")
                start = time.time()
                response = llm.chat(user_input)
                elapsed = time.time() - start

                print(u"Pepper ({0:.2f}s): {1}".format(elapsed, response))

            except KeyboardInterrupt:
                break
    else:
        print(u"[STOP] Impossible de démarrer le chat.")