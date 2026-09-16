# wifizone-bypass — Academic PoC (LAB ONLY)

> 🌍 *Version française : [README.md](README.md)*
>
> ⚠️ **Ethics / legal**: for **educational** purposes, on **your own lab** (a test access point you own, written authorization).
> Using this on a third-party WiFi zone without authorization = intrusion / theft of service, illegal.
> The program refuses to test without the authorization checkbox / option, and always restores your original MAC.

Demonstrates why **MAC-only authentication is insufficient**: a MAC travels in clear text, can be captured passively and replayed with standard commands (`nmcli`, `ip link`).

---

## 🖥️ Easy way: the graphical interface (`gui.py`)

No terminal to memorize. Modern interface (Flet, not tkinter) in **French or English** (**EN/FR** button, top right) with **dark/light mode** (🌙/☀️ button).

```bash
pip install -r requirements-gui.txt
sudo .venv/bin/python gui.py
```

> **Why `sudo`?** Changing MACs and capturing traffic require root privileges.
> **Why does it sometimes open in the browser?** Under sudo, Flet can't find its display client cached for root and can't always download it. The app tries the real window first, otherwise it falls back to the browser — **the exact address (localhost + network IP + port) is then printed in the terminal**, keep it open.
> To force: `sudo FLET_GUI=web .venv/bin/python gui.py` (browser, zero download) or `sudo FLET_GUI=desktop ...` (window). A possible Flet client download the first time is normal (official package, reused afterwards).

### Step 0 — Capture YOUR lab (optional)
- Enter the **duration** (30 s by default), click **● Capture**, **⏹ Stop** to quit early.
- The capture is saved to `/tmp/capture-YYYYMMDD-HHMMSS.pcapng` (not in the project folder: the capture tool drops its root privileges and cannot write elsewhere).
- At the end, MAC addresses are **extracted automatically** (`wlan.sa/wlan.da` via tshark, otherwise `eth.src/eth.dst`): duplicates, broadcast and invalid addresses filtered, and the file field is filled in by itself.

### Step 1 — Where to test?
- **WiFi interface**: auto-detected list (`wlan0`…).
- **MACs file**: 📂 **Choose a MACs file** button, or type/fix the path by hand (e.g. `mac_output.txt`, `/tmp/mac_output.txt`). In browser mode, the chosen file is imported locally (`macs_gui_import.txt`).
- **Target SSID**: a simple free-form label (e.g. `TP-SalleB`) found again in `results.csv`.

### Step 2 — Run the real test
- Check **"I confirm testing ONLY my own authorized lab"**.
- Click **▶ Run** (refuses to start twice; **⏹ Stop** quits cleanly between two MACs, with restore).
- Live follow-up: `Try 3/40: aa:...`, progress bar, result cards **✅ internet OK / ⚠️ captive portal / ❌ no internet**, and a **log** at the bottom.

### The cycle tested for EACH MAC address
1. Takes the next address from the list.
2. Applies it via the NetworkManager profile (`nmcli connection modify <profile> 802-11-wireless.cloned-mac-address <mac>` then `nmcli connection up <profile>`) — without this, NetworkManager restores the factory MAC on reconnect and skews every result.
3. **Verifies first**: interface back up + **read MAC == requested MAC** + **IP address obtained (DHCP)**. No IP → direct failure, no pointless test, next one.
4. Does the equivalent of `curl http://www.google.com`: ✅ if real Google page, ⚠️ if captive portal, ❌ otherwise. (No ping: the gateway answers even without authentication, so ping proves nothing.)
5. Writes the result to `results.csv` and moves to the next one (~2–4 s per MAC).

### "Use" and "Restore" buttons
- Every green card has a **Use** button: applies that MAC in one click (same verified sequence) so you can browse with it.
- **↩ Restore my MAC**: clears the profile's `cloned-mac-address`, puts the original MAC back (the session-start one, otherwise the hardware one via `ethtool -P`), reconnects, **and displays the actually read MAC** — never a fake "restored 👍".

### The log (`$` lines)
Every exact system command run is shown with a leading `$ ` (e.g. `$ nmcli connection up "ADMINISTRATION FOYER AKWABA"`). Handy to understand, debug and feed your report. Only the DHCP polling (`ip -4 ...` every 0.5 s) is filtered out to stay readable.

---

## ⌨️ Terminal way (`tester_mac.py`, unchanged and still working)

```bash
# validate without changing anything
python3 tester_mac.py --interface wlan0 --file mac_output.txt --dry-run

# real lab test
sudo python3 tester_mac.py -i wlan0 -f mac_output.txt \
  --lab-ap "TP-SalleB" --confirm-lab --out results.csv

# useful options
#   --http-url http://www.google.com   curl-style test URL(s), comma-separated
#   --timeout 4                        HTTP timeout per MAC (s)
#   --delay 8                          MAX DHCP wait per MAC (early exit on IP)
#   --limit 5                          limit to N MACs (short test)
#   --manual                           Enter pause between MACs (manual browser test)
```

Same engine as the GUI: verified persistent apply (read-back MAC + IP), google curl, `results.csv` CSV (`timestamp,lab,interface,mac,applied,ping_ok,http_ok,http_code,portal,detail,mode` — `ping_ok` kept empty for compatibility), auto restore even on Ctrl+C. Note: the CLI itself stays in French.

---

## 🛠️ Prerequisites

- Linux, `python3`, `iproute2`, `ethtool`, `network-manager` (`nmcli`), `tshark` for capture.
- root (`sudo`) to change MACs and capture.
- GUI: `pip install -r requirements-gui.txt` (`flet` package only; the CLI needs stdlib only).

```bash
sudo apt install tshark python3 network-manager ethtool iproute2
```

## ❓ Frequent issues

| Symptom | Cause / fix |
|---|---|
| `Permission denied` on the `.pcapng` during capture | Normal: captures go to `/tmp/`, handled automatically. |
| Files owned by root in the project | Given back to your user via `SUDO_UID` after writing; clean the old root `__pycache__` with `sudo rm -rf __pycache__`. |
| The MAC "doesn't change" | That was NetworkManager overwriting it: now applied via the profile's `cloned-mac-address` + read-back verification. |
| The interface "stays down" | `set_mac` always brings the interface back up in a `finally` + `ensure_link_up` after each phase. |
| "File not found" in the GUI | The file doesn't exist yet: generate it (Step 0) or create it (one MAC per line), or fix the path (`/tmp/...`). |
| Flet re-downloads its client under sudo | Normal the 1st time (empty root cache); reused afterwards. `FLET_GUI=web` to avoid it. |

---

## 🔍 For your report

| Vulnerability | Explanation | Countermeasure |
|---|---|---|
| MAC alone | In clear text, replayable | Captive portal + session token |
| No bound session | Trivial replay | RADIUS / 802.1X, short timeout |
| Trivial spoofing | Standard `nmcli`/`ip link`, NM even reapplies by itself | Duplicate-MAC detection, simultaneous-connection alerts |

Operator leads: 802.1X, short-lived tokens, same-MAC-on-2-radios detection, client isolation.

---

## 📁 Structure

```
.
├── README.md            # This doc in French
├── README.en.md         # This doc in English (this file)
├── tester_mac.py        # CLI engine + shared functions (apply, curl test, restore)
├── gui.py               # Flet UI: capture, test, Use, Stop, Restore, $ log (FR/EN, dark/light)
├── requirements-gui.txt # flet>=1.0 (GUI only)
├── .gitignore           # ignores pcap, mac_output*.txt, results.csv
├── mac_output.txt       # YOUR MAC list (generated, not versioned)
└── results.csv          # Results (generated, not versioned)
```
