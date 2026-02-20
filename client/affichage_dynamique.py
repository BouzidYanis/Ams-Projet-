try:
    from naoqi import ALProxy
    import qi
except ImportError:
    print("Attention: modules naoqi/qi non disponibles")


class PepperWebDisplayService:
    def __init__(self, session):
        """
        Initialise le service d'affichage web pour Pepper
        
        Args:
            session: Session qi connectée au robot
        """
        self.session = session
        self.tablet = session.service("ALTabletService")
        
        # Active le WiFi si nécessaire
        try:
            self.tablet.enableWifi()
        except Exception as e:
            print("Avertissement WiFi:", e)
    
    def showUrl(self, url: str):
        """Affiche une URL sur la tablette"""
        try:
            self.tablet.showWebview(url)
            print(f"Affichage de: {url}")
        except Exception as e:
            print(f"Erreur lors de l'affichage de l'URL: {e}")
            raise
    
    def showPage(self, url: str):
        """Alias de showUrl pour compatibilité"""
        self.showUrl(url)
    
    def hidePage(self):
        """Cache la page web"""
        try:
            self.tablet.hideWebview()
        except Exception as e:
            print(f"Erreur lors du masquage: {e}")
    
    def reloadPage(self):
        """Recharge la page actuelle"""
        try:
            self.tablet.reload()
        except Exception as e:
            print(f"Erreur lors du rechargement: {e}")
    
    def goBack(self):
        """Retour à la page précédente"""
        try:
            self.tablet.goBack()
        except Exception as e:
            print(f"Erreur lors du retour arrière: {e}")
    
    def resetTablet(self):
        """Réinitialise la tablette"""
        try:
            self.tablet.resetTablet()
        except Exception as e:
            print(f"Erreur lors de la réinitialisation: {e}")