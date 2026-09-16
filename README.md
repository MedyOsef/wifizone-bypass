# wifizone-bypass — PoC académique (LABO UNIQUEMENT)

> ⚠️ **Éthique / légal** : à but **éducatif**, sur **votre propre labo** (AP de test vous appartenant, autorisation écrite).
> L'usage sur un WiFi zone tiers sans autorisation = intrusion / vol de service, illégal.
> Le script exige `--confirm-lab --lab-ap "NomLabo"` et restaure votre MAC d'origine.

Démontre pourquoi **l'authentification par MAC seule est insuffisante** : MAC en clair, rejouable avec `ip link`.

---

## 🎯 Ce que fait la v2

Ancien script : MAC en dur, `shell=True`, test manuel à chaque fois, pas de restauration.
Nouveau `tester_mac.py` :
- `argparse` : `--interface`, `--file`, `--out`, `--ping-target`, `--http-url`, `--limit`, `--dry-run`, `--manual`
- Validation : regex, rejet broadcast/multicast, déduplique, ignore votre propre MAC
- Sans `shell=True` (listes d'args), compatible NetworkManager (`nmcli disconnect/connect`)
- Test **auto** vers **votre passerelle labo** (ping + HTTP), log CSV `results.csv`
- Sauvegarde + **restauration auto** de la MAC d'origine (même sur Ctrl+C)
- Garde-fou : refuse de tourner hors `--dry-run` sans `--confirm-lab`

## 🛠️ Prérequis

- Linux, `python3` (stdlib uniquement, pas de dépendances), `iproute2`, `nmcli` recommandé
- `tshark` uniquement pour analyser **votre capture labo**
- root pour changer de MAC

```bash
sudo apt install tshark python3 network-manager
```

## ⚙️ Workflow labo recommandé

### 1. Montez votre labo (pas le réseau du voisin)
Créez un AP de test (hostapd / routeur de TP) avec filtrage MAC activé. Notez son SSID = votre `--lab-ap`.

### 2. Capture labo -> liste MACs
```bash
# capture sur VOTRE labo uniquement
tshark -i wlan0 -w labo.pcapng
# extraction + tri par activité (les plus actifs d'abord, utile en démo)
tshark -r labo.pcapng -T fields -e wlan.sa -e wlan.da \
  | tr '\t' '\n' | grep -Ei '^([0-9a-f]{2}:){5}[0-9a-f]{2}$' \
  | grep -vi '^ff:ff:ff:ff:ff:ff$' | sort | uniq -c | sort -nr | awk '{print $2}' > mac_output.txt
```

### 3. Simulation sans risque
```bash
python3 tester_mac.py --interface wlan0 --file mac_output.txt --dry-run
```

### 4. Test réel sur votre labo
```bash
sudo python3 tester_mac.py \
  --interface wlan0 --file mac_output.txt \
  --lab-ap "TP-Reseau-SalleB" --confirm-lab \
  --ping-target 192.168.1.1 --http-url http://192.168.1.1/ \
  --out results.csv
# mode historique manuel :
sudo python3 tester_mac.py -i wlan0 -f mac_output.txt --lab-ap "TP-Reseau-SalleB" --confirm-lab --manual
```

Résultat : `results.csv` avec `timestamp,lab,interface,mac,applied,ping_ok,http_ok,http_code,mode`.

### 5. Persistance (labo uniquement)
```bash
sudo nmcli connection modify "NOM-DU-WIFI-LABO" 802-11-wireless.cloned-mac-address "MA:CA:DD:RE:SS"
sudo nmcli connection up "NOM-DU-WIFI-LABO"
```

## 🔍 À mettre dans votre rapport

| Vulnérabilité | Explication | Contre-mesure |
|---|---|---|
| MAC seule | En clair, rejouable | Portail captif + token session |
| Pas de session liée | Rejeu trivial | RADIUS / 802.1X, timeout court |
| Usurpation facile | `ip link set` standard | Détection doublons MAC, alertes simultanées |

Pistes opérateur : 802.1X, tokens courts, détection même MAC sur 2 radios / 2 débits, isolation client.

## 🖥️ Version simple pour non-techniques (GUI Flet, pas tkinter)

Pas de terminal à retenir. Interface moderne en français, mode Démo sans risque par défaut.

```bash
# installer Flet une fois (avec pip disponible)
pip install -r requirements-gui.txt
# démo sans risque (pas besoin de sudo)
python3 gui.py
# test réel labo uniquement
sudo python3 gui.py
```

Dans la fenêtre :
1. **Étape 1** : choisissez l'interface (liste auto) + bouton 📂 pour le fichier MACs + nom du labo
2. **Étape 2** : laissez `Mode Démo` coché pour débuter (simule 5 adresses, ne touche à rien)
3. Cliquez **▶ Lancer** -> progression + ✅/❌ par carte, journal simple en bas
4. Pour le vrai test labo : décochez Démo, cochez la case d'autorisation, relancez avec sudo. Bouton ↩ pour restaurer.

## 📁 Structure

```
.
├── README.md
├── tester_mac.py       # Script v2 (argparse, test auto, restore)
├── gui.py              # GUI Flet jolie pour non-techniques (mode démo par défaut)
├── requirements-gui.txt # flet uniquement
├── .gitignore          # ignore pcap, mac_output*.txt, results.csv
└── results.csv         # Généré (non versionné)
```
