# HTopWin

[![VARØ Industries](https://img.shields.io/badge/VAR%C3%98-Industries-c8883e?style=flat-square)](https://varo.industries)

> **htop for Windows** — a rich, interactive terminal process manager with remote SSH monitoring.

Built with [Textual](https://textual.textualize.io/) and [psutil](https://psutil.readthedocs.io/). Runs natively on Windows 10/11, and also works on Linux and macOS.

---

## Features

### Local monitoring
- **Per-core CPU bars** using smooth Unicode block characters (▏▎▍▌▋▊▉█)
- **Memory & Swap bars** with used/total display
- **Process table** — PID, Name, User, CPU%, MEM%, Threads, Status, Command
- **Sortable columns** — click any header or use the F6 sort menu
- **Live search/filter** — press `/` or F3 to filter by name, user, PID, or command
- **Kill & signal** — `k` for quick SIGKILL, F9 for a full signal menu
- **Color-coded values** — green < 50%, yellow 50–80%, red > 80%
- **System info strip** — uptime, CPU cores/threads, clock frequency, load averages
- **Auto-refresh** every 2 seconds (F5 to force)

### Remote SSH monitoring
- Connect to any Linux/Unix server via SSH
- Collects live CPU-per-core, memory, swap, load averages, and full process list from the remote host
- Seamlessly switches all panels and the process table to remote data
- Press F4 to disconnect and return to local monitoring

### Encrypted server manager
- Store unlimited SSH server profiles locally
- Credentials encrypted with **Fernet / AES-128-CBC**
- Key derived from your master password via **PBKDF2-HMAC-SHA256 (600 000 iterations)**
- Supports both password auth and SSH private key auth
- Nothing is ever stored in plain text

---

## Requirements

- **Python 3.8+**
- Windows 10/11 (also runs on Linux and macOS)

---

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/VAROIndustries/HTopWin.git
cd HTopWin

# 2. Create a virtual environment (recommended)
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Launch
python htopwin.py
```

> **Tip:** Run as Administrator (Windows) or with `sudo` (Linux) to see all processes without access-denied gaps.

---

## Remote Monitoring Setup

Remote monitoring requires two additional packages:

```bash
pip install paramiko cryptography
```

These are already listed in `requirements.txt` — a plain `pip install -r requirements.txt` installs everything.

### Connecting to a remote server

1. Press **F2** to open the Server Manager.
2. On first launch you will be asked to **create a master password**. This password encrypts your server list — keep it safe. If you forget it, delete `~/.htopwin/servers.enc` and start fresh.
3. Press **`a`** or click **Add** to register a server:

   | Field | Description |
   |---|---|
   | Name | Short label, e.g. `web-prod` |
   | Host | IP address or hostname |
   | Port | SSH port (default `22`) |
   | Username | SSH login user, e.g. `ubuntu` |
   | Auth type | `password` or `key` |
   | Password | SSH password (leave blank when using a key) |
   | Key path | Path to private key, e.g. `~/.ssh/id_rsa` |

4. Select the server and press **Enter** (or click **Connect**).
5. All panels — CPU bars, memory bars, sysinfo strip, and process table — switch to the remote host.
6. Press **F4** to disconnect and return to local view.

### Where credentials are stored

| Path | Contents |
|---|---|
| `~/.htopwin/servers.salt` | 16-byte random salt (written once on first use) |
| `~/.htopwin/servers.enc` | Fernet-encrypted JSON blob containing all server profiles |

---

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `q` / F10 | Quit |
| F2 | Open Server Manager (remote SSH) |
| F3 / `/` | Toggle search / filter bar |
| F4 | Disconnect remote, return to local |
| F5 | Force immediate refresh |
| F6 | Sort menu |
| F9 | Send signal to selected process |
| `k` | Kill selected process (SIGKILL, with confirmation) |
| `↑` / `↓` | Navigate process list |
| Click header | Sort by that column (click again to reverse) |
| Escape | Close dialogs / clear search |

---

## Column Reference

| Column | Description |
|---|---|
| PID | Process ID |
| Name | Executable name |
| User | Owner username |
| CPU% | CPU usage (color-coded) |
| MEM% | Memory usage (color-coded) |
| Threads | Thread count |
| Status | running / sleeping / stopped / zombie … |
| Command | Full command line |

---

## Color Guide

| Color | Threshold |
|---|---|
| Green | < 50% |
| Yellow | 50 – 80% |
| Red | > 80% |

Applies to CPU%, MEM%, and the CPU/memory bars.

---

## Platform Notes

**Windows**
- The F9 signal menu exposes only SIGTERM (graceful) and SIGKILL (force) — the full POSIX signal set is not available on Windows.
- Some system processes show `N/A` for username due to OS access restrictions. Run as Administrator to minimise this.

**Linux / macOS**
- Full POSIX signal menu (SIGHUP, SIGINT, SIGQUIT, SIGKILL, SIGTERM, SIGSTOP, SIGCONT).
- Load averages shown in the sysinfo strip.
- Remote monitoring reads `/proc` directly, so the target server must be Linux.

---

## Project Structure

```
HTopWin/
├── htopwin.py          # Main TUI application
├── server_manager.py   # Encrypted SSH credential store
├── remote_monitor.py   # SSH-based remote data collector
├── requirements.txt
└── README.md
```

---

## Dependencies

| Package | Purpose |
|---|---|
| [textual](https://github.com/Textualize/textual) | TUI framework |
| [psutil](https://github.com/giampaolo/psutil) | Local system & process info |
| [paramiko](https://www.paramiko.org/) | SSH client for remote monitoring |
| [cryptography](https://cryptography.io/) | Fernet encryption for credential storage |

---

## License

MIT — see [LICENSE](LICENSE) for details.
