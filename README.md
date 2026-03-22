# wifizone-bypass
PoC: passive MAC capture via tshark + spoofing script to expose WiFi zone auth flaws.

# 📡 WiFi Zone MAC Address Tester

> **Projet académique** — Démonstration des limites de sécurité des systèmes d'authentification par adresse MAC dans les WiFi zones africaines.

---

## 🎯 Contexte et objectif

Les **WiFi zones** sont des points d'accès communautaires très répandus en Afrique subsaharienne. Des particuliers mettent à disposition un accès internet contre un forfait payant (hebdomadaire ou mensuel). L'authentification des utilisateurs repose uniquement sur leur **adresse MAC** — l'identifiant matériel de leur carte réseau.

Ce projet universitaire démontre que cette méthode d'authentification présente une **faille de sécurité critique** : une adresse MAC peut être capturée passivement sur le réseau, puis usurpée pour accéder au service sans autorisation.

> ⚠️ **Avertissement légal et éthique** : Ce projet est réalisé dans un cadre **strictement educatif**. L'utilisation de ces techniques sur des réseaux sans autorisation explicite est illégale. L'objectif est de sensibiliser aux limites des systèmes d'authentification par adresse MAC.

---

## 🛠️ Prérequis

- Système Linux (Kali, Ubuntu, Debian…)
- `tshark` (paquet `wireshark-cli`)
- `python3`
- `NetworkManager` (`nmcli`)
- Droits **root** (`sudo`)

```bash
sudo apt install tshark python3
```

---

## ⚙️ Fonctionnement — Étape par étape

### Étape 1 — Capture du trafic réseau

Utiliser **Wireshark** ou **tshark** pour capturer le trafic sur l'interface réseau et enregistrer le fichier `.pcapng`.

### Étape 2 — Extraction des adresses MAC

La commande suivante extrait toutes les adresses MAC sources et destinations depuis la capture, les trie et supprime les doublons :

```bash
tshark -r sniffing-file.pcapng -T fields -e eth.src -e eth.dst \
  | tr '\t' '\n' \
  | sort -u > mac_output.txt
```

**Résultat** : un fichier `mac_output.txt` contenant une adresse MAC par ligne.

### Étape 3 — Test des adresses MAC

Le script Python `tester_mac.py` applique chaque adresse MAC extraite sur l'interface réseau, puis attend que l'utilisateur vérifie manuellement si la connexion fonctionne.

```bash
sudo python3 tester_mac.py
```

**Fonctionnement du script :**
1. Vérifie les droits root et l'existence du fichier `mac_output.txt`
2. Pour chaque adresse MAC de la liste :
   - Désactive l'interface réseau
   - Applique la nouvelle adresse MAC
   - Réactive l'interface
   - **Pause** — l'utilisateur teste manuellement (ping, navigateur…)
   - Passe à la suivante sur appui d'`Entrée`

---

## 📄 Script principal — `tester_mac.py`

---

## 💾 (Optionnel) Persistance de l'adresse MAC

Si une adresse MAC fonctionnelle est trouvée, il est possible de l'associer de façon permanente à un réseau WiFi spécifique via NetworkManager :

```bash
sudo nmcli connection modify "NOM-DU-WIFI" 802-11-wireless.cloned-mac-address "MA:CA:DD:RE:SS"
sudo nmcli connection up "NOM-DU-WIFI"
```

Remplacer `NOM-DU-WIFI` par le SSID du réseau et `MA:CA:DD:RE:SS` par l'adresse MAC retenue.

---

## 🔍 Limites de sécurité démontrées

| Vulnérabilité | Explication |
|---|---|
| **Authentification par MAC uniquement** | L'adresse MAC transite en clair sur le réseau et peut être capturée passivement |
| **Absence de chiffrement de la session** | Aucun token ou session sécurisée n'est lié à l'utilisateur |
| **Usurpation triviale** | Changer son adresse MAC est une opération standard sous Linux, sans matériel spécial |

### Recommandations pour les opérateurs de WiFi zones

- Combiner l'authentification MAC avec un **portail captif** (login/mot de passe)
- Implémenter un système de **tokens de session** côté serveur
- Utiliser **802.1X** (authentification RADIUS) pour les déploiements plus avancés
- Limiter la durée de validité des sessions et détecter les connexions simultanées

---

## 📁 Structure du projet

```
.
├── README.md
├── tester_mac.py       # Script principal de test
└── mac_output.txt      # Généré par tshark (non versionné)
```

---

## 👨‍🎓 Informations académiques

- **Type** : Projet universitaire de sécurité réseau
- **Objectif pédagogique** : Démontrer les failles d'une authentification basée sur l'adresse MAC
- **Cadre** : Éthique et légal — réalisé avec l'accord du corps enseignant
