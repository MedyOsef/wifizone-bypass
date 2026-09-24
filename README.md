# wifizone-bypass — PoC académique (LABO UNIQUEMENT)
![description](https://github.com/MedyOsef/wifizone-bypass/blob/main/wifi_labo_testeur_mac.gif?raw=true)
> 🌍 *English version: [README.en.md](README.en.md)*

> ⚠️ **Éthique / légal** : à but **éducatif**, sur **votre propre labo** (point d'accès de test vous appartenant, autorisation écrite).
> L'usage sur un WiFi zone tiers sans autorisation = intrusion / vol de service, illégal.
> Le programme refuse de tester sans la case / l'option d'autorisation, et restaure toujours votre MAC d'origine.

Démontre pourquoi **l'authentification par MAC seule est insuffisante** : une MAC transite en clair, se capture passivement et se rejoue avec des commandes standard (`nmcli`, `ip link`).

---

## 🖥️ Utilisation simple : l'interface graphique (`gui.py`)

Pas de terminal à retenir. Interface moderne (Flet, pas tkinter) en **français ou anglais** (bouton **EN/FR** en haut à droite) avec **mode sombre/clair** (bouton 🌙/☀️).

```bash
pip install -r requirements-gui.txt
sudo .venv/bin/python gui.py
```

> **Pourquoi `sudo` ?** Changer de MAC et capturer du trafic exigent les droits root.
> **Pourquoi ça s'ouvre dans le navigateur en sudo ?** C'est volontaire : la fenêtre native lancée en root plante en dur (GTK + thème d'icônes de l'user → `abort`, irrattrapable). En sudo l'appli va donc **directement** sur le navigateur — **l'adresse exacte (localhost + IP réseau + port) s'affiche dans le terminal**, laissez-le ouvert.
> Pour forcer : `FLET_GUI=web` (navigateur, zéro téléchargement) ou `FLET_GUI=desktop` (fenêtre — déconseillé en sudo : crash GTK probable).

### Étape 0 — Capturer VOTRE labo (optionnel)
- Renseignez la **durée** (30 s par défaut), cliquez **● Capturer**, **⏹ Stop** pour arrêter avant la fin.
- La capture est enregistrée dans `/tmp/capture-AAAAMMJJ-HHMMSS.pcapng` (et pas dans le dossier projet : l'outil de capture abandonne ses privilèges root et ne peut pas écrire ailleurs).
- À la fin, les adresses MAC sont **extraites automatiquement** (`wlan.sa/wlan.da` via tshark, sinon `eth.src/eth.dst`) : doublons, broadcast et adresses invalides filtrés, et le champ fichier est rempli tout seul.

### Étape 1 — Où tester ?
- **Interface WiFi** : liste détectée automatiquement (`wlan0`…).
- **Fichier MACs** : bouton 📂 **Choisir un fichier MACs**, ou tapez/corrigez le chemin à la main (ex. `mac_output.txt`, `/tmp/mac_output.txt`). En mode navigateur, le fichier choisi est importé en local (`macs_gui_import.txt`).
- **SSID Cible** : simple étiquette libre (ex. `TP-SalleB`) retrouvée dans `results.csv`.

### Étape 2 — Lancer le vrai test
- Cochez **« Je confirme tester UNIQUEMENT mon propre labo autorisé »**.
- Cliquez **▶ Lancer** (refuse de démarrer deux fois ; **⏹ Stop** arrête proprement entre deux MACs, avec restauration).
- Suivi en direct : `Essai 3/40 : aa:...`, barre de progression, cartes résultat **✅ internet OK / ⚠️ portail captif / ❌ pas d'internet**, et **journal** en bas.

### Le cycle testé pour CHAQUE adresse MAC
1. Prend l'adresse suivante de la liste.
2. L'applique via le profil NetworkManager (`nmcli connection modify <profil> 802-11-wireless.cloned-mac-address <mac>` puis `nmcli connection up <profil>`) — sans ça, NetworkManager restaure la MAC d'usine au reconnect et fausse tous les résultats.
3. **Vérifie d'abord** : carte remontée + **MAC relue == demandée** + **adresse IP obtenue (DHCP)**. Sans IP → échec direct, pas de test inutile, suivante.
4. Fait l'équivalent de `curl http://www.google.com` : ✅ si vraie page Google, ⚠️ si portail captif, ❌ sinon. (Pas de ping : la passerelle répond même sans authentification, donc le ping ne prouve rien.)
5. Écrit le résultat dans `results.csv` et passe à la suivante (~2–4 s par MAC).

### Bouton « Utiliser » et « Restaurer »
- Chaque carte verte a un bouton **Utiliser** : applique cette MAC en un clic (même séquence vérifiée) pour surfer avec.
- **↩ Restaurer mon MAC** : efface le `cloned-mac-address` du profil, remet la MAC d'origine (celle du début de session, sinon la hardware via `ethtool -P`), reconnecte, **et affiche la MAC réellement lue** — jamais de faux « restaurée 👍 ».

### Le journal (lignes `$`)
Chaque commande système exacte exécutée s'affiche avec `$ ` devant (ex. `$ nmcli connection up "ADMINISTRATION FOYER AKWABA"`). Pratique pour comprendre, débugger et alimenter le rapport. Seul le polling DHCP (`ip -4 ...` toutes les 0,5 s) est filtré pour rester lisible.

---

## ⌨️ Utilisation terminal (`tester_mac.py`, inchangé et toujours fonctionnel)

```bash
# valider sans rien modifier
python3 tester_mac.py --interface wlan0 --file mac_output.txt --dry-run

# test réel labo
sudo python3 tester_mac.py -i wlan0 -f mac_output.txt \
  --lab-ap "TP-SalleB" --confirm-lab --out results.csv

# options utiles
#   --http-url http://www.google.com   URL(s) test façon curl, séparées par virgule
#   --timeout 4                        timeout HTTP par MAC (s)
#   --delay 8                          attente MAX DHCP par MAC (sortie précoce dès l'IP)
#   --limit 5                          limiter à N MACs (test court)
#   --manual                           pause Entrée entre chaque MAC (test navigateur à la main)
```

Même moteur que la GUI : application persistante vérifiée (MAC relue + IP), curl google, CSV `results.csv` (`timestamp,lab,interface,mac,applied,ping_ok,http_ok,http_code,portal,detail,mode` — `ping_ok` gardé vide pour compatibilité), restauration auto même sur Ctrl+C.

---

## 🛠️ Prérequis

- Linux, `python3`, `iproute2`, `ethtool`, `network-manager` (`nmcli`), `tshark` pour la capture.
- root (`sudo`) pour changer de MAC et capturer.
- GUI : `pip install -r requirements-gui.txt` (paquet `flet` uniquement ; le CLI n'a besoin que de la stdlib).

```bash
sudo apt install tshark python3 network-manager ethtool iproute2
```

## 📴 Fonctionnement hors-ligne (terrain sans internet)

L'ordinateur n'a pas internet au lancement ? C'est prévu : **tout tourne en local**, seul le verdict curl *tente* le réseau (et échoue vite sinon).

**Préparation EN LIGNE, une seule fois avant le terrain :**
```bash
pip install -r requirements-gui.txt   # ou le .venv déjà prêt
python3 gui.py                        # amorce le cache d'affichage (puis Ctrl+C)
```
(Pas besoin d'amorcer quoi que ce soit en root : en sudo l'appli utilise le navigateur, sans téléchargement.)

**Matrice hors-ligne :**

| Fonction | Sans réseau |
|---|---|
| GUI hors sudo (fenêtre) | ✅ 100 % locale une fois le client en cache |
| GUI en sudo (navigateur) | ✅ direct, `no_cdn=True` : zéro appel CDN, zéro download |
| Capture tshark + extraction MACs | ✅ local |
| Apply MAC + vérif MAC lue + IP DHCP | ✅ local |
| Verdict curl google | ❌ rapide `pas de réseau (DNS…)` (pré-check DNS ~3 s max, pas de blocage) |
| Restore + CSV + journal `$` | ✅ local |

> Astuce : sans réseau, chaque MAC donne `❌ pas de réseau (DNS…)` en ~3 s — normal, c'est le verdict « pas d'internet », pas un bug. Dès qu'une MAC ouvre l'accès, le verdict passe à ✅ tout seul.

## ❓ Problèmes fréquents

| Symptôme | Cause / solution |
|---|---|
| `Permission denied` sur le `.pcapng` en capture | Normal : captures dans `/tmp/`, corrigé automatiquement. |
| Fichiers appartenant à root dans le projet | Rendus à votre user via `SUDO_UID` après écriture ; nettoyez l'ancien `__pycache__` root avec `sudo rm -rf __pycache__`. |
| La MAC « ne change pas » | C'était NetworkManager qui écrasait : maintenant application via `cloned-mac-address` du profil + vérification lue. |
| L'interface « reste down » | `set_mac` remonte toujours l'interface en `finally` + `ensure_link_up` après chaque phase. |
| « Fichier introuvable » dans la GUI | Le fichier n'existe pas encore : générez-le (Étape 0) ou créez-le (une MAC par ligne), ou corrigez le chemin (`/tmp/...`). |
| Flet retélécharge son client en sudo | Ne devrait plus arriver : en sudo l'appli va direct au navigateur (pas de download). Hors sudo, normal la 1ʳᵉ fois (cache vide) puis réutilisé. |
| Crash GTK `ensure_surface_for_gicon` / `Bail out!` en sudo | Connu : fenêtre native en root + thème d'icônes user = abort irrattrapable. L'appli contourne en allant direct au navigateur en sudo ; ne forcez pas `FLET_GUI=desktop` en sudo. |

---

## 🔍 À mettre dans votre rapport

| Vulnérabilité | Explication | Contre-mesure |
|---|---|---|
| MAC seule | En clair, rejouable | Portail captif + token session |
| Pas de session liée | Rejeu trivial | RADIUS / 802.1X, timeout court |
| Usurpation facile | `nmcli`/`ip link` standard, NM réapplique tout seul | Détection doublons MAC, alertes simultanées |

Pistes opérateur : 802.1X, tokens courts, détection même MAC sur 2 radios / 2 débits, isolation client.

---

## 📁 Structure

```
.
├── README.md
├── README.en.md         # Ce doc en anglais
├── tester_mac.py        # Moteur CLI + fonctions partagées (apply, test curl, restore)
├── gui.py               # Interface Flet : capture, test, Utiliser, Stop, Restaurer, journal $
├── requirements-gui.txt # flet>=1.0 (GUI uniquement)
├── .gitignore           # ignore pcap, listes MACs, results.csv, .venv/, __pycache__…
├── mac_output.txt       # VOTRE liste de MACs (généré, non versionné)
└── results.csv          # Résultats (généré, non versionné)
```
