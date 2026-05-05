#!/usr/bin/env python3
"""
test_survey.py
Script de test pour le système de questionnaire de satisfaction
"""

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8001"

def test_satisfaction_survey():
    """Test complet du système de questionnaire"""
    
    print("\n" + "="*60)
    print("TEST: Système de Questionnaire de Satisfaction")
    print("="*60)
    
    # 1. Tester la page HTML
    print("\n[TEST 1] Récupération de la page satisfaction.html...")
    try:
        response = requests.get(f"{BASE_URL}/satisfaction.html")
        if response.status_code == 200:
            print("✓ Page HTML récupérée avec succès")
            print(f"  Taille: {len(response.text)} bytes")
        else:
            print(f"✗ Erreur: {response.status_code}")
            return
    except Exception as e:
        print(f"✗ Erreur connexion: {e}")
        return
    
    # 2. Créer une session test
    print("\n[TEST 2] Création d'une session test...")
    
    # Simuler une session avec historique
    test_session_id = "test-session-2024-01-15"
    
    # Premiers tests: vérifier que les endpoints existent
    print("\n[TEST 3] Test des endpoints GET...")
    
    # Test GET history
    print("  - GET /api/session/{id}/history")
    try:
        response = requests.get(f"{BASE_URL}/api/session/{test_session_id}/history")
        if response.status_code == 200:
            data = response.json()
            print(f"    ✓ OK - {data.get('turn_count', 0)} tours")
        else:
            print(f"    ✗ Status: {response.status_code}")
    except Exception as e:
        print(f"    ✗ Erreur: {e}")
    
    # Test GET NLU data
    print("  - GET /api/session/{id}/nlu-data")
    try:
        response = requests.get(f"{BASE_URL}/api/session/{test_session_id}/nlu-data")
        if response.status_code == 200:
            data = response.json()
            print(f"    ✓ OK - {data.get('total_items', 0)} items NLU")
        else:
            print(f"    ✗ Status: {response.status_code}")
    except Exception as e:
        print(f"    ✗ Erreur: {e}")
    
    # 3. Test POST survey submit
    print("\n[TEST 4] Soumission du questionnaire...")
    
    survey_payload = {
        "session_id": test_session_id,
        "ease_of_use": 4,
        "response_quality": 5,
        "interaction_comfort": 4,
        "additional_comments": "Très bon service, bravo !",
        "nlu_corrections": [
            {
                "original_text": "Je veux réserver une activité",
                "predicted_intent": "book_activity",
                "corrected_intent": "book_activity",
                "corrected_entities": {"activity": "football"}
            }
        ]
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/v1/survey/submit",
            json=survey_payload,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"  Status: {response.status_code}")
        result = response.json()
        
        if response.status_code == 200:
            print("  ✓ Questionnaire soumis avec succès")
            print(f"    - Message: {result.get('message')}")
            print(f"    - Session reset: {result.get('session_reset')}")
            print(f"    - Ready for next: {result.get('ready_for_next_user')}")
        else:
            print(f"  ✗ Erreur: {result.get('detail', 'Unknown error')}")
            
    except Exception as e:
        print(f"  ✗ Erreur: {e}")
    
    # 4. Test de validation - scores invalides
    print("\n[TEST 5] Test de validation (scores invalides)...")
    
    invalid_payload = {
        "session_id": test_session_id,
        "ease_of_use": 10,  # Invalid (> 5)
        "response_quality": 5,
        "interaction_comfort": 4
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/v1/survey/submit",
            json=invalid_payload
        )
        
        if response.status_code != 200:
            result = response.json()
            print(f"  ✓ Validation fonctionne: {result.get('detail')}")
        else:
            print(f"  ✗ Validation ne fonctionne pas")
            
    except Exception as e:
        print(f"  ✗ Erreur: {e}")
    
    # 5. Récupérer les données du feedback depuis MongoDB
    print("\n[TEST 6] Vérification du stockage MongoDB...")
    
    try:
        from app.DB_access import DatabaseMongo
        db = DatabaseMongo()
        feedback = db.get_collection("satisfaction_feedback").find_one({
            "session_id": test_session_id
        })
        
        if feedback:
            print("  ✓ Feedback trouvé dans MongoDB")
            print(f"    - ID: {feedback['_id']}")
            print(f"    - Facilité: {feedback['ease_of_use']}/5")
            print(f"    - Qualité: {feedback['response_quality']}/5")
            print(f"    - Confort: {feedback['interaction_comfort']}/5")
            print(f"    - Commentaires: {feedback.get('additional_comments', '')}")
            
            # Vérifier les corrections NLU
            corrections = feedback.get('nlu_corrections', [])
            print(f"    - Corrections NLU: {len(corrections)}")
            for i, correction in enumerate(corrections, 1):
                print(f"      {i}. '{correction['original_text']}' -> {correction['corrected_intent']}")
        else:
            print("  ✗ Feedback non trouvé dans MongoDB")
            
    except ImportError:
        print("  ⚠ Impossible d'accéder à MongoDB directement")
    except Exception as e:
        print(f"  ✗ Erreur: {e}")
    
    # 7. Test analytics simple
    print("\n[TEST 7] Statistiques de satisfaction...")
    
    try:
        from app.DB_access import DatabaseMongo
        db = DatabaseMongo()
        
        pipeline = [
            {
                "$group": {
                    "_id": None,
                    "avg_ease": {"$avg": "$ease_of_use"},
                    "avg_quality": {"$avg": "$response_quality"},
                    "avg_comfort": {"$avg": "$interaction_comfort"},
                    "count": {"$sum": 1},
                    "total_turns": {"$sum": "$conversation_turns"}
                }
            }
        ]
        
        stats = list(db.get_collection("satisfaction_feedback").aggregate(pipeline))
        
        if stats:
            s = stats[0]
            print("  ✓ Statistiques disponibles")
            print(f"    - Facilité d'utilisation: {s.get('avg_ease', 0):.2f}/5")
            print(f"    - Qualité des réponses: {s.get('avg_quality', 0):.2f}/5")
            print(f"    - Confort d'interaction: {s.get('avg_comfort', 0):.2f}/5")
            print(f"    - Total questionnaires: {s.get('count', 0)}")
            print(f"    - Total tours de conversation: {s.get('total_turns', 0)}")
        else:
            print("  ⚠ Aucune donnée disponible")
            
    except Exception as e:
        print(f"  ⚠ Impossible de calculer les stats: {e}")
    
    print("\n" + "="*60)
    print("Tests terminés")
    print("="*60 + "\n")

def test_nlu_corrections():
    """Test du système de corrections NLU"""
    
    print("\n" + "="*60)
    print("TEST: Corrections NLU et Formation Continue")
    print("="*60)
    
    test_session_id = "test-nlu-session-2024"
    
    print("\n[TEST] Vérification des collections NLU...")
    
    try:
        from app.DB_access import DatabaseMongo
        db = DatabaseMongo()
        
        # Compter les corrections
        corrections_count = db.get_collection("nlu_corrections").count_documents({})
        print(f"  ✓ Collection 'nlu_corrections': {corrections_count} documents")
        
        # Afficher les dernières corrections
        if corrections_count > 0:
            recent = list(db.get_collection("nlu_corrections").find().sort("timestamp", -1).limit(3))
            print(f"    Dernières corrections:")
            for correction in recent:
                print(f"      - '{correction['original_text']}' -> {correction['corrected_intent']}")
        
    except Exception as e:
        print(f"  ✗ Erreur: {e}")
    
    print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    import sys
    
    print("\n🧪 Suite de tests pour le Questionnaire de Satisfaction\n")
    
    # Vérifier que le serveur est en ligne
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        if response.status_code == 200:
            print(f"✓ Serveur accessible: {BASE_URL}")
        else:
            print(f"✗ Serveur retourne: {response.status_code}")
    except Exception as e:
        print(f"✗ Serveur non accessible: {e}")
        print(f"  Assurez-vous que le serveur est lancé sur {BASE_URL}")
        sys.exit(1)
    
    # Exécuter les tests
    test_satisfaction_survey()
    test_nlu_corrections()
    
    print("\n✓ Tous les tests sont terminés!\n")
