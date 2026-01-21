# -*- coding: utf-8 -*-
import requests
import os

class NetworkClient:
    def __init__(self, server_url, timeout):
        self.server = server_url
        self.timeout = timeout

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

    def send_dialog_text(self, text, session_id=None, lang="fr"):
        """ Envoie le texte reconnu au DialogManager """
        url = "{0}/v1/respond".format(self.server)
        payload = {"text": text, "lang": lang}
        if session_id:
            payload["session_id"] = session_id
        
        try:
            r = requests.post(url, json=payload, timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print("Erreur Dialog: {0}".format(str(e)))
            return None