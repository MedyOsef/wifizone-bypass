import subprocess
import os
import sys

# --- CONFIGURATION ---
INTERFACE = "wlan0"
FICHIER_MACS = "mac_output-03-21.txt"

def run_command(command):
    """Exécute une commande système."""
    try:
        subprocess.run(command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Erreur lors de l'exécution : {e}")

def main():
    # 1. Vérification des droits root
    if os.geteuid() != 0:
        print("Erreur : Ce script doit être lancé avec 'sudo python3 tester_mac.py'")
        sys.exit(1)

    # 2. Vérification du fichier
    if not os.path.exists(FICHIER_MACS):
        print(f"Erreur : Le fichier '{FICHIER_MACS}' est introuvable.")
        sys.exit(1)

    # 3. Lecture des adresses MAC
    with open(FICHIER_MACS, "r") as f:
        # On nettoie les lignes (enlève les espaces et les sauts de ligne)
        mac_list = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    if not mac_list:
        print("La liste d'adresses MAC est vide.")
        sys.exit(1)

    print(f"--- Début du test ({len(mac_list)} adresses chargées) ---")
    
    for i, mac in enumerate(mac_list, 1):
        print(f"\n[{i}/{len(mac_list)}] Préparation de l'adresse : {mac}")
        
        # Application des commandes
        print(f"Arrêt de {INTERFACE}...")
        run_command(f"ip link set dev {INTERFACE} down")
        
        print(f"Changement d'adresse vers {mac}...")
        run_command(f"ip link set dev {INTERFACE} address {mac}")
        
        print(f"Réactivation de {INTERFACE}...")
        run_command(f"ip link set dev {INTERFACE} up")
        
        print("\n✅ ADRESSE APPLIQUÉE.")
        print("Attentes de teste (internet, ping, etc.).")
        
        # BLOQUAGE TOTAL : Le script s'arrête ici jusqu'à une action de ta part
        input("--> Appuie sur ENTRÉE pour passer à la MAC suivante...")
        
        print("-" * 40)

    print("\nFin de la liste. Toutes les adresses ont été testées.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nArrêt du script par l'utilisateur.")
        sys.exit(0)
