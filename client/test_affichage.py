# -*- coding: utf-8 -*-
import qi
import sys
import time
from nav import Navigation
# Configuration
PEPPER_IP = "192.168.13.213"  # Remplacez par l'IP de votre Pepper
PEPPER_PORT = 9559

# def afficher_page_web(url):
#     """Affiche une page web sur la tablette de Pepper"""
#     try:
#         # Connexion a Pepper
#         print("Connexion a Pepper ({})...".format(PEPPER_IP))
#         session = qi.Session()
#         session.connect("tcp://{}:{}".format(PEPPER_IP, PEPPER_PORT))
#         print("Connecte !")
        
#         # Recuperation du service tablette
#         tablet = session.service("ALTabletService")
        
#         # Active le WiFi
#         try:
#             tablet.enableWifi()
#         except:
#             pass
        
#         # Affiche la page
#         print("Affichage de: " + url)
#         tablet.showWebview(url)
#         print("Page affichee avec succes !")
#         # tablet.executeJS('naviguerVers("salle_b");')        
#         # Laisser la page affichée pendant 30 secondes
#         print("Attente de 30 secondes...")
#         time.sleep(3)
        
#         # Masquer la page
#         tablet.hideWebview()
#         print("Page masquee.")
        
#     except Exception as e:
#         print("Erreur: " + str(e))
#         sys.exit(1)

# if __name__ == "__main__":
#     # URL de votre page web
#     url = "http://10.126.8.40:5500/carte_navigation.html?destination=salle_c"
    
#     afficher_page_web(url)

if __name__ == "__main__":
    try:
        # Connexion a Pepper
        print("Connexion a Pepper ({})...".format(PEPPER_IP))
        session = qi.Session()
        session.connect("tcp://{}:{}".format(PEPPER_IP, PEPPER_PORT))
        print("Connecte !")

        # Initialisation du service d'affichage et de navigation
        nav = Navigation("http://10.126.8.40:5500/",session)
        nav.afficher_carte('salle_a')
    except Exception as e:
        print("Erreur: " + str(e))
        sys.exit(1)