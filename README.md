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

## Notes

- Some system processes may show `N/A` for username or 0 for handles due to Windows access restrictions.
- On Windows, F9 signal menu only exposes SIGTERM (graceful) and SIGKILL (force), since the full POSIX signal set is not available.
- Run as Administrator to see all processes and their details without access-denied errors.

## License

MIT
