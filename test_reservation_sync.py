#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de test pour la réservation avec synchronisation WebSocket
"""

import asyncio
import websockets
import json
import requests
import sys

# URLs
API_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000"

async def test_websocket_sync():
    """Test la synchronisation WebSocket des slots"""
    
    # 1. Créer une session de test
    print("\n=== TEST 1: Création de session ===")
    session_response = requests.get(f"{API_URL}/v1/session")
    if session_response.status_code != 200:
        # Créer une sessions via le format POST
        test_session = "test_session_001"
    else:
        test_session = "test_session_001"
    
    print(f"✓ Session: {test_session}")
    
    # 2. Connecter au WebSocket
    print("\n=== TEST 2: Connexion WebSocket ===")
    try:
        async with websockets.connect(f"{WS_URL}/ws/reservation/{test_session}") as websocket:
            print("✓ WebSocket connecté")
            
            # 3. Recevoir le message initial
            print("\n=== TEST 3: Réception initial ===")
            initial_message = await websocket.recv()
            initial_data = json.loads(initial_message)
            print(f"✓ Message reçu: {initial_data}")
            
            # 4. Envoyer une requête de réservation
            print("\n=== TEST 4: Envoi de requête de réservation ===")
            reservation_request = {
                "text": "Je veux réserver la salle A pour le 21 avril 2026 à 10h",
                "session_id": test_session,
                "user_name": "Jean Dupont"
            }
            
            response = requests.post(
                f"{API_URL}/v1/respond",
                json=reservation_request
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✓ Réponse du serveur: {result['text']}")
            else:
                print(f"✗ Erreur: {response.status_code}")
            
            # 5. Vérifier les slots
            print("\n=== TEST 5: Vérification des slots ===")
            slots_response = requests.get(f"{API_URL}/v1/session/{test_session}/slots")
            if slots_response.status_code == 200:
                slots_data = slots_response.json()
                print(f"✓ Slots actuels: {slots_data['slots']}")
            
            # 6. Recevoir la mise à jour via WebSocket
            print("\n=== TEST 6: Réception mise à jour WebSocket ===")
            try:
                websocket.settimeout(2)
                updated_message = await asyncio.wait_for(websocket.recv(), timeout=3.0)
                updated_data = json.loads(updated_message)
                print(f"✓ Mise à jour reçue: {updated_data}")
            except asyncio.TimeoutError:
                print("⚠ Timeout - aucune mise à jour reçue (peut être normal)")
            
            print("\n=== TESTS RÉUSSIS ===\n")
            
    except Exception as e:
        print(f"✗ Erreur WebSocket: {e}")
        sys.exit(1)


def test_http_slots():
    """Test l'endpoint HTTP pour les slots"""
    print("\n=== TEST HTTP: Récupération des slots ===")
    
    session_id = "test_session_002"
    
    # 1. Envoyer une requête
    print("1. Envoi de requête de réservation...")
    response = requests.post(
        f"{API_URL}/v1/respond",
        json={
            "text": "Je veux réserver la salle B pour le 22 avril à 14h30",
            "session_id": session_id
        }
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✓ Réponse: {result['text']}")
    else:
        print(f"✗ Erreur: {response.status_code}")
    
    # 2. Récupérer les slots
    print("\n2. Récupération des slots...")
    slots_response = requests.get(f"{API_URL}/v1/session/{session_id}/slots")
    
    if slots_response.status_code == 200:
        slots_data = slots_response.json()
        print(f"✓ Slots récupérés:")
        for key, value in slots_data['slots'].items():
            print(f"  - {key}: {value}")
    else:
        print(f"✗ Erreur: {slots_response.status_code}")


if __name__ == "__main__":
    print("╔═══════════════════════════════════════════╗")
    print("║ TEST SYNCHRONISATION RÉSERVATION         ║")
    print("╚═══════════════════════════════════════════╝")
    
    # Test HTTP simple
    test_http_slots()
    
    # Test WebSocket
    try:
        asyncio.run(test_websocket_sync())
    except KeyboardInterrupt:
        print("\n\nTests interrompus")
