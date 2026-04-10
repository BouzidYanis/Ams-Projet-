#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script de test pour la réservation avec synchronisation WebSocket
Compatible Python 2.7 + Python 3
"""

import json
import requests
import sys
import socket
import threading
import time

# URLs
API_URL = "http://localhost:8001"
WS_URL = "ws://localhost:8001"

def test_websocket_sync():
    """Test la synchronisation WebSocket des slots"""
    
    # 1. Créer une session de test
    print("\n=== TEST 1: Création de session ===")
    test_session = "test_session_001"
    print("[OK] Session: {}".format(test_session))
    
    # 2. Envoyer une requête de réservation
    print("\n=== TEST 2: Envoi de requête de réservation ===")
    reservation_request = {
        "text": "Je veux reserver la salle A pour le 21 avril 2026 a 10h",
        "session_id": test_session,
        "user_name": "Jean Dupont"
    }
    
    try:
        response = requests.post(
            "{}/v1/respond".format(API_URL),
            json=reservation_request,
            timeout=5
        )
        
        if response.status_code == 200:
            result = response.json()
            print("[OK] Reponse du serveur: {}".format(result.get('text', 'N/A')))
        else:
            print("[ERREUR] Code: {}".format(response.status_code))
            print("[ERREUR] Details: {}".format(response.text))
            
    except requests.ConnectionError as e:
        print("[ERREUR] Connexion refusee: {}".format(e))
        print("[INFO] Assurez-vous que le serveur FastAPI est en cours d'execution")
        print("[INFO] Lancez: python -m uvicorn app.main:app --host 0.0.0.0 --port 8000")
        return False
    except Exception as e:
        print("[ERREUR] Erreur: {}".format(e))
        return False
    
    # 3. Vérifier les slots via HTTP
    print("\n=== TEST 3: Verification des slots (HTTP) ===")
    try:
        slots_response = requests.get(
            "{}/v1/session/{}/slots".format(API_URL, test_session),
            timeout=5
        )
        if slots_response.status_code == 200:
            slots_data = slots_response.json()
            print("[OK] Slots actuels:")
            for key, value in slots_data.get('slots', {}).items():
                print("  - {}: {}".format(key, value))
        else:
            print("[ERREUR] Code: {}".format(slots_response.status_code))
    except Exception as e:
        print("[ERREUR] Impossible de recuperer les slots: {}".format(e))
        return False
    
    print("\n=== TESTS REUSSIS ===\n")
    return True


def test_health_check():
    """Vérifie que le serveur est accessible"""
    print("\n=== PRE-TEST: Vérification du serveur ===")
    try:
        response = requests.get(
            "{}/".format(API_URL),
            timeout=5
        )
        print("[OK] Serveur accessible")
        return True
    except requests.ConnectionError:
        print("[ERREUR] Le serveur n'est pas accessible sur {}".format(API_URL))
        print("")
        print("SOLUTION:")
        print("1. Assurez-vous que le backend est lancé:")
        print("   python -m uvicorn app.main:app --host 0.0.0.0 --port 8001")
        print("2. Ou utilisez le script de lancement:")
        print("   python start.py")
        print("")
        return False
    except Exception as e:
        print("[ERREUR] Erreur: {}".format(e))
        return False


def test_http_slots():
    """Test l'endpoint HTTP pour les slots"""
    print("\n=== TEST HTTP: Recuperation des slots ===")
    
    session_id = "test_session_002"
    
    # 1. Envoyer une requête
    print("1. Envoi de requete de reservation...")
    try:
        response = requests.post(
            "{}/v1/respond".format(API_URL),
            json={
                "text": "Je veux reserver la salle B pour le 22 avril a 14h30",
                "session_id": session_id
            },
            timeout=5
        )
        
        if response.status_code == 200:
            result = response.json()
            print("[OK] Reponse: {}".format(result.get('text', 'N/A')))
        else:
            print("[ERREUR] Code: {}".format(response.status_code))
    except Exception as e:
        print("[ERREUR] {}".format(e))
        return False
    
    # 2. Récupérer les slots
    print("\n2. Recuperation des slots...")
    try:
        slots_response = requests.get(
            "{}/v1/session/{}/slots".format(API_URL, session_id),
            timeout=5
        )
        
        if slots_response.status_code == 200:
            slots_data = slots_response.json()
            print("[OK] Slots recuperes:")
            for key, value in slots_data.get('slots', {}).items():
                print("  - {}: {}".format(key, value))
            return True
        else:
            print("[ERREUR] Code: {}".format(slots_response.status_code))
            return False
    except Exception as e:
        print("[ERREUR] {}".format(e))
        return False


if __name__ == "__main__":
    print("\n" + "="*50)
    print("TEST DE SYNCHRONISATION RESERVATION")
    print("="*50)
    
    # Vérifier que le serveur est en cours d'exécution
    if not test_health_check():
        sys.exit(1)
    
    # Test HTTP simple
    print("\n[TEST 1/2] Tests HTTP...")
    http_ok = test_http_slots()
    
    # Test WebSocket
    print("\n[TEST 2/2] Tests de reservation...")
    ws_ok = test_websocket_sync()
    
    # Résumé
    print("\n" + "="*50)
    print("RESUME DES TESTS:")
    print("="*50)
    print("[{}] Tests HTTP".format("OK" if http_ok else "ERREUR"))
    print("[{}] Tests Reservation".format("OK" if ws_ok else "ERREUR"))
    print("="*50 + "\n")
    
    if http_ok and ws_ok:
        print("[SUCCESS] Tous les tests sont passes!")
        sys.exit(0)
    else:
        print("[FAILURE] Certains tests ont echoue")
        sys.exit(1)
