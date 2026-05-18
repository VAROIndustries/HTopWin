# HTopWin — htop for Windows

A terminal-based process manager for Windows, inspired by [htop](https://htop.dev/). Built with [Textual](https://textual.textualize.io/) and [psutil](https://psutil.readthedocs.io/).

![HTopWin Screenshot](screenshot.png)

## Features

- **Per-core CPU bars** with smooth Unicode block-character fill (▏▎▍▌▋▊▉█)
- **Memory & Swap bars** with used/total display
- **Process table** with columns: PID, Name, User, CPU%, MEM%, Threads, Status, Command
- **Sortable columns** — click any header or press F6 for a sort menu
- **Real-time search/filter** — press `/` or F3 to filter by name, user, PID, or command
- **Kill processes** — press `k` to confirm-kill or `F9` to send a specific signal
- **Color-coded bars and values** — green < 50%, yellow 50–80%, red > 80%
- **System info strip** — uptime, CPU core/thread count, current frequency
- **Auto-refresh** every 2 seconds
- **Windows-friendly** — gracefully handles access-denied processes; uses `kill()`/`terminate()` on Windows

## Requirements

- Python 3.8+
- Windows 10/11 (also works on Linux/macOS)

## Installation

```bash
# 1. Clone or download the project
cd HTopWin

# 2. Create a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
python htopwin.py
```

## Keyboard Shortcuts

| Key         | Action                          |
|-------------|---------------------------------|
| `q` / F10   | Quit                            |
| `k`         | Kill selected process (SIGKILL) |
| F9          | Send signal menu                |
| F5          | Force refresh now               |
| F6          | Open sort menu                  |
| F3 or `/`   | Toggle search/filter bar        |
| `Escape`    | Close search / dismiss dialogs  |
| `↑` / `↓`  | Navigate process list           |
| Click header| Sort by that column             |

## Column Reference

| Column   | Description                                |
|----------|--------------------------------------------|
| PID      | Process ID                                 |
| Name     | Process executable name                    |
| User     | Owner username                             |
| CPU%     | CPU usage percentage                       |
| MEM%     | Memory usage percentage                    |
| Threads  | Number of threads                          |
| Status   | running / sleeping / stopped / zombie …   |
| Command  | Full command line                          |

## Color Coding

| Color  | Meaning           |
|--------|-------------------|
| Green  | < 50% usage       |
| Yellow | 50–80% usage      |
| Red    | > 80% usage       |

## Remote Monitoring

HTopWin can monitor remote Linux servers over SSH. Credentials are stored
encrypted on your local machine — nothing is sent or stored in plain text.

### Quick start

1. Press **F2** to open the Server Manager.
2. The first time you open it you will be prompted to set a **master password**.
   Remember this password — if you lose it, delete `~/.htopwin/servers.enc`
   and create a new store.
3. Press **a** (or click "Add") to add a server:
   - **Name** — a short label (e.g. `web-prod`)
   - **Host** — IP address or hostname
   - **Port** — SSH port (default `22`)
   - **Username** — SSH username (e.g. `root` or `ubuntu`)
   - **Auth type** — `password` or `key`
   - **Password** — leave blank when using a key
   - **Key path** — path to your private key, e.g. `~/.ssh/id_rsa`
4. Select the server in the list and press **Enter** or click **Connect**.
5. HTopWin switches to remote mode: CPU bars, memory bars, sysinfo strip,
   and the process table all reflect the remote host.
6. Press **F4** to disconnect and return to local monitoring.

### Credential storage

| File | Contents |
|------|----------|
| `~/.htopwin/servers.salt` | 16-byte random salt (created once) |
| `~/.htopwin/servers.enc`  | Fernet-encrypted JSON server list |

The encryption key is derived from your master password with
PBKDF2-HMAC-SHA256 (600 000 iterations).  Delete `servers.enc` to reset
the store completely.

### Additional dependencies

Remote monitoring requires two extra packages:

```bash
pip install paramiko cryptography
```

If these are not installed, HTopWin still works normally for local monitoring
and will show an error notification if you attempt to open the Server Manager.

## Notes

- Some system processes may show `N/A` for username or 0 for handles due to Windows access restrictions.
- On Windows, F9 signal menu only exposes SIGTERM (graceful) and SIGKILL (force), since the full POSIX signal set is not available.
- Run as Administrator to see all processes and their details without access-denied errors.

## License

MIT
