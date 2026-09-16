#!/usr/bin/env python3
"""
GUI jolie (Flet, pas tkinter) — pour profils non-techniques, LABO UNIQUEMENT.

  pip install -r requirements-gui.txt
  python3 gui.py            # mode démo sans risque par défaut
  sudo python3 gui.py       # requis seulement pour le test réel labo

Principe simplifié :
  1. Choisir interface + fichier MACs (boutons, pas de terminal)
  2. Écrire le nom du labo + cocher la case d'autorisation
  3. Gros bouton Lancer -> barre de progression -> ✅/❌ par MAC
  4. Restauration auto de votre MAC à la fin.
"""
from __future__ import annotations

import csv
import os
import threading
from datetime import datetime
from pathlib import Path

try:
    import flet as ft
except ImportError:
    raise SystemExit("Flet manquant : pip install -r requirements-gui.txt  (pip install flet)")

# Réutilise la logique robuste du CLI (validation, filtre, restore, test)
import tester_mac as core


def list_interfaces() -> list[str]:
    net = Path("/sys/class/net")
    if not net.exists():
        return ["wlan0"]
    ifaces = [p.name for p in net.iterdir() if p.is_dir() and p.name != "lo"]
    return sorted(ifaces) or ["wlan0"]


def main(page: ft.Page):
    page.title = "WiFi Labo — Testeur MAC (démo pédagogique)"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed="indigo", use_material3=True)
    page.padding = 24
    page.window_width = 760
    page.window_height = 820
    page.scroll = ft.ScrollMode.AUTO

    # --- État ---
    mac_file = ft.Ref[ft.Text]()
    results_view = ft.ListView(spacing=6, padding=6, height=300)
    progress = ft.ProgressBar(visible=False, color="indigo")
    status = ft.Text("Bienvenue 👋 — commencez en mode Démo, sans risque.", size=14)
    log_box = ft.Text("", size=12, color="grey")

    ifaces = list_interfaces()
    dd_iface = ft.Dropdown(label="Interface WiFi", options=[ft.dropdown.Option(i) for i in ifaces],
                           value=ifaces[0] if ifaces else "wlan0", width=260)
    tf_lab = ft.TextField(label="Nom de votre labo (ex : TP-SalleB)", width=320, value="")
    tf_file = ft.Text(value="Aucun fichier choisi", size=13)
    mac_file.current = tf_file
    chk_confirm = ft.Checkbox(label="Je confirme tester UNIQUEMENT mon propre labo autorisé", value=False)
    sw_demo = ft.Switch(label="Mode Démo sans risque (recommandé pour débuter)", value=True)
    tf_ping = ft.TextField(label="Passerelle de votre labo", value="192.168.1.1", width=220)
    tf_http = ft.TextField(label="Page test de votre labo", value="http://192.168.1.1/", width=320)

    picked_path: dict = {"path": "mac_output.txt"}

    def append_log(msg: str):
        log_box.value = (log_box.value + "\n" + msg).strip()[-2000:]
        page.update()

    def set_status(msg: str):
        status.value = msg
        page.update()

    def add_result(mac: str, ok: bool | None, detail: str):
        icon = "check_circle" if ok is True else ("cancel" if ok is False else "info")
        color = "green" if ok is True else ("red" if ok is False else "grey")
        results_view.controls.append(
            ft.Card(content=ft.ListTile(leading=ft.Icon(icon, color=color),
                                        title=ft.Text(mac, weight="bold"),
                                        subtitle=ft.Text(detail, size=12)))
        )
        page.update()

    # --- File picker ---
    picker = ft.FilePicker()
    page.overlay.append(picker)

    def on_pick(e: ft.FilePickerResultEvent):
        if e.files:
            picked_path["path"] = e.files[0].path
            tf_file.value = e.files[0].path
            set_status(f"Fichier choisi ✅ : {e.files[0].name} — cliquez sur Lancer.")
        page.update()

    picker.on_result = on_pick

    # --- Lancement (thread pour ne pas figer l'UI) ---
    def run_test(_):
        results_view.controls.clear()
        progress.visible = True
        page.update()
        threading.Thread(target=worker, daemon=True).start()

    def worker():
        try:
            path = Path(picked_path["path"])
            if not path.exists():
                set_status("❌ Fichier introuvable. Cliquez sur « Choisir un fichier » d'abord.")
                return
            own = core.get_current_mac(dd_iface.value)
            macs, rejected = core.load_macs(path, skip_own=own)
            if sw_demo.value:
                macs = macs[:5]  # démo courte pour non-techniques
                set_status(f"Mode Démo : simulation de {len(macs)} adresses, rien n'est modifié 👍")
                for m in macs:
                    add_result(m, None, "simulé — aucun changement réseau (démo)")
                if rejected:
                    append_log(f"{len(rejected)} lignes ignorées (ex : {rejected[0]})")
                set_status(f"Terminé ✅ — {len(macs)} adresses simulées. Décochez Démo + sudo pour le vrai test labo.")
                return

            # --- Test réel labo : garde-fous ---
            if not chk_confirm.value or not tf_lab.value.strip():
                set_status("⛔ Cochez la case + indiquez le nom du labo (obligatoire).")
                return
            if os.geteuid() != 0:
                set_status("⛔ Relancez avec sudo pour le test réel (le mode Démo marche sans sudo).")
                return
            core.save_original_mac(dd_iface.value)
            set_status(f"Test réel sur « {tf_lab.value.strip()} » — {len(macs)} adresses… ne fermez pas.")
            out = Path("results.csv")
            is_new = not out.exists()
            with out.open("a", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["timestamp", "lab", "interface", "mac", "applied", "ping_ok", "http_ok", "http_code", "mode"])
                if is_new:
                    w.writeheader()
                for i, mac in enumerate(macs, 1):
                    set_status(f"Essai {i}/{len(macs)} : {mac} …")
                    ok = core.set_mac(dd_iface.value, mac, reconnect=True, delay=4.0)
                    if not ok:
                        add_result(mac, False, "échec changement — voir log")
                        continue
                    c = core.test_connectivity(tf_ping.value.strip(), tf_http.value.strip(), 5)
                    good = bool(c["ping_ok"] or c["http_ok"])
                    add_result(mac, good, f"{'✅ accès labo OK' if good else '❌ pas d’accès'} — ping={c['ping_ok']} http={c['http_ok']}")
                    w.writerow({"timestamp": datetime.now().isoformat(timespec="seconds"), "lab": tf_lab.value.strip(),
                                "interface": dd_iface.value, "mac": mac, "applied": True,
                                "ping_ok": c["ping_ok"], "http_ok": c["http_ok"], "http_code": c["http_code"], "mode": "gui"})
            set_status(f"Terminé ✅ — résultats dans results.csv. MAC d'origine restaurée 👍")
        except Exception as e:  # message simple, pas de traceback effrayant
            set_status(f"Oups ❌ : {e} — essayez le mode Démo d'abord.")
        finally:
            try:
                core.restore_mac()
            except Exception:
                pass
            progress.visible = False
            page.update()

    def restore_now(_):
        core.restore_mac()
        set_status("MAC d'origine restaurée 👍")

    # --- Layout joli, en cartes ---
    page.add(
        ft.Text("📡 Testeur MAC — version simple", size=24, weight="bold"),
        ft.Text("Pour TP / démo en classe. Labo autorisé uniquement — le mode Démo ne touche à rien.",
                color="grey", size=13),
        ft.Card(content=ft.Container(
            content=ft.Column([
                ft.Text("Étape 1 — Où tester ?", weight="bold"),
                ft.Row([dd_iface, tf_lab], wrap=True),
                ft.Row([ft.ElevatedButton("📂 Choisir un fichier MACs", icon="folder_open",
                                          on_click=lambda _: picker.pick_files(allowed_extensions=["txt"])),
                        tf_file], wrap=True),
            ]), padding=16)),
        ft.Card(content=ft.Container(
            content=ft.Column([
                ft.Text("Étape 2 — Quel mode ?", weight="bold"),
                sw_demo,
                ft.Row([tf_ping, tf_http], wrap=True),
                chk_confirm,
                ft.Text("Le test réel exige sudo + case cochée. Sinon, restez en Démo.",
                        size=12, color="grey"),
            ]), padding=16)),
        ft.Row([
            ft.FilledButton("▶ Lancer", icon="play_arrow", on_click=run_test, height=48, expand=True),
            ft.OutlinedButton("↩ Restaurer ma MAC", icon="refresh", on_click=restore_now, height=48),
        ]),
        progress, status,
        ft.Text("Résultats :", weight="bold"),
        ft.Container(content=results_view, border=ft.border.all(1, "lightgrey"), border_radius=12),
        ft.Text("Journal :", weight="bold"), log_box,
        ft.Text("Pédagogie : une MAC seule ne protège rien → portail captif, sessions, 802.1X.",
                size=12, color="grey"),
    )


if __name__ == "__main__":
    ft.app(target=main)
