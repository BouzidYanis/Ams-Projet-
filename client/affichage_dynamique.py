# -*- coding: utf-8 -*-
try:
    from naoqi import ALProxy
    import qi
except ImportError:
    print("Attention: modules naoqi/qi non disponibles")


class PepperWebDisplayService:
    def __init__(self, session):
        """
        Initialise le service d'affichage web pour Pepper
        """
        self.session = session
        self.tablet = session.service("ALTabletService")
        
        try:
            self.tablet.enableWifi()
        except Exception as e:
            print("Avertissement WiFi: {}".format(e))
    
    def showUrl(self, url):
        """Affiche une URL sur la tablette"""
        try:
            self.tablet.showWebview(url)
            print("Affichage de: {}".format(url))
        except Exception as e:
            print("Erreur lors de l'affichage de l'URL: {}".format(e))
            raise
    
    def showPage(self, url):
        """Alias de showUrl pour compatibilite"""
        self.showUrl(url)
    
    def hidePage(self):
        """Cache la page web"""
        try:
            self.tablet.hideWebview()
        except Exception as e:
            print("Erreur lors du masquage: {}".format(e))
    
    def reloadPage(self):
        """Recharge la page actuelle"""
        try:
            self.tablet.reload()
        except Exception as e:
            print("Erreur lors du rechargement: {}".format(e))
    
    def goBack(self):
        """Retour a la page precedente"""
        try:
            self.tablet.goBack()
        except Exception as e:
            print("Erreur lors du retour arriere: {}".format(e))
    
    def resetTablet(self):
        """Reinitialise la tablette"""
        try:
            self.tablet.resetTablet()
        except Exception as e:
            print("Erreur lors de la reinitialisation: {}".format(e))