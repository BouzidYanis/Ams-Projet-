# -*- coding: utf-8 -*-
from naoqi import ALProxy

class PepperRobot:
    def __init__(self, ip="127.0.0.1", port=9559):
        try:
            self.tts = ALProxy("ALAnimatedSpeech", ip, port)
            print(u"Connecté au Robot Pepper".encode('utf-8'))
        except Exception as e:
            print(u"Erreur connexion NAOqi: {0}".format(e).encode('utf-8'))
            self.tts = None    

    def say(self, text):
        if self.tts and text:
            self.tts.say(text.encode('utf-8'))
        else:
            print("Robot simulé : " + text)       
            