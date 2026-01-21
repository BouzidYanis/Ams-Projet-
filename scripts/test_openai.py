# scripts/test_gemini.py
#
# Test simple pour vérifier que le backend "gemini" de LLMClient fonctionne.
# Lancer depuis la racine du projet :
#   PYTHONPATH=. python scripts/test_gemini.py

from app.llm import LLMClient, LLMError
import os

def run_test():
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "configs", "llm_config.json")
    print("Config utilisée:", cfg_path)
    client = LLMClient(cfg_path)

    system_prompt = "Tu es un assistant pour un robot d'accueil d'une salle multisports. Réponds en français de façon concise."
    history = [
        {"role": "user", "content": "Bonjour, quels sont les horaires de la salle multisports ?"}
    ]

    try:
        out = client.generate_chat(system_prompt, history)
        print("Réponse de Gemini :")
        print(out)
    except LLMError as e:
        print("LLMError:", e)
    except Exception as e:
        print("Erreur inattendue:", e)

if __name__ == "__main__":
    run_test()