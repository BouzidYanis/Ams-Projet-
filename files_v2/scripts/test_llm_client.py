from app.llm import LLMClient, LLMError
import os

cfg_path = os.path.join(os.path.dirname(__file__), "..", "configs", "llm_config.json")

def run_test():
    print("Config utilisée:", cfg_path)
    client = LLMClient(cfg_path)
    system_prompt = "Tu es un assistant mock pour test."
    history = [
        {"role": "user", "content": "Bonjour, je veux m'inscrire au yoga à 18:00"}
    ]
    try:
        out = client.generate_chat(system_prompt, history)
        print("Réponse du LLM:")
        print(out)
    except LLMError as e:
        print("LLMError:", e)
    except Exception as e:
        print("Erreur inattendue:", e)

if __name__ == "__main__":
    run_test()