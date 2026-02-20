# -*- coding: utf-8 -*-
import os
import requests
from affichage_dynamique import PepperWebDisplayService

class Navigation:
    def __init__(self,api_base,session):
        self.api_base = api_base.rstrip("/")
        self.web_display = PepperWebDisplayService(session)
        self.session = session
    def afficher_carte(self, destination):
        url = "{}/carte_navigation.html?destination={}".format(self.api_base, destination)
        self.web_display.showUrl(url)
    
    def parler(self, message):
        # Implémenter la fonction pour faire parler le robot
        self.session.service("ALTextToSpeech").say(message)
