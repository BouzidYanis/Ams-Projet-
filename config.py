#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration pour le serveur de dialogue avec synchronisation de réservation
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env.local")

# ═══════════════════════════════════════════════════════════════════
# SERVEUR FASTAPI
# ═══════════════════════════════════════════════════════════════════

FASTAPI_HOST = "0.0.0.0"
FASTAPI_PORT = 8000
FASTAPI_RELOAD = True

# ═══════════════════════════════════════════════════════════════════
# COMMUNICATION RÉSEAU (Robot ↔ Backend)
# ═══════════════════════════════════════════════════════════════════

# Backend API (où le robot envoie les requêtes)
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# URL WebSocket pour synchronisation (la tablette se connecte ici)
WEBSOCKET_URL = os.getenv("WEBSOCKET_URL", "ws://localhost:8000")

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION TABLETTE/ROBOT
# ═══════════════════════════════════════════════════════════════════

# Adresse IP du robot Pepper
PEPPER_IP = os.getenv("PEPPER_IP", "192.168.13.202")
PEPPER_PORT = int(os.getenv("PEPPER_PORT", "9559"))

# Serveur web où la tablette accède aux pages HTML
# Cet URL est affiché sur la tablette du robot
TABLET_WEB_BASE_URL = os.getenv("TABLET_WEB_BASE_URL", "http://10.126.8.40:5500/")

# Pour développement local, utilisez:
# TABLET_WEB_BASE_URL = "http://localhost:8000/"

# URLs des pages
TABLET_RESERVATION_URL = TABLET_WEB_BASE_URL + "reservation.html"
TABLET_NAVIGATION_URL = TABLET_WEB_BASE_URL + "carte_navigation.html"

# ═══════════════════════════════════════════════════════════════════
# MODÈLES ET CONFIGURATIONS
# ═══════════════════════════════════════════════════════════════════

# Modèle ASR
ASR_MODEL_SIZE = os.getenv("ASR_MODEL_SIZE", "medium")

# Système de dialogue
DEFAULT_LANGUAGE = "fr"

# Session store TTL (Time To Live en secondes)
SESSION_TTL_SECONDS = 3600  # 1 heure

# ═══════════════════════════════════════════════════════════════════
# PATHS
# ═══════════════════════════════════════════════════════════════════

PROJECT_ROOT = Path(__file__).parent
APP_DIR = PROJECT_ROOT / "app"
CONFIGS_DIR = PROJECT_ROOT / "configs"
MODELS_DIR = PROJECT_ROOT

# ═══════════════════════════════════════════════════════════════════
# DÉBOGAGE
# ═══════════════════════════════════════════════════════════════════

DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")
VERBOSE_LOGGING = os.getenv("VERBOSE_LOGGING", "False").lower() in ("true", "1", "yes")

# ═══════════════════════════════════════════════════════════════════
# CORS & SÉCURITÉ
# ═══════════════════════════════════════════════════════════════════

# Origines autorisées pour les requêtes CORS
CORS_ORIGINS = [
    "http://localhost",
    "http://localhost:8000",
    "http://localhost:5500",
    "http://10.126.8.40:5500",
    "http://10.126.8.53:8080",
    "http://192.168.13.202:9559",
    os.getenv("ALLOWED_ORIGIN", ""),
]

# Filtrer les entrées vides
CORS_ORIGINS = [origin for origin in CORS_ORIGINS if origin]

# ═══════════════════════════════════════════════════════════════════
# BASE DE DONNÉES
# ═══════════════════════════════════════════════════════════════════

# MongoDB
MONGODB_URL = os.getenv("MONGODB_URL", os.getenv("MONGODB_URI", "mongodb://localhost:27017/"))
MONGODB_DB = os.getenv("MONGODB_DB", "multisports")

# ═══════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════

LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOG_LEVEL = "DEBUG" if DEBUG else "INFO"

# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════

def get_backend_url():
    """Obtient l'URL du backend"""
    return BACKEND_URL

def get_websocket_url():
    """Obtient l'URL WebSocket"""
    return WEBSOCKET_URL

def get_tablet_url(page="reservation"):
    """Obtient l'URL de la tablette pour une page"""
    if page == "reservation":
        return TABLET_RESERVATION_URL
    elif page == "navigation":
        return TABLET_NAVIGATION_URL
    else:
        return TABLET_WEB_BASE_URL + page

def is_local_deployment():
    """Vérifie si c'est un déploiement local"""
    return "localhost" in BACKEND_URL or "127.0.0.1" in BACKEND_URL

# ═══════════════════════════════════════════════════════════════════
# AFFICHAGE DE LA CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "="*60)
    print("CONFIGURATION - Serveur de Dialogue Pepper")
    print("="*60)
    print(f"\n🖥️  Backend:")
    print(f"   URL: {BACKEND_URL}")
    print(f"   Port: {FASTAPI_PORT}")
    print(f"\n🤖 Robot Pepper:")
    print(f"   IP: {PEPPER_IP}")
    print(f"   Port: {PEPPER_PORT}")
    print(f"\n📱 Tablette (Frontend):")
    print(f"   Base URL: {TABLET_WEB_BASE_URL}")
    print(f"   Pages web:")
    print(f"      - Réservation: {TABLET_RESERVATION_URL}")
    print(f"      - Navigation: {TABLET_NAVIGATION_URL}")
    print(f"\n🔌 WebSocket:")
    print(f"   URL: {WEBSOCKET_URL}")
    print(f"\n📊 Session Store:")
    print(f"   TTL: {SESSION_TTL_SECONDS}s")
    print(f"\n🛠️  Modèles:")
    print(f"   ASR: {ASR_MODEL_SIZE}")
    print(f"   Langue: {DEFAULT_LANGUAGE}")
    print(f"\n📂 Répertoires:")
    print(f"   Racine: {PROJECT_ROOT}")
    print(f"   App: {APP_DIR}")
    print(f"   Configs: {CONFIGS_DIR}")
    print(f"\n{'🐛 DEBUG' if DEBUG else '✓ Production'}")
    print("="*60 + "\n")
