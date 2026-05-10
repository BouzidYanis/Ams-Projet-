# -*- coding: utf-8 -*-
import requests
import os

REQUEST_TIMEOUT = 70

class NetworkClient:
    def __init__(self, server_url, timeout):
        self.server = server_url
        self.timeout = timeout
        self.dialog_session_id = None

    def send_asr_file(self, file_path):
        """ Envoie le fichier WAV au serveur ASR """
        print(u' Envoi du fichier au serveur ASR...').encode('utf-8')
        url = "{0}/v1/asr".format(self.server)
        try:
            with open(file_path, 'rb') as f:
                files = {'file': (os.path.basename(file_path), f, 'audio/wav')}
                r = requests.post(url, files=files, timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(u" Erreur ASR: {0}".format(str(e)).encode('utf-8'))
            return None

    def send_dialog_text(self, text, lang="fr", session_id=None, user_name=None):
        """Envoie le texte transcrit au DialogManager et retourne la réponse."""
        payload = {
            "text": text,
            "lang": lang
        }
        # Ajouter les champs optionnels seulement s'ils ont une valeur
        if session_id is not None:
            payload["session_id"] = session_id
        if user_name is not None and user_name:
            payload["user_name"] = str(user_name)  # S'assurer que c'est une string

        try:
            url = "{0}/v1/respond".format(self.server)
            resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
            if resp.ok:
                data = resp.json()
                self.dialog_session_id = data.get("session_id", self.dialog_session_id)
                return data
            else:
                print("[DIALOG] Erreur HTTP {}: {}".format(resp.status_code, resp.text[:200]))
                return None
        except Exception as e:
            print("[DIALOG] Erreur envoi: " + repr(e))  # FIX
            return None

    def send_sleep_mode(self, session_id=None, user_name=None):
        """Archive la session côté serveur quand le robot passe en veille."""
        if not session_id:
            return None

        params = {"session_id": session_id}
        if user_name:
            params["user_name"] = str(user_name)

        try:
            url = "{0}/v1/sleep_mode".format(self.server)
            resp = requests.post(url, params=params, timeout=REQUEST_TIMEOUT)
            if resp.ok:
                return resp.json()
            print("[SLEEP] Erreur HTTP {}: {}".format(resp.status_code, resp.text[:200]))
            return None
        except Exception as e:
            print("[SLEEP] Erreur envoi: " + repr(e))
            return None

#Vielle Version
    # def send_dialog_text(self, text, session_id=None, lang="fr"):
    #     """ Envoie le texte reconnu au DialogManager """
    #     url = "{0}/v1/respond".format(self.server)
    #     payload = {"text": text, "lang": lang}
    #     if session_id:
    #         payload["session_id"] = session_id
        
    #     try:
    #         r = requests.post(url, json=payload, timeout=self.timeout)
    #         r.raise_for_status()
    #         return r.json()
    #     except Exception as e:
    #         print("Erreur Dialog: {0}".format(str(e)))
    #         return None