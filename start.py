#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script de lancement interactif pour le projet Ams-Projet
Permet de gérer le backend, client, tests et configuration
"""

import subprocess
import sys
import os
import platform
import time
import signal

class StartMenu:
    def __init__(self):
        self.processes = {}
        self.running = True
        self.project_root = os.path.dirname(os.path.abspath(__file__))
        
    def clear_screen(self):
        """Efface l'écran"""
        if platform.system() == "Windows":
            os.system("cls")
        else:
            os.system("clear")
    
    def print_header(self):
        """Affiche l'entête du menu"""
        print("\n" + "="*60)
        print("  AMS-PROJET - ROBOT ACCUEIL - MENU DE LANCEMENT")
        print("="*60 + "\n")
    
    def print_menu(self):
        """Affiche le menu principal"""
        self.print_header()
        print("OPTIONS DISPONIBLES:")
        print("  [1] Lancer le serveur Backend (FastAPI)")
        print("  [2] Lancer le client Robot (main2.py)")
        print("  [3] Lancer les tests de reservation")
        print("  [4] Valider la configuration")
        print("  [5] Afficher la configuration")
        print("  [6] Installer les dependances")
        print("  [7] Verifier l'etat des services")
        print("  [0] Quitter")
        print("\n" + "-"*60 + "\n")
    
    def get_choice(self):
        """Récupère le choix de l'utilisateur"""
        try:
            choice = raw_input("Entrez votre choix [0-7]: ").strip()
            return choice
        except:
            choice = input("Entrez votre choix [0-7]: ").strip()
            return choice
    
    def check_python_version(self):
        """Affiche la version Python"""
        print("Version Python: {}".format(sys.version))
        return True
    
    def check_required_packages(self):
        """Verifie les packages requis"""
        print("\nVerification des packages requis...")
        required = ["fastapi", "uvicorn", "requests", "websockets", "spacy", "pydantic"]
        missing = []
        
        for package in required:
            try:
                __import__(package)
                print("  [OK] {}".format(package))
            except ImportError:
                print("  [ERREUR] {} manquant".format(package))
                missing.append(package)
        
        if missing:
            print("\nPackages manquants: {}".format(", ".join(missing)))
            print("Installez-les avec: pip install {}".format(" ".join(missing)))
            return False
        
        print("\n[OK] Tous les packages requis sont installes")
        return True
    
    def check_config_files(self):
        """Verifie l'existence des fichiers de configuration"""
        print("\nVerification des fichiers de configuration...")
        files = [
            "app/main.py",
            "app/dialog_manager.py",
            "app/sessions.py",
            "configs/llm_openai_config.json",
            "configs/intents.json",
            "client/main2.py",
            "test_reservation_sync.py",
        ]
        
        missing = []
        for f in files:
            path = os.path.join(self.project_root, f)
            if os.path.exists(path):
                print("  [OK] {}".format(f))
            else:
                print("  [ERREUR] {} introuvable".format(f))
                missing.append(f)
        
        if missing:
            print("\nFichiers manquants: {}".format(", ".join(missing)))
            return False
        
        print("\n[OK] Tous les fichiers requis sont presents")
        return True
    
    def launch_backend(self):
        """Lance le serveur FastAPI"""
        print("\nLancement du serveur Backend...")
        print("=" * 60)
        
        try:
            # Verifier que les dépendances sont disponibles
            import uvicorn
            import fastapi
            
            print("[OK] FastAPI et Uvicorn disponibles")
            print("Port: 8001")
            print("URL: http://localhost:8001")
            print("\nAppuyez sur Ctrl+C pour arreter le serveur")
            print("-" * 60 + "\n")
            
            # Lancer uvicorn
            cmd = [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host", "0.0.0.0",
                "--port", "8001",
                "--reload"
            ]
            
            self.processes["backend"] = subprocess.Popen(cmd, cwd=self.project_root)
            print("[INFO] Serveur Backend lancé (PID: {})".format(self.processes["backend"].pid))
            
            # Attendre un peu pour que le serveur démarre
            time.sleep(3)
            print("[INFO] Serveur pret sur http://localhost:8001")
            
            # Garder le processus en cours d'exécution
            self.processes["backend"].wait()
            
        except ImportError as e:
            print("[ERREUR] Dependances manquantes: {}".format(e))
            print("Installez avec: pip install fastapi uvicorn")
        except KeyboardInterrupt:
            print("\n[INFO] Serveur Backend arrete")
            if "backend" in self.processes:
                self.processes["backend"].terminate()
        except Exception as e:
            print("[ERREUR] {}".format(e))
    
    def launch_client(self):
        """Lance le client Robot"""
        print("\nLancement du client Robot...")
        print("=" * 60)
        
        try:
            print("[INFO] Assurez-vous que le robot Pepper est accessible")
            print("[INFO] Port du robot: 9559")
            print("\nAppuyez sur Ctrl+C pour arreter le client")
            print("-" * 60 + "\n")
            
            # Verifier si on est sur Python 2 ou 3
            if sys.version_info[0] == 2:
                cmd = ["python", "client/main2.py"]
            else:
                cmd = ["python", "client/main2.py"]
            
            self.processes["client"] = subprocess.Popen(cmd, cwd=self.project_root)
            print("[INFO] Client Robot lancé (PID: {})".format(self.processes["client"].pid))
            
            # Garder le processus en cours d'exécution
            self.processes["client"].wait()
            
        except KeyboardInterrupt:
            print("\n[INFO] Client Robot arrete")
            if "client" in self.processes:
                self.processes["client"].terminate()
        except Exception as e:
            print("[ERREUR] {}".format(e))
    
    def run_tests(self):
        """Lance les tests de reservation"""
        print("\nLancement des tests de reservation...")
        print("=" * 60)
        
        try:
            print("[IMPORTANT] Assurez-vous que le serveur Backend est en cours d'execution!")
            print("\nLancez dans un autre terminal: python start.py (option 1)")
            print("-" * 60 + "\n")
            
            time.sleep(2)
            
            cmd = [sys.executable, "test_reservation_sync.py"]
            self.processes["tests"] = subprocess.Popen(cmd, cwd=self.project_root)
            
            # Attendre la fin des tests
            self.processes["tests"].wait()
            
        except Exception as e:
            print("[ERREUR] {}".format(e))
        finally:
            if "tests" in self.processes:
                del self.processes["tests"]
    
    def validate_setup(self):
        """Valide la configuration"""
        print("\nValidation de la configuration...")
        print("=" * 60 + "\n")
        
        try:
            cmd = [sys.executable, "validate_setup.py"]
            subprocess.call(cmd, cwd=self.project_root)
        except Exception as e:
            print("[ERREUR] {}".format(e))
            print("Fichier validate_setup.py non trouve")
    
    def show_config(self):
        """Affiche la configuration"""
        print("\nAffichage de la configuration...")
        print("=" * 60 + "\n")
        
        config_file = os.path.join(self.project_root, "configs/config.py")
        
        if os.path.exists(config_file):
            try:
                with open(config_file, "r") as f:
                    content = f.read()
                    print(content)
            except Exception as e:
                print("[ERREUR] Impossible de lire la configuration: {}".format(e))
        else:
            print("[INFO] Fichier config.py non trouve")
            print("Vous pouvez consulter les fichiers de configuration dans configs/")
            
            # Afficher les fichiers disponibles
            configs_dir = os.path.join(self.project_root, "configs")
            if os.path.exists(configs_dir):
                print("\nFichiers disponibles:")
                for f in os.listdir(configs_dir):
                    print("  - {}".format(f))
    
    def install_dependencies(self):
        """Installe les dépendances"""
        print("\nInstallation des dependances...")
        print("=" * 60 + "\n")
        
        try:
            print("[INFO] Installation des packages Python requis...")
            
            requirements = [
                "fastapi",
                "uvicorn",
                "requests",
                "websockets",
                "spacy",
                "pydantic",
                "pydantic[dotenv]",
                "pymongo",
            ]
            
            for package in requirements:
                print("\nInstallation de: {}".format(package))
                cmd = [sys.executable, "-m", "pip", "install", package]
                result = subprocess.call(cmd)
                
                if result == 0:
                    print("[OK] {} installe".format(package))
                else:
                    print("[ERREUR] Impossible d'installer {}".format(package))
            
            print("\n[OK] Installation terminee")
            
        except Exception as e:
            print("[ERREUR] {}".format(e))
    
    def check_services_status(self):
        """Affiche l'état des services"""
        print("\nEtat des services...")
        print("=" * 60 + "\n")
        
        # Verifier Backend
        try:
            import requests
            response = requests.get("http://localhost:8001/", timeout=2)
            print("[ONLINE] Backend (http://localhost:8001)")
        except:
            print("[OFFLINE] Backend (http://localhost:8001)")
        
        # Verifier WebSocket
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(("localhost", 8001))
            if result == 0:
                print("[ONLINE] WebSocket (ws://localhost:8001)")
            else:
                print("[OFFLINE] WebSocket (ws://localhost:8001)")
            sock.close()
        except:
            print("[OFFLINE] WebSocket (ws://localhost:8001)")
        
        # Afficher les processus actifs
        print("\nProcessus actifs:")
        if self.processes:
            for name, proc in self.processes.items():
                status = "En cours" if proc.poll() is None else "Termine"
                print("  - {} (PID: {}) [{}]".format(name, proc.pid, status))
        else:
            print("  Aucun processus actif")
        
        print()
    
    def run(self):
        """Boucle principale du menu"""
        while self.running:
            try:
                self.print_menu()
                choice = self.get_choice()
                
                if choice == "1":
                    self.launch_backend()
                elif choice == "2":
                    self.launch_client()
                elif choice == "3":
                    self.run_tests()
                elif choice == "4":
                    self.validate_setup()
                elif choice == "5":
                    self.show_config()
                elif choice == "6":
                    self.install_dependencies()
                elif choice == "7":
                    self.check_services_status()
                elif choice == "0":
                    self.quit_menu()
                else:
                    print("[ERREUR] Choix invalide. Entrez 0-7")
                    time.sleep(1)
                
                raw_input("\nAppuyez sur Entree pour continuer...")
            except NameError:
                input("\nAppuyez sur Entree pour continuer...")
            except KeyboardInterrupt:
                print("\n\n[INFO] Menu interrompu")
                self.quit_menu()
            except Exception as e:
                print("\n[ERREUR] Une erreur est survenue: {}".format(e))
                time.sleep(2)
    
    def quit_menu(self):
        """Quitte le menu"""
        print("\nArrêt de tous les processus...")
        
        for name, proc in self.processes.items():
            if proc.poll() is None:
                print("[INFO] Arrêt de {}...".format(name))
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except:
                    proc.kill()
        
        print("[OK] Tous les processus ont ete arretes")
        print("\nAu revoir!\n")
        self.running = False
        sys.exit(0)


def main():
    """Point d'entrée"""
    try:
        menu = StartMenu()
        menu.run()
    except KeyboardInterrupt:
        print("\n\n[INFO] Programme interrompu")
        sys.exit(0)
    except Exception as e:
        print("\n[ERREUR] Erreur fatale: {}".format(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
