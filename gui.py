#!/usr/bin/env python3
"""
GUI jolie (Flet, pas tkinter) — pour profils non-techniques, LABO UNIQUEMENT.
Français / English + mode sombre / clair (boutons en haut à droite).

  sudo .venv/bin/python gui.py   # requis : capture + change la MAC + teste le vrai internet

Principe :
  0. Capturer le trafic de VOTRE labo (tshark) -> MACs extraites auto
  1. Choisir interface + fichier MACs (boutons, pas de terminal)
  2. Écrire le SSID Cible + cocher la case d'autorisation
  3. Gros bouton Lancer -> barre de progression -> ✅/❌ par MAC (test HTTP façon navigateur)
  4. Restauration auto de votre MAC à la fin.
"""
from __future__ import annotations

import csv
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

try:
    import flet as ft
except ImportError:
    raise SystemExit("Flet manquant : pip install -r requirements-gui.txt  (pip install flet)")

# Réutilise la logique robuste du CLI (validation, filtre, restore, test)
import tester_mac as core


STRINGS = {
    "fr": {
        "app_title": "WiFi Labo — Testeur MAC",
        "app_sub": "Labo autorisé uniquement. Le test change votre MAC puis vérifie le vrai internet (HTTP façon navigateur).",
        "s0_title": "Étape 0 — Capturer VOTRE labo (optionnel)",
        "s0_hint": "Restez sur votre AP de labo. La capture remplit le fichier MACs toute seule.",
        "dur_label": "Durée capture (s)",
        "btn_capture": "● Capturer",
        "btn_stop": "⏹ Stop",
        "cap_idle": "Pas de capture pour l'instant.",
        "s1_title": "Étape 1 — Où tester ?",
        "iface_label": "Interface WiFi",
        "lab_label": "SSID Cible (ex : TP-SalleB)",
        "file_label": "Fichier MACs (chemin, modifiable à la main)",
        "btn_choose": "📂 Choisir un fichier MACs",
        "s2_title": "Étape 2 — Lancer le vrai test",
        "http_label": "Test : curl google.com (modifiable)",
        "confirm_label": "Je confirme tester UNIQUEMENT mon propre labo autorisé",
        "s2_hint": "Exige sudo + case cochée. Ex : sudo .venv/bin/python gui.py",
        "btn_run": "▶ Lancer",
        "btn_restore": "↩ Restaurer mon MAC",
        "results_title": "Résultats :",
        "journal_title": "Journal (lignes $ = commandes exactes exécutées) :",
        "footer": "Pédagogie : une MAC seule ne protège rien → portail captif, sessions, 802.1X.",
        "status_ready": "Choisissez interface + fichier, puis Lancer.",
        "theme_to_dark": "Passer en mode sombre",
        "theme_to_light": "Passer en mode clair",
        "btn_use": "Utiliser",
        "pick_imported": "Fichier importé ✅ : {name} -> {path} — cliquez sur Lancer.",
        "pick_chosen": "Fichier choisi ✅ : {name} — cliquez sur Lancer.",
        "pick_nopath": "⚠️ « {name} » : chemin client inaccessible au serveur. Copiez le fichier vers {cwd} ou /tmp et corrigez le chemin à la main.",
        "pick_fail": "Oups ❌ import : {ex} — corrigez le chemin à la main.",
        "picker_na": "⚠️ Sélecteur indisponible ({ex}). Tapez le chemin à la main ex : /tmp/mac_output.txt",
        "cap_need_confirm": "⛔ Cochez la case + SSID Cible avant de capturer (labo autorisé uniquement).",
        "cap_need_sudo": "⛔ Capture : relancez avec sudo : sudo .venv/bin/python gui.py",
        "cap_no_tshark": "❌ tshark introuvable. Installez : sudo apt install tshark",
        "cap_bad_dur": "❌ Durée invalide (nombre de secondes, ex : 30).",
        "cap_busy": "⏳ Capture déjà en cours…",
        "cap_stop_req": "⏹ Arrêt demandé…",
        "cap_idle2": "Pas de capture en cours.",
        "cap_start": "● Capture sur {iface} pendant ~{dur}s -> {pcap} …",
        "cap_progress": "● Capture en cours… {elapsed}s / ~{dur}s -> {pcap} (⏹ pour arrêter)",
        "cap_stopped": "⏹ Capture arrêtée : {pcap} — extraction…",
        "cap_fail": "❌ Capture échouée (code {rc}). {out}",
        "cap_fail_log": "Échec capture : {out}",
        "cap_done": "✅ Capture terminée : {pcap} — extraction des MACs…",
        "cap_extracted": "✅ {kept} MACs extraites de {pcap} -> {fname} ({rejected} ignorées). Cliquez ▶ Lancer.",
        "extract_log": "Extraction : {kept} gardées, {rejected} rejetées -> {path}",
        "cap_zero": "⚠️ 0 MAC extraite de {pcap}. Rapprochez-vous du labo / augmentez la durée.",
        "cap_err": "Oups ❌ capture : {e}",
        "file_notfound": "❌ Fichier introuvable : {path}. Corrigez le chemin (ex : /tmp/mac_output.txt) ou utilisez 📂.",
        "tested_log": "Testé : {path} (cwd={cwd})",
        "file_ok": "Fichier OK : {name} — chargement…",
        "no_macs": "❌ Aucune MAC valide dans le fichier.",
        "rejected_n": "{n} lignes ignorées (ex : {ex})",
        "test_need_confirm": "⛔ Cochez la case + indiquez le nom du labo (obligatoire).",
        "test_need_sudo": "⛔ Relancez avec sudo : sudo .venv/bin/python gui.py",
        "test_start": "Test réel sur « {lab} » — {n} adresses… ne fermez pas.",
        "test_busy": "⏳ Test déjà en cours… (⏹ Stop pour arrêter)",
        "test_stop_req": "⏹ Arrêt demandé… fin de la MAC en cours puis restauration.",
        "test_norun": "Pas de test en cours.",
        "test_progress": "Essai {i}/{n} : {mac} … (⏹ Stop pour arrêter)",
        "apply_fail": "échec application — {detail}",
        "test_interrupted": "⏹ Test interrompu à {i}/{n} — restauration…",
        "test_stopped": "⏹ Test arrêté — MAC d'origine restaurée.",
        "test_done": "Terminé ✅ — résultats dans results.csv. MAC d'origine restaurée 👍",
        "test_err": "Oups ❌ : {e}",
        "res_ok": "✅ internet OK",
        "res_portal": "⚠️ portail captif",
        "res_ko": "❌ pas d'internet",
        "apply_need_sudo": "⛔ Relancez avec sudo pour appliquer une MAC.",
        "apply_start": "Application de {mac} sur {iface}… (profil NM + reconnect)",
        "use_log": "Utiliser {mac} : {detail}",
        "apply_ok": "✅ {mac} active sur {iface} — surfez ! ({detail})",
        "apply_ko": "❌ {mac} non appliquée : {detail}",
        "restore_prefix": "Restaurer : ",
    },
    "en": {
        "app_title": "WiFi Labo — MAC Tester",
        "app_sub": "Authorized lab only. The test changes your MAC then checks real internet (browser-style HTTP).",
        "s0_title": "Step 0 — Capture YOUR lab (optional)",
        "s0_hint": "Stay on your lab AP. The capture fills the MAC file by itself.",
        "dur_label": "Capture duration (s)",
        "btn_capture": "● Capture",
        "btn_stop": "⏹ Stop",
        "cap_idle": "No capture yet.",
        "s1_title": "Step 1 — Where to test?",
        "iface_label": "WiFi interface",
        "lab_label": "Target SSID (e.g. TP-SalleB)",
        "file_label": "MACs file (path, editable by hand)",
        "btn_choose": "📂 Choose a MACs file",
        "s2_title": "Step 2 — Run the real test",
        "http_label": "Test: curl google.com (editable)",
        "confirm_label": "I confirm testing ONLY my own authorized lab",
        "s2_hint": "Requires sudo + checked box. E.g. sudo .venv/bin/python gui.py",
        "btn_run": "▶ Run",
        "btn_restore": "↩ Restore my MAC",
        "results_title": "Results:",
        "journal_title": "Log ($ lines = exact commands run):",
        "footer": "Lesson: a MAC alone protects nothing → captive portal, sessions, 802.1X.",
        "status_ready": "Choose interface + file, then Run.",
        "theme_to_dark": "Switch to dark mode",
        "theme_to_light": "Switch to light mode",
        "btn_use": "Use",
        "pick_imported": "File imported ✅: {name} -> {path} — click Run.",
        "pick_chosen": "File chosen ✅: {name} — click Run.",
        "pick_nopath": "⚠️ \"{name}\": client path unreachable from server. Copy the file to {cwd} or /tmp and fix the path by hand.",
        "pick_fail": "Oops ❌ import: {ex} — fix the path by hand.",
        "picker_na": "⚠️ Picker unavailable ({ex}). Type the path by hand e.g. /tmp/mac_output.txt",
        "cap_need_confirm": "⛔ Check the box + Target SSID before capturing (authorized lab only).",
        "cap_need_sudo": "⛔ Capture: relaunch with sudo: sudo .venv/bin/python gui.py",
        "cap_no_tshark": "❌ tshark not found. Install: sudo apt install tshark",
        "cap_bad_dur": "❌ Invalid duration (seconds, e.g. 30).",
        "cap_busy": "⏳ Capture already running…",
        "cap_stop_req": "⏹ Stop requested…",
        "cap_idle2": "No capture running.",
        "cap_start": "● Capturing on {iface} for ~{dur}s -> {pcap} …",
        "cap_progress": "● Capturing… {elapsed}s / ~{dur}s -> {pcap} (⏹ to stop)",
        "cap_stopped": "⏹ Capture stopped: {pcap} — extracting…",
        "cap_fail": "❌ Capture failed (code {rc}). {out}",
        "cap_fail_log": "Capture failed: {out}",
        "cap_done": "✅ Capture done: {pcap} — extracting MACs…",
        "cap_extracted": "✅ {kept} MACs extracted from {pcap} -> {fname} ({rejected} ignored). Click ▶ Run.",
        "extract_log": "Extraction: {kept} kept, {rejected} rejected -> {path}",
        "cap_zero": "⚠️ 0 MACs extracted from {pcap}. Move closer to the lab / increase duration.",
        "cap_err": "Oops ❌ capture: {e}",
        "file_notfound": "❌ File not found: {path}. Fix the path (e.g. /tmp/mac_output.txt) or use 📂.",
        "tested_log": "Tried: {path} (cwd={cwd})",
        "file_ok": "File OK: {name} — loading…",
        "no_macs": "❌ No valid MAC in the file.",
        "rejected_n": "{n} lines ignored (e.g. {ex})",
        "test_need_confirm": "⛔ Check the box + enter the lab name (required).",
        "test_need_sudo": "⛔ Relaunch with sudo: sudo .venv/bin/python gui.py",
        "test_start": "Real test on \"{lab}\" — {n} addresses… don't close.",
        "test_busy": "⏳ Test already running… (⏹ Stop to quit)",
        "test_stop_req": "⏹ Stop requested… finishing current MAC then restoring.",
        "test_norun": "No test running.",
        "test_progress": "Try {i}/{n}: {mac} … (⏹ Stop to quit)",
        "apply_fail": "apply failed — {detail}",
        "test_interrupted": "⏹ Test interrupted at {i}/{n} — restoring…",
        "test_stopped": "⏹ Test stopped — original MAC restored.",
        "test_done": "Done ✅ — results in results.csv. Original MAC restored 👍",
        "test_err": "Oops ❌: {e}",
        "res_ok": "✅ internet OK",
        "res_portal": "⚠️ captive portal",
        "res_ko": "❌ no internet",
        "apply_need_sudo": "⛔ Relaunch with sudo to apply a MAC.",
        "apply_start": "Applying {mac} on {iface}… (NM profile + reconnect)",
        "use_log": "Use {mac}: {detail}",
        "apply_ok": "✅ {mac} active on {iface} — browse! ({detail})",
        "apply_ko": "❌ {mac} not applied: {detail}",
        "restore_prefix": "Restore: ",
    },
}


def list_interfaces() -> list[str]:
    net = Path("/sys/class/net")
    if not net.exists():
        return ["wlan0"]
    ifaces = [p.name for p in net.iterdir() if p.is_dir() and p.name != "lo"]
    return sorted(ifaces) or ["wlan0"]


def chown_to_invoker(path: Path) -> None:
    """Sous sudo, rend le fichier à l'utilisateur d'origine (évite les fichiers root-only dans son home)."""
    try:
        uid = os.environ.get("SUDO_UID")
        gid = os.environ.get("SUDO_GID")
        if uid is None:
            return
        os.chown(path, int(uid), int(gid) if gid is not None else -1)
    except Exception:
        pass


def main(page: ft.Page):
    lang = {"cur": "fr"}

    def T(key: str, **kw) -> str:
        s = STRINGS[lang["cur"]].get(key, key)
        return s.format(**kw) if kw else s

    page.title = T("app_title")
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed="indigo")
    page.padding = 24
    page.scroll = ft.ScrollMode.AUTO

    # --- État ---
    results_view = ft.ListView(spacing=6, padding=6, height=300)
    progress = ft.ProgressBar(visible=False, color=ft.Colors.INDIGO)
    status = ft.Text(T("status_ready"), size=14)
    log_box = ft.Text("", size=12, color=ft.Colors.GREY)

    # En-tête : titre + boutons thème / langue
    title_t = ft.Text(T("app_title"), size=24, weight=ft.FontWeight.BOLD)
    sub_t = ft.Text(T("app_sub"), color=ft.Colors.GREY, size=13)
    theme_btn = ft.IconButton(icon=ft.Icons.DARK_MODE, tooltip=T("theme_to_dark"))
    lang_btn = ft.TextButton(content="EN", tooltip="Language / Langue")

    def toggle_theme(_):
        if page.theme_mode == ft.ThemeMode.DARK:
            page.theme_mode = ft.ThemeMode.LIGHT
            theme_btn.icon = ft.Icons.DARK_MODE
        else:
            page.theme_mode = ft.ThemeMode.DARK
            theme_btn.icon = ft.Icons.LIGHT_MODE
        apply_lang()

    def toggle_lang(_):
        lang["cur"] = "en" if lang["cur"] == "fr" else "fr"
        core.LANG = lang["cur"]  # détails techniques du core dans la même langue
        apply_lang()

    theme_btn.on_click = toggle_theme
    lang_btn.on_click = toggle_lang

    ifaces = list_interfaces()
    dd_iface = ft.Dropdown(label=T("iface_label"), options=[ft.DropdownOption(i) for i in ifaces],
                           value=ifaces[0] if ifaces else "wlan0", width=260)
    tf_lab = ft.TextField(label=T("lab_label"), width=320, value="")
    tf_file = ft.TextField(label=T("file_label"), value="mac_output.txt", width=420)
    chk_confirm = ft.Checkbox(label=T("confirm_label"), value=False)
    tf_http = ft.TextField(label=T("http_label"), value="http://www.google.com", width=420)

    # --- Capture intégrée (Étape 0) ---
    tf_duration = ft.TextField(label=T("dur_label"), value="30", width=160)
    cap_status = ft.Text(T("cap_idle"), size=13)
    cap_progress = ft.ProgressBar(visible=False, color=ft.Colors.INDIGO)
    cap_state: dict = {"proc": None, "stop": False}
    btn_capture = ft.FilledTonalButton("● Capturer", icon="fiber_manual_record")
    btn_stopcap = ft.OutlinedButton(T("btn_stop"), icon="stop")
    btn_capture.content = T("btn_capture")

    s0_title = ft.Text(T("s0_title"), weight=ft.FontWeight.BOLD)
    s0_hint = ft.Text(T("s0_hint"), size=12, color=ft.Colors.GREY)
    s1_title = ft.Text(T("s1_title"), weight=ft.FontWeight.BOLD)
    btn_choose = ft.FilledTonalButton(T("btn_choose"), icon="folder_open")
    s2_title = ft.Text(T("s2_title"), weight=ft.FontWeight.BOLD)
    s2_hint = ft.Text(T("s2_hint"), size=12, color=ft.Colors.GREY)
    btn_run = ft.FilledButton(T("btn_run"), icon="play_arrow", height=48, expand=True)
    btn_stop = ft.OutlinedButton(T("btn_stop"), icon="stop", height=48)
    btn_restore = ft.OutlinedButton(T("btn_restore"), icon="refresh", height=48)
    results_title = ft.Text(T("results_title"), weight=ft.FontWeight.BOLD)
    journal_title = ft.Text(T("journal_title"), weight=ft.FontWeight.BOLD)
    footer_t = ft.Text(T("footer"), size=12, color=ft.Colors.GREY)

    def apply_lang():
        """Réapplique la langue (+ icônes thème) à toute l'interface statique."""
        page.title = T("app_title")
        title_t.value = T("app_title")
        sub_t.value = T("app_sub")
        s0_title.value = T("s0_title")
        s0_hint.value = T("s0_hint")
        tf_duration.label = T("dur_label")
        btn_capture.content = T("btn_capture")
        btn_stopcap.content = T("btn_stop")
        dd_iface.label = T("iface_label")
        tf_lab.label = T("lab_label")
        tf_file.label = T("file_label")
        btn_choose.content = T("btn_choose")
        s1_title.value = T("s1_title")
        s2_title.value = T("s2_title")
        tf_http.label = T("http_label")
        chk_confirm.label = T("confirm_label")
        s2_hint.value = T("s2_hint")
        btn_run.content = T("btn_run")
        btn_stop.content = T("btn_stop")
        btn_restore.content = T("btn_restore")
        results_title.value = T("results_title")
        journal_title.value = T("journal_title")
        footer_t.value = T("footer")
        lang_btn.content = "FR" if lang["cur"] == "en" else "EN"
        if page.theme_mode == ft.ThemeMode.DARK:
            theme_btn.icon = ft.Icons.LIGHT_MODE
            theme_btn.tooltip = T("theme_to_light")
        else:
            theme_btn.icon = ft.Icons.DARK_MODE
            theme_btn.tooltip = T("theme_to_dark")
        status.value = T("status_ready")
        cap_status.value = T("cap_idle")
        page.update()

    def find_tshark() -> str | None:
        for tool in ("tshark", "dumpcap"):
            p = shutil.which(tool)
            if p:
                return p
        return None

    def append_log(msg: str):
        log_box.value = (log_box.value + "\n" + msg).strip()[-2000:]
        page.update()

    # Journal des commandes exactes : chaque commande système exécutée par le
    # core est affichée avec "$ " (sauf le polling DHCP "ip -4 ...", trop bavard).
    def _journal_cmd(cmd: list[str]):
        if len(cmd) >= 2 and cmd[0] == "ip" and cmd[1] == "-4":
            return
        append_log("$ " + " ".join(cmd))

    core.COMMAND_LOGGER = _journal_cmd

    # État du test (pour le bouton Stop)
    test_state: dict = {"running": False, "stop": False}

    def set_status(msg: str):
        status.value = msg
        page.update()

    def apply_mac(mac: str):
        """Applique une MAC qui fonctionne, en un clic (thread pour ne pas figer l'UI).
        Passe par le profil NetworkManager (sinon NM restaure la MAC d'usine
        au reconnect) et affiche la MAC réellement lue après application."""
        def _do():
            try:
                if os.geteuid() != 0:
                    set_status(T("apply_need_sudo"))
                    return
                # Sauvegarde l'originale AVANT (sinon Restaurer ne saura pas quoi remettre)
                core.save_original_mac(dd_iface.value)
                set_status(T("apply_start", mac=mac, iface=dd_iface.value))
                ok, detail = core.apply_mac_persistent(dd_iface.value, mac)
                append_log(T("use_log", mac=mac, detail=detail))
                if ok:
                    set_status(T("apply_ok", mac=mac, iface=dd_iface.value, detail=detail))
                else:
                    set_status(T("apply_ko", mac=mac, detail=detail))
            except Exception as e:
                set_status(T("test_err", e=e))
                try:
                    core.ensure_link_up(dd_iface.value)
                except Exception:
                    pass
        threading.Thread(target=_do, daemon=True).start()

    def add_result(mac: str, ok: bool | None, detail: str, show_apply: bool = False):
        icon = ft.Icons.CHECK_CIRCLE if ok is True else (ft.Icons.CANCEL if ok is False else ft.Icons.INFO)
        color = ft.Colors.GREEN if ok is True else (ft.Colors.RED if ok is False else ft.Colors.GREY)
        trailing = (ft.FilledTonalButton(T("btn_use"), icon="check",
                                         on_click=lambda _, m=mac: apply_mac(m))
                    if show_apply else None)
        tile = ft.ListTile(leading=ft.Icon(icon, color=color),
                           title=ft.Text(mac, weight=ft.FontWeight.BOLD),
                           subtitle=ft.Text(detail, size=12),
                           trailing=trailing)
        results_view.controls.append(ft.Card(content=tile))
        page.update()

    # --- File picker (Flet 1.0 : pick_files est async).
    # En mode navigateur (sudo), le chemin du poste client n'existe pas côté
    # serveur -> on récupère le contenu (with_data) et on le sauve en local.
    # + champ chemin modifiable à la main en secours (toujours fonctionnel).
    def on_pick(e: ft.FilePickerResultEvent):
        try:
            if not e.files:
                return
            f = e.files[0]
            data = getattr(f, "bytes", None)
            if data:
                local = Path("macs_gui_import.txt")
                local.write_bytes(data)
                tf_file.value = str(local.resolve())
                set_status(T("pick_imported", name=f.name, path=local.resolve()))
            elif getattr(f, "path", None) and Path(f.path).exists():
                tf_file.value = f.path
                set_status(T("pick_chosen", name=f.name))
            else:
                # Chemin client inaccessible au serveur (cas navigateur/sudo)
                tf_file.value = f.name or tf_file.value
                set_status(T("pick_nopath", name=f.name, cwd=Path.cwd()))
        except Exception as ex:
            set_status(T("pick_fail", ex=ex))
        page.update()

    picker = ft.FilePicker(on_result=on_pick)
    page.services.append(picker)

    async def choose_file(_):
        try:
            await picker.pick_files(allowed_extensions=["txt"], with_data=True)
        except Exception as ex:
            set_status(T("picker_na", ex=ex))
            page.update()

    def extract_macs_from_pcap(pcap: Path, out: Path) -> tuple[int, int]:
        """Extrait wlan.sa/da via tshark (sans shell), filtre + déduplique, écrit `out`.
        Retourne (nb_gardées, nb_rejetées)."""
        tool = find_tshark()
        if tool is None:
            raise RuntimeError("tshark introuvable : sudo apt install tshark")
        # Champs WiFi d'abord, repli ethernet si besoin (managed)
        field_sets = (["wlan.sa", "wlan.da"], ["eth.src", "eth.dst"])
        raw = ""
        for fields in field_sets:
            cmd = [tool, "-r", str(pcap), "-T", "fields"]
            for fl in fields:
                cmd += ["-e", fl]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip():
                raw = r.stdout
                break
        if not raw.strip():
            return 0, 0
        seen: set[str] = set()
        kept: list[str] = []
        rejected = 0
        for token in re.split(r"[\s\t,;]+", raw):
            token = token.strip().lower()
            if not token:
                continue
            ok, _ = core.valid_mac(token)
            if not ok:
                rejected += 1
                continue
            if token not in seen:
                seen.add(token)
                kept.append(token)
        out.write_text("\n".join(kept) + ("\n" if kept else ""))
        return len(kept), rejected

    def set_cap_status(msg: str):
        cap_status.value = msg
        page.update()

    def start_capture(_):
        if not chk_confirm.value or not tf_lab.value.strip():
            set_cap_status(T("cap_need_confirm"))
            return
        if os.geteuid() != 0:
            set_cap_status(T("cap_need_sudo"))
            return
        tool = find_tshark()
        if tool is None:
            set_cap_status(T("cap_no_tshark"))
            return
        try:
            dur = int((tf_duration.value or "30").strip())
        except ValueError:
            set_cap_status(T("cap_bad_dur"))
            return
        dur = max(5, min(600, dur))
        if cap_state.get("proc") is not None:
            set_cap_status(T("cap_busy"))
            return
        threading.Thread(target=worker_capture, args=(dur,), daemon=True).start()

    def stop_capture(_):
        cap_state["stop"] = True
        proc = cap_state.get("proc")
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
            set_cap_status(T("cap_stop_req"))
        else:
            set_cap_status(T("cap_idle2"))

    def worker_capture(dur: int):
        cap_state["stop"] = False
        cap_progress.visible = True
        page.update()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        # /tmp : dumpcap/tshark lancé en root abandonne ses privilèges pour la
        # capture ; il ne peut donc pas écrire dans le home de l'utilisateur.
        pcap = Path(tempfile.gettempdir()) / f"capture-{stamp}.pcapng"
        try:
            set_cap_status(T("cap_start", iface=dd_iface.value, dur=dur, pcap=pcap.name))
            append_log(f"tshark -i {dd_iface.value} -a duration:{dur} -w {pcap.name}")
            proc = subprocess.Popen(
                [find_tshark(), "-i", dd_iface.value, "-a", f"duration:{dur}", "-w", str(pcap)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            cap_state["proc"] = proc
            start = time.time()
            while proc.poll() is None:
                if cap_state["stop"]:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                    break
                elapsed = int(time.time() - start)
                set_cap_status(T("cap_progress", elapsed=elapsed, dur=dur, pcap=pcap.name))
                time.sleep(1)
            rc = proc.poll()
            cap_state["proc"] = None
            if cap_state["stop"]:
                set_cap_status(T("cap_stopped", pcap=pcap.name))
            elif rc != 0 or not pcap.exists():
                out = ""
                try:
                    out = (proc.stdout.read() or "")[-500:] if proc.stdout else ""
                except Exception:
                    pass
                set_cap_status(T("cap_fail", rc=rc, out=out))
                append_log(T("cap_fail_log", out=out))
                return
            else:
                set_cap_status(T("cap_done", pcap=pcap.name))
            # Extraction auto vers le champ fichier
            raw_out = (tf_file.value or "").strip() or "mac_output.txt"
            out_path = Path(raw_out).expanduser()
            if not out_path.is_absolute():
                out_path = Path.cwd() / out_path
            kept, rejected = extract_macs_from_pcap(pcap, out_path)
            chown_to_invoker(out_path)
            tf_file.value = str(out_path)
            if kept:
                set_cap_status(T("cap_extracted", kept=kept, pcap=pcap.name, fname=out_path.name, rejected=rejected))
                append_log(T("extract_log", kept=kept, rejected=rejected, path=out_path))
            else:
                set_cap_status(T("cap_zero", pcap=pcap.name))
            page.update()
        except Exception as e:
            set_cap_status(T("cap_err", e=e))
        finally:
            cap_state["proc"] = None
            # La capture ne doit jamais laisser l'interface down
            try:
                core.ensure_link_up(dd_iface.value)
            except Exception:
                pass
            cap_progress.visible = False
            page.update()

    # --- Lancement (thread pour ne pas figer l'UI) ---
    def run_test(_):
        if test_state["running"]:
            set_status(T("test_busy"))
            return
        results_view.controls.clear()
        test_state.update(running=True, stop=False)
        progress.visible = True
        page.update()
        threading.Thread(target=worker, daemon=True).start()

    def stop_test(_):
        if not test_state["running"]:
            set_status(T("test_norun"))
            return
        test_state["stop"] = True
        set_status(T("test_stop_req"))

    def worker():
        out: Path | None = None
        try:
            raw = (tf_file.value or "").strip() or "mac_output.txt"
            path = Path(raw).expanduser()
            if not path.is_absolute():
                path = Path.cwd() / path
            if not path.exists():
                set_status(T("file_notfound", path=path))
                append_log(T("tested_log", path=path, cwd=Path.cwd()))
                return
            set_status(T("file_ok", name=path.name))
            own = core.get_current_mac(dd_iface.value)
            macs, rejected = core.load_macs(path, skip_own=own)
            if not macs:
                set_status(T("no_macs"))
                return
            if rejected:
                append_log(T("rejected_n", n=len(rejected), ex=rejected[0]))

            # --- Test réel labo : garde-fous ---
            if not chk_confirm.value or not tf_lab.value.strip():
                set_status(T("test_need_confirm"))
                return
            if os.geteuid() != 0:
                set_status(T("test_need_sudo"))
                return
            core.save_original_mac(dd_iface.value)
            set_status(T("test_start", lab=tf_lab.value.strip(), n=len(macs)))
            out = Path("results.csv")
            is_new = not out.exists()
            with out.open("a", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["timestamp", "lab", "interface", "mac", "applied", "ping_ok", "http_ok", "http_code", "portal", "detail", "mode"])
                if is_new:
                    w.writeheader()
                for i, mac in enumerate(macs, 1):
                    if test_state["stop"]:
                        append_log(T("test_interrupted", i=i, n=len(macs)))
                        break
                    set_status(T("test_progress", i=i, n=len(macs), mac=mac))
                    # Voie persistante vérifiée (profil NM) : sinon NM restaure
                    # la MAC d'usine et le test se fait avec la mauvaise MAC.
                    applied, apply_detail = core.apply_mac_persistent(dd_iface.value, mac, delay=4.0)
                    if not applied:
                        add_result(mac, False, T("apply_fail", detail=apply_detail))
                        append_log(f"{mac} : {apply_detail}")
                        continue
                    c = core.test_connectivity(tf_http.value.strip(), 4)
                    # Seul le curl google décide (pas de ping : la passerelle répond même sans auth)
                    good = bool(c["http_ok"])
                    if good:
                        label = T("res_ok")
                    elif c.get("portal"):
                        label = T("res_portal")
                    else:
                        label = T("res_ko")
                    add_result(mac, good, f"{label} — {c.get('detail','')}",
                               show_apply=good)
                    w.writerow({"timestamp": datetime.now().isoformat(timespec="seconds"), "lab": tf_lab.value.strip(),
                                "interface": dd_iface.value, "mac": mac, "applied": True,
                                "ping_ok": c["ping_ok"], "http_ok": c["http_ok"], "http_code": c["http_code"],
                                "portal": c.get("portal", ""), "detail": f"[{apply_detail}] {c.get('detail', '')}", "mode": "gui"})
            if test_state["stop"]:
                set_status(T("test_stopped"))
            else:
                set_status(T("test_done"))
            chown_to_invoker(out)
        except Exception as e:  # message simple, pas de traceback effrayant
            set_status(T("test_err", e=e))
        finally:
            test_state["running"] = False
            test_state["stop"] = False
            try:
                core.restore_mac()
            except Exception:
                pass
            # Ceinture + bretelles : ne jamais laisser l'interface down
            try:
                core.ensure_link_up(dd_iface.value)
            except Exception:
                pass
            # Le CSV a été écrit en root : le rendre à l'utilisateur
            try:
                if out is not None and out.exists():
                    chown_to_invoker(out)
            except Exception:
                pass
            progress.visible = False
            page.update()

    def restore_now(_):
        ok, msg = core.restore_mac(dd_iface.value)
        append_log(T("restore_prefix") + msg)
        set_status(("✅ " if ok else "❌ ") + msg)
        try:
            core.ensure_link_up(dd_iface.value)
        except Exception:
            pass

    # --- Layout joli, en cartes ---
    btn_capture.on_click = start_capture
    btn_stopcap.on_click = stop_capture
    btn_choose.on_click = choose_file
    btn_run.on_click = run_test
    btn_stop.on_click = stop_test
    btn_restore.on_click = restore_now
    page.add(
        ft.Row([
            ft.Column([title_t, sub_t], expand=True),
            theme_btn,
            lang_btn,
        ]),
        ft.Card(content=ft.Container(
            content=ft.Column([
                s0_title,
                s0_hint,
                ft.Row([
                    tf_duration,
                    btn_capture,
                    btn_stopcap,
                ], wrap=True),
                cap_progress, cap_status,
            ]), padding=16)),
        ft.Card(content=ft.Container(
            content=ft.Column([
                s1_title,
                ft.Row([dd_iface, tf_lab], wrap=True),
                ft.Row([btn_choose,
                        tf_file], wrap=True),
            ]), padding=16)),
        ft.Card(content=ft.Container(
            content=ft.Column([
                s2_title,
                tf_http,
                chk_confirm,
                s2_hint,
            ]), padding=16)),
        ft.Row([
            btn_run,
            btn_stop,
            btn_restore,
        ]),
        progress, status,
        results_title,
        ft.Container(content=results_view, border_radius=12, bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST, padding=4),
        journal_title, log_box,
        footer_t,
    )


WEB_PORT = 8550


def _print_web_url():
    """Affiche l'adresse du mode navigateur pour que l'utilisateur ne soit pas perdu."""
    print("=" * 62)
    print(f"🌐 Mode navigateur : ouvrez http://localhost:{WEB_PORT} dans votre navigateur")
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("8.8.8.8", 80))  # aucun paquet envoyé, juste pour connaître l'IP locale
        print(f"   Depuis un autre appareil du réseau : http://{s.getsockname()[0]}:{WEB_PORT}")
        s.close()
    except Exception:
        pass
    print("   Laissez ce terminal ouvert pendant l'utilisation.")
    print("=" * 62, flush=True)


if __name__ == "__main__":
    # FLET_GUI=web force le navigateur (AUCUN download), =desktop force la fenêtre.
    # Sinon : en sudo on tente la fenêtre native d'abord — ce qui télécharge le
    # client flet-desktop dans le cache de root LA PREMIÈRE FOIS (normal, officiel,
    # réutilisé ensuite) — avec repli navigateur si échec ; hors sudo, fenêtre.
    force = os.environ.get("FLET_GUI", "").strip().lower()
    if force == "web":
        _print_web_url()
        ft.run(main, view=ft.AppView.WEB_BROWSER, port=WEB_PORT)
    elif force == "desktop" or os.geteuid() != 0:
        ft.run(main)
    else:
        try:
            ft.run(main)
        except Exception as e:
            print(f"Fenêtre desktop indisponible ({e}).")
            _print_web_url()
            ft.run(main, view=ft.AppView.WEB_BROWSER, port=WEB_PORT)
