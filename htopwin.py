"""
HTopWin - htop for Windows
A terminal-based process manager for Windows built with Textual and psutil.
"""

from __future__ import annotations

import asyncio
import ctypes
import platform
import signal
import sys
from datetime import timedelta
from typing import ClassVar, Optional

try:
    import winreg  # Windows only
except ImportError:
    winreg = None  # type: ignore[assignment]

# remote imports — handled lazily so the app works without them if not installed

import psutil
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
)

IS_WINDOWS = platform.system() == "Windows"


# ─────────────────────────────────────────────────────────
#  Admin / Startup helpers
# ─────────────────────────────────────────────────────────

def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


STARTUP_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_APP_NAME = "HTopWin"


def _is_in_startup() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        import winreg as _winreg
        key = _winreg.OpenKey(_winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0, _winreg.KEY_READ)
        _winreg.QueryValueEx(key, STARTUP_APP_NAME)
        _winreg.CloseKey(key)
        return True
    except Exception:
        return False


def _set_startup(enable: bool) -> None:
    if not IS_WINDOWS:
        return
    try:
        import winreg as _winreg
        key = _winreg.OpenKey(_winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0, _winreg.KEY_SET_VALUE)
        if enable:
            exe = sys.executable if not getattr(sys, 'frozen', False) else sys.executable
            script = sys.argv[0] if not getattr(sys, 'frozen', False) else ""
            value = f'"{exe}" "{script}"' if script else f'"{exe}"'
            _winreg.SetValueEx(key, STARTUP_APP_NAME, 0, _winreg.REG_SZ, value)
        else:
            try:
                _winreg.DeleteValue(key, STARTUP_APP_NAME)
            except FileNotFoundError:
                pass
        _winreg.CloseKey(key)
    except Exception:
        pass


def _restart_as_admin() -> None:
    """Re-launch the current process with admin privileges."""
    if not IS_WINDOWS:
        return
    exe = sys.executable
    script = sys.argv[0] if not getattr(sys, 'frozen', False) else ""
    params = f'"{script}"' if script else ""
    ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)


# ─────────────────────────────────────────────────────────
#  Inline CSS
# ─────────────────────────────────────────────────────────
APP_CSS = """
/* ── Base ── */
Screen {
    background: #1a1a2e;
    color: #e0e0e0;
}

/* ── Top panel ── */
#top-panel {
    height: auto;
    background: #16213e;
    padding: 0 1;
    border-bottom: solid #0f3460;
}

#cpu-section {
    height: auto;
    padding: 0;
}

#mem-section {
    height: auto;
    padding: 0;
}

.section-title {
    color: #00d4ff;
    text-style: bold;
    width: auto;
    padding: 0 1 0 0;
}

.bar-row {
    height: 1;
    layout: horizontal;
}

.bar-label {
    width: 8;
    color: #a0a0c0;
    text-align: right;
    padding-right: 1;
}

.bar-container {
    width: 1fr;
    height: 1;
}

.bar-value {
    width: 7;
    color: #c0c0e0;
    text-align: right;
    padding-left: 1;
}

/* ── System info strip ── */
#sysinfo-bar {
    height: 1;
    background: #0f3460;
    padding: 0 2;
    color: #a0c0ff;
    layout: horizontal;
}

.sysinfo-item {
    width: auto;
    padding: 0 2;
    color: #a0c0ff;
}

.sysinfo-sep {
    color: #304060;
    width: 1;
}

/* ── Toolbar ── */
#toolbar {
    height: 1;
    background: #16213e;
    padding: 0 1;
    layout: horizontal;
}

#search-input {
    width: 30;
    height: 1;
    background: #0d1b2a;
    color: #e0e0e0;
    border: none;
    padding: 0 1;
    display: none;
}

#search-input:focus {
    border: none;
    background: #1a2a3a;
}

#search-input.visible {
    display: block;
}

.toolbar-label {
    color: #6080a0;
    width: auto;
    padding: 0 1;
}

.sort-indicator {
    color: #00d4ff;
    width: auto;
    padding: 0 1;
}

/* ── Process table ── */
#process-scroll {
    height: 1fr;
    background: #1a1a2e;
}

#process-table {
    height: auto;
    background: #1a1a2e;
}

DataTable {
    background: #1a1a2e;
    color: #d0d0e0;
    height: 1fr;
}

DataTable > .datatable--header {
    background: #0f3460;
    color: #00d4ff;
    text-style: bold;
}

DataTable > .datatable--header-hover {
    background: #1a4a80;
    color: #40e0ff;
    text-style: bold;
}

DataTable > .datatable--cursor {
    background: #1a4080;
    color: #ffffff;
}

DataTable > .datatable--hover {
    background: #1e2a4a;
    color: #e0e8ff;
}

DataTable > .datatable--odd-row {
    background: #1e1e32;
}

DataTable > .datatable--even-row {
    background: #1a1a2e;
}

/* ── Status bar ── */
#status-bar {
    height: 1;
    background: #0f3460;
    padding: 0 2;
    layout: horizontal;
    color: #a0c0ff;
}

.status-item {
    width: auto;
    padding: 0 2;
}

.status-key {
    color: #00d4ff;
    text-style: bold;
}

.status-val {
    color: #e0e0e0;
}

/* ── Modal screens ── */
ModalScreen {
    background: rgba(0, 0, 0, 0.8);
    align: center middle;
}

#kill-dialog {
    width: 50;
    height: auto;
    background: #16213e;
    border: solid #0f3460;
    padding: 1 2;
}

#kill-dialog Label {
    text-align: center;
    width: 100%;
    margin-bottom: 1;
}

#kill-dialog .dialog-title {
    color: #ff4444;
    text-style: bold;
    text-align: center;
    width: 100%;
}

#kill-dialog .dialog-info {
    color: #a0c0ff;
    text-align: center;
    width: 100%;
    margin-bottom: 1;
}

#kill-buttons {
    layout: horizontal;
    align: center middle;
    height: auto;
    margin-top: 1;
}

#kill-buttons Button {
    margin: 0 1;
}

Button.danger {
    background: #8b0000;
    color: #ffcccc;
    border: solid #cc0000;
}

Button.danger:hover {
    background: #cc0000;
}

Button.safe {
    background: #1a3a1a;
    color: #ccffcc;
    border: solid #336633;
}

Button.safe:hover {
    background: #336633;
}

/* ── Signal menu ── */
#signal-dialog {
    width: 40;
    height: auto;
    max-height: 30;
    background: #16213e;
    border: solid #0f3460;
    padding: 1 2;
}

#signal-dialog .dialog-title {
    color: #ffaa00;
    text-style: bold;
    text-align: center;
    width: 100%;
    margin-bottom: 1;
}

#signal-list {
    height: auto;
    max-height: 20;
    background: #0d1b2a;
    border: solid #1a3a5a;
}

ListItem {
    padding: 0 1;
    color: #c0d0e0;
}

ListItem:hover {
    background: #1a4080;
    color: #ffffff;
}

ListView:focus > ListItem.--highlight {
    background: #1a4080;
    color: #ffffff;
}

/* ── Sort menu ── */
#sort-dialog {
    width: 35;
    height: auto;
    background: #16213e;
    border: solid #0f3460;
    padding: 1 2;
}

#sort-dialog .dialog-title {
    color: #00d4ff;
    text-style: bold;
    text-align: center;
    width: 100%;
    margin-bottom: 1;
}

/* ── Footer override ── */
Footer {
    background: #0f3460;
    color: #a0c0ff;
}

Footer > .footer--key {
    background: #1a4080;
    color: #ffffff;
}

/* ── Scrollbar ── */
ScrollableContainer > .scrollbar {
    background: #0f3460;
}

ScrollableContainer > .scrollbar--slider {
    background: #304880;
}

/* ── Server Manager ── */
#server-manager-dialog {
    width: 70;
    height: 30;
    background: #16213e;
    border: solid #0f3460;
    padding: 1 2;
}
#server-manager-dialog .dialog-title {
    color: #00d4ff;
    text-style: bold;
    text-align: center;
    width: 100%;
    margin-bottom: 1;
}
#server-list {
    height: 15;
    background: #0d1b2a;
    border: solid #1a3a5a;
}
#server-buttons {
    layout: horizontal;
    height: auto;
    margin-top: 1;
}
#server-buttons Button {
    margin: 0 1;
}

/* ── Add Server Form ── */
#add-server-dialog {
    width: 60;
    height: auto;
    background: #16213e;
    border: solid #0f3460;
    padding: 1 2;
}
#add-server-dialog .dialog-title {
    color: #00d4ff;
    text-style: bold;
    text-align: center;
    width: 100%;
    margin-bottom: 1;
}
.form-row {
    height: 3;
    layout: horizontal;
    margin-bottom: 1;
}
.form-label {
    width: 14;
    color: #a0c0ff;
    padding-top: 1;
}
.form-input {
    width: 1fr;
    background: #0d1b2a;
    color: #e0e0e0;
    border: solid #1a3a5a;
}
.form-input:focus {
    border: solid #00d4ff;
}
#form-buttons {
    layout: horizontal;
    height: auto;
    margin-top: 1;
    align: center middle;
}
#form-buttons Button {
    margin: 0 1;
}

/* ── Master Password ── */
#master-pw-dialog {
    width: 50;
    height: auto;
    background: #16213e;
    border: solid #0f3460;
    padding: 1 2;
}
#master-pw-dialog .dialog-title {
    color: #ffcc00;
    text-style: bold;
    text-align: center;
    width: 100%;
    margin-bottom: 1;
}

/* ── Remote status ── */
.remote-badge {
    color: #00ff88;
    text-style: bold;
    width: auto;
    padding: 0 2;
}

/* ── Settings screen ── */
#settings-dialog {
    width: 60;
    height: auto;
    background: #16213e;
    border: solid #0f3460;
    padding: 1 2;
}
#settings-dialog .dialog-title {
    color: #00d4ff;
    text-style: bold;
    text-align: center;
    width: 100%;
    margin-bottom: 1;
}
.settings-row {
    height: 3;
    layout: horizontal;
    margin-bottom: 1;
}
.settings-label {
    width: 30;
    color: #a0c0ff;
    padding-top: 1;
}
.settings-value {
    width: 1fr;
    color: #e0e0e0;
    padding-top: 1;
}
#settings-buttons {
    layout: horizontal;
    height: auto;
    margin-top: 1;
    align: center middle;
}
#settings-buttons Button {
    margin: 0 1;
}
.admin-badge {
    color: #ffcc00;
    text-style: bold;
}
.not-admin-badge {
    color: #ff6666;
}
"""

# ─────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────
BLOCK_CHARS = " ▏▎▍▌▋▊▉█"


def make_bar(pct: float, width: int = 20) -> str:
    """Return a Unicode block-character progress bar string."""
    pct = max(0.0, min(100.0, pct))
    filled_units = pct / 100.0 * width * 8
    full_blocks = int(filled_units // 8)
    remainder = int(filled_units % 8)
    bar = "█" * full_blocks
    if remainder > 0 and full_blocks < width:
        bar += BLOCK_CHARS[remainder]
    bar = bar.ljust(width)
    return bar


def bar_color(pct: float) -> str:
    """Return a Rich markup color string based on percentage."""
    if pct < 50:
        return "#00cc44"
    elif pct < 80:
        return "#ffcc00"
    else:
        return "#ff3333"


def rich_bar(pct: float, width: int = 20) -> str:
    """Return a Rich markup string for a colored bar."""
    color = bar_color(pct)
    bar = make_bar(pct, width)
    return f"[{color}]{bar}[/{color}]"


def format_bytes(n: int) -> str:
    for unit in ("B", "K", "M", "G", "T"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}P"


def format_uptime(seconds: float) -> str:
    td = timedelta(seconds=int(seconds))
    days = td.days
    hours, rem = divmod(td.seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


# ─────────────────────────────────────────────────────────
#  Widgets
# ─────────────────────────────────────────────────────────
class BarWidget(Static):
    """A single labelled progress bar."""

    DEFAULT_CSS = """
    BarWidget {
        height: 1;
        layout: horizontal;
    }
    """

    def __init__(self, label: str, pct: float = 0.0, extra: str = "", **kwargs):
        super().__init__(**kwargs)
        self._label = label
        self._pct = pct
        self._extra = extra

    def compose(self) -> ComposeResult:
        yield Static(self._label, classes="bar-label")
        yield Static("", id=f"bar-fill-{self.id}", classes="bar-container")
        yield Static("", id=f"bar-val-{self.id}", classes="bar-value")

    def on_mount(self) -> None:
        self._render_bar()

    def update_bar(self, pct: float, extra: str = "") -> None:
        self._pct = pct
        self._extra = extra
        self._render_bar()

    def _render_bar(self) -> None:
        try:
            fill_widget = self.query_one(f"#bar-fill-{self.id}", Static)
            val_widget = self.query_one(f"#bar-val-{self.id}", Static)
            fill_widget.update(rich_bar(self._pct, width=25))
            val_widget.update(f"{self._pct:5.1f}%{(' ' + self._extra) if self._extra else ''}")
        except NoMatches:
            pass


class CpuBarsPanel(Widget):
    """Panel showing one bar per CPU core, arranged in 2 columns."""

    DEFAULT_CSS = """
    CpuBarsPanel {
        height: auto;
        width: auto;
        padding: 0;
    }
    .cpu-col {
        height: auto;
        width: auto;
        padding-right: 2;
    }
    """

    def compose(self) -> ComposeResult:
        cpu_count = psutil.cpu_count(logical=True) or 1
        half = (cpu_count + 1) // 2
        yield Static("[bold #00d4ff]CPU[/bold #00d4ff]", classes="section-title")
        with Horizontal():
            with Vertical(classes="cpu-col"):
                for i in range(half):
                    yield BarWidget(label=f"{i+1:>2}", pct=0.0, id=f"cpu-bar-{i}")
            with Vertical(classes="cpu-col"):
                for i in range(half, cpu_count):
                    yield BarWidget(label=f"{i+1:>2}", pct=0.0, id=f"cpu-bar-{i}")

    def refresh_stats(self, per_cpu: list[float]) -> None:
        for i, pct in enumerate(per_cpu):
            try:
                bar = self.query_one(f"#cpu-bar-{i}", BarWidget)
                bar.update_bar(pct)
            except NoMatches:
                pass


class MemBarsPanel(Widget):
    """Panel showing memory and swap bars."""

    DEFAULT_CSS = """
    MemBarsPanel {
        height: auto;
        padding: 0;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("[bold #00d4ff]  MEM[/bold #00d4ff]", classes="section-title")
        yield BarWidget(label="  Mem", pct=0.0, id="mem-bar")
        yield BarWidget(label=" Swp", pct=0.0, id="swp-bar")

    def refresh_stats(self, mem: psutil.svmem, swap: psutil.sswap) -> None:  # type: ignore[name-defined]
        try:
            mem_bar = self.query_one("#mem-bar", BarWidget)
            used_str = format_bytes(mem.used)
            total_str = format_bytes(mem.total)
            mem_bar.update_bar(mem.percent, f"{used_str}/{total_str}")
        except NoMatches:
            pass
        try:
            swp_bar = self.query_one("#swp-bar", BarWidget)
            if swap.total > 0:
                used_str = format_bytes(swap.used)
                total_str = format_bytes(swap.total)
                swp_bar.update_bar(swap.percent, f"{used_str}/{total_str}")
            else:
                swp_bar.update_bar(0.0, "N/A")
        except NoMatches:
            pass


# ─────────────────────────────────────────────────────────
#  Modal Screens
# ─────────────────────────────────────────────────────────
class KillConfirmScreen(ModalScreen[bool]):
    """Confirmation dialog before killing a process."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Confirm"),
    ]

    def __init__(self, pid: int, name: str, **kwargs):
        super().__init__(**kwargs)
        self._pid = pid
        self._name = name

    def compose(self) -> ComposeResult:
        with Container(id="kill-dialog"):
            yield Label("[bold red]  KILL PROCESS[/bold red]", classes="dialog-title")
            yield Label(
                f"Send SIGKILL to:[/]\n[bold white]{self._name}[/bold white] (PID [yellow]{self._pid}[/yellow])",
                classes="dialog-info",
            )
            with Horizontal(id="kill-buttons"):
                yield Button("  Kill", id="btn-kill", classes="danger")
                yield Button("  Cancel", id="btn-cancel", classes="safe")

    @on(Button.Pressed, "#btn-kill")
    def action_confirm(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#btn-cancel")
    def action_cancel(self) -> None:
        self.dismiss(False)


if IS_WINDOWS:
    SIGNALS = [
        (signal.SIGTERM, "SIGTERM (15) - Graceful terminate"),
        (9,              "SIGKILL (9)  - Force kill"),
    ]
else:
    SIGNALS = [
        (signal.SIGHUP,  "SIGHUP  (1)  - Hangup"),
        (signal.SIGINT,  "SIGINT  (2)  - Interrupt"),
        (signal.SIGQUIT, "SIGQUIT (3)  - Quit"),
        (9,              "SIGKILL (9)  - Force kill"),
        (signal.SIGTERM, "SIGTERM (15) - Graceful terminate"),
        (signal.SIGSTOP, "SIGSTOP (19) - Stop"),
        (signal.SIGCONT, "SIGCONT (18) - Continue"),
    ]


class SignalMenuScreen(ModalScreen[int | None]):
    """Menu for choosing which signal to send."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, pid: int, name: str, **kwargs):
        super().__init__(**kwargs)
        self._pid = pid
        self._name = name

    def compose(self) -> ComposeResult:
        with Container(id="signal-dialog"):
            yield Label(
                f"[bold yellow]  Send Signal[/bold yellow]\n[dim]{self._name} (PID {self._pid})[/dim]",
                classes="dialog-title",
            )
            items = [ListItem(Label(desc), id=f"sig-{int(sig)}") for sig, desc in SIGNALS]
            yield ListView(*items, id="signal-list")

    @on(ListView.Selected)
    def signal_selected(self, event: ListView.Selected) -> None:
        if event.item.id and event.item.id.startswith("sig-"):
            sig_val = int(event.item.id[4:])
            self.dismiss(sig_val)

    def action_cancel(self) -> None:
        self.dismiss(None)


class SortMenuScreen(ModalScreen[str | None]):
    """Menu for choosing sort column."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    COLUMNS = [
        ("pid", "PID"),
        ("name", "Name"),
        ("username", "User"),
        ("cpu_percent", "CPU%"),
        ("memory_percent", "MEM%"),
        ("num_threads", "Threads"),
        ("status", "Status"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="sort-dialog"):
            yield Label("[bold #00d4ff]  Sort By[/bold #00d4ff]", classes="dialog-title")
            items = [ListItem(Label(f"  {display}"), id=f"sort-{key}") for key, display in self.COLUMNS]
            yield ListView(*items, id="sort-list")

    @on(ListView.Selected)
    def sort_selected(self, event: ListView.Selected) -> None:
        if event.item.id and event.item.id.startswith("sort-"):
            key = event.item.id[5:]
            self.dismiss(key)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ─────────────────────────────────────────────────────────
#  Remote / Server Manager Screens
# ─────────────────────────────────────────────────────────

class MasterPasswordScreen(ModalScreen):
    """Prompt for master password to unlock server store."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, prompt_text: str = "Enter master password:", **kwargs):
        super().__init__(**kwargs)
        self._prompt_text = prompt_text

    def compose(self) -> ComposeResult:
        with Container(id="master-pw-dialog"):
            yield Label("[bold yellow]  Server Store[/bold yellow]", classes="dialog-title")
            yield Label(self._prompt_text, classes="dialog-info")
            yield Input(password=True, placeholder="master password...", id="master-pw-input")
            with Horizontal(id="kill-buttons"):
                yield Button("  Unlock", id="btn-unlock", classes="safe")
                yield Button("  Cancel", id="btn-cancel", classes="danger")

    def on_mount(self) -> None:
        self.query_one("#master-pw-input", Input).focus()

    @on(Button.Pressed, "#btn-unlock")
    def do_unlock(self) -> None:
        pw = self.query_one("#master-pw-input", Input).value
        self.dismiss(pw if pw else None)

    @on(Button.Pressed, "#btn-cancel")
    def do_cancel(self) -> None:
        self.dismiss(None)

    @on(Input.Submitted, "#master-pw-input")
    def input_submitted(self, event: Input.Submitted) -> None:
        pw = event.value
        self.dismiss(pw if pw else None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class AddServerScreen(ModalScreen):
    """Form to add or edit a server entry."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, existing: dict | None = None, **kwargs):
        super().__init__(**kwargs)
        self._existing = existing or {}

    def compose(self) -> ComposeResult:
        with Container(id="add-server-dialog"):
            title = "Edit Server" if self._existing else "Add Server"
            yield Label(f"[bold #00d4ff]{title}[/bold #00d4ff]", classes="dialog-title")
            with Horizontal(classes="form-row"):
                yield Label("Name:", classes="form-label")
                yield Input(value=self._existing.get("name", ""), placeholder="my-server", id="f-name", classes="form-input")
            with Horizontal(classes="form-row"):
                yield Label("Host:", classes="form-label")
                yield Input(value=self._existing.get("host", ""), placeholder="192.168.1.1 or hostname", id="f-host", classes="form-input")
            with Horizontal(classes="form-row"):
                yield Label("Port:", classes="form-label")
                yield Input(value=str(self._existing.get("port", 22)), placeholder="22", id="f-port", classes="form-input")
            with Horizontal(classes="form-row"):
                yield Label("Username:", classes="form-label")
                yield Input(value=self._existing.get("username", ""), placeholder="root", id="f-user", classes="form-input")
            with Horizontal(classes="form-row"):
                yield Label("Auth type:", classes="form-label")
                yield Input(value=self._existing.get("auth_type", "password"), placeholder="password or key", id="f-auth", classes="form-input")
            with Horizontal(classes="form-row"):
                yield Label("Password:", classes="form-label")
                yield Input(value=self._existing.get("password", ""), password=True, placeholder="(leave blank if using key)", id="f-pass", classes="form-input")
            with Horizontal(classes="form-row"):
                yield Label("Key path:", classes="form-label")
                yield Input(value=self._existing.get("key_path", ""), placeholder="~/.ssh/id_rsa (optional)", id="f-key", classes="form-input")
            with Horizontal(id="form-buttons"):
                yield Button("  Save", id="btn-save", classes="safe")
                yield Button("  Cancel", id="btn-cancel", classes="danger")

    def on_mount(self) -> None:
        self.query_one("#f-name", Input).focus()

    @on(Button.Pressed, "#btn-save")
    def do_save(self) -> None:
        name      = self.query_one("#f-name", Input).value.strip()
        host      = self.query_one("#f-host", Input).value.strip()
        port_str  = self.query_one("#f-port", Input).value.strip()
        username  = self.query_one("#f-user", Input).value.strip()
        auth_type = self.query_one("#f-auth", Input).value.strip() or "password"
        password  = self.query_one("#f-pass", Input).value
        key_path  = self.query_one("#f-key", Input).value.strip()

        if not name or not host or not username:
            self.notify("Name, Host, and Username are required.", severity="error")
            return
        try:
            port = int(port_str) if port_str else 22
        except ValueError:
            self.notify("Port must be a number.", severity="error")
            return

        server = {
            "name":      name,
            "host":      host,
            "port":      port,
            "username":  username,
            "auth_type": auth_type,
            "password":  password,
            "key_path":  key_path,
        }
        self.dismiss(server)

    @on(Button.Pressed, "#btn-cancel")
    def do_cancel(self) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ServerManagerScreen(ModalScreen):
    """Server list — select a server to connect, or manage servers."""

    BINDINGS = [
        Binding("escape", "cancel", "Close"),
        Binding("a", "add_server", "Add"),
        Binding("d", "delete_server", "Delete"),
        Binding("enter", "connect_selected", "Connect"),
    ]

    def __init__(self, store, **kwargs):
        super().__init__(**kwargs)
        self._store = store  # ServerStore instance

    def compose(self) -> ComposeResult:
        with Container(id="server-manager-dialog"):
            yield Label("[bold #00d4ff]  Server Manager[/bold #00d4ff]", classes="dialog-title")
            yield ListView(id="server-list")
            with Horizontal(id="server-buttons"):
                yield Button("  Connect", id="btn-connect", classes="safe")
                yield Button("  Add (a)", id="btn-add",     classes="safe")
                yield Button("  Delete (d)", id="btn-delete", classes="danger")
                yield Button("  Close",   id="btn-close",   classes="safe")

    def on_mount(self) -> None:
        self._refresh_list()

    def _refresh_list(self) -> None:
        lv = self.query_one("#server-list", ListView)
        lv.clear()
        servers = self._store.list_servers()
        if not servers:
            lv.append(ListItem(Label("[dim]No servers configured. Press 'a' to add one.[/dim]"), id="no-servers"))
        else:
            for s in servers:
                auth = s.get("auth_type", "password")
                host = s.get("host", "")
                port = s.get("port", 22)
                user = s.get("username", "")
                lv.append(ListItem(
                    Label(
                        f"[bold white]{s['name']}[/bold white]  "
                        f"[dim]{user}@{host}:{port}[/dim]  "
                        f"[#6080a0]{auth}[/#6080a0]"
                    ),
                    id=f"srv-{s['name']}",
                ))

    def _get_selected_server_name(self) -> str | None:
        lv = self.query_one("#server-list", ListView)
        if lv.highlighted_child and lv.highlighted_child.id:
            item_id = lv.highlighted_child.id
            if item_id.startswith("srv-"):
                return item_id[4:]
        return None

    @on(Button.Pressed, "#btn-connect")
    def action_connect_selected(self) -> None:
        name = self._get_selected_server_name()
        if not name:
            self.notify("Select a server first.", severity="warning")
            return
        server = self._store.get_server(name)
        self.dismiss(server)

    @on(ListView.Selected)
    def list_item_selected(self, event: ListView.Selected) -> None:
        if event.item.id and event.item.id.startswith("srv-"):
            name = event.item.id[4:]
            server = self._store.get_server(name)
            self.dismiss(server)

    @on(Button.Pressed, "#btn-add")
    def action_add_server(self) -> None:
        def handle(server: dict | None) -> None:
            if server:
                try:
                    self._store.add_server(server)
                    self.notify(f"Server '{server['name']}' saved.", severity="information")
                    self._refresh_list()
                except ValueError as e:
                    self.notify(str(e), severity="error")
        self.app.push_screen(AddServerScreen(), handle)

    @on(Button.Pressed, "#btn-delete")
    def action_delete_server(self) -> None:
        name = self._get_selected_server_name()
        if not name:
            self.notify("Select a server to delete.", severity="warning")
            return
        self._store.remove_server(name)
        self.notify(f"Server '{name}' deleted.", severity="information")
        self._refresh_list()

    @on(Button.Pressed, "#btn-close")
    def action_cancel(self) -> None:
        self.dismiss(None)


class SettingsScreen(ModalScreen[None]):
    """App settings: admin mode, startup, refresh interval."""

    BINDINGS = [Binding("escape", "cancel", "Close")]

    def compose(self) -> ComposeResult:
        is_admin = _is_admin()
        in_startup = _is_in_startup()
        admin_text = "[bold #ffcc00]YES (elevated)[/bold #ffcc00]" if is_admin else "[#ff6666]NO[/#ff6666]"
        startup_text = "[bold #00ff88]Enabled[/bold #00ff88]" if in_startup else "[dim]Disabled[/dim]"

        with Container(id="settings-dialog"):
            yield Label("[bold #00d4ff]  Settings[/bold #00d4ff]", classes="dialog-title")

            with Horizontal(classes="settings-row"):
                yield Label("Running as Administrator:", classes="settings-label")
                yield Label(admin_text, classes="settings-value", id="admin-status")

            with Horizontal(classes="settings-row"):
                yield Label("Run at Windows startup:", classes="settings-label")
                yield Label(startup_text, classes="settings-value", id="startup-status")

            with Horizontal(id="settings-buttons"):
                if not is_admin and IS_WINDOWS:
                    yield Button("  Restart as Admin", id="btn-restart-admin", classes="safe")
                if IS_WINDOWS:
                    label = "  Disable Startup" if in_startup else "  Enable Startup"
                    yield Button(label, id="btn-toggle-startup", classes="safe")
                yield Button("  Close", id="btn-close", classes="safe")

    @on(Button.Pressed, "#btn-restart-admin")
    def do_restart_admin(self) -> None:
        self.app.notify("Relaunching with elevated privileges…", severity="information")
        _restart_as_admin()
        self.app.exit()

    @on(Button.Pressed, "#btn-toggle-startup")
    def do_toggle_startup(self) -> None:
        current = _is_in_startup()
        _set_startup(not current)
        new_state = not current
        status = self.query_one("#startup-status", Label)
        if new_state:
            status.update("[bold #00ff88]Enabled[/bold #00ff88]")
            self.app.notify("HTopWin will launch at Windows startup.", severity="information")
        else:
            status.update("[dim]Disabled[/dim]")
            self.app.notify("Removed from Windows startup.", severity="information")
        # Relabel button
        try:
            btn = self.query_one("#btn-toggle-startup", Button)
            btn.label = "  Disable Startup" if new_state else "  Enable Startup"
        except Exception:
            pass

    @on(Button.Pressed, "#btn-close")
    def action_cancel(self) -> None:
        self.dismiss(None)


# ─────────────────────────────────────────────────────────
#  Process data collection
# ─────────────────────────────────────────────────────────
PROC_ATTRS = [
    "pid", "name", "username", "cpu_percent", "memory_percent",
    "num_threads", "status", "cmdline", "create_time",
]
if IS_WINDOWS:
    PROC_ATTRS.append("num_handles")


def collect_processes() -> list[dict]:
    """Collect process info using psutil, handling permission errors gracefully."""
    procs = []
    for proc in psutil.process_iter(PROC_ATTRS):
        try:
            info = proc.info  # type: ignore[attr-defined]
            info["cmdline_str"] = " ".join(info.get("cmdline") or []) or info.get("name", "")
            info["username"] = info.get("username") or "N/A"
            info["cpu_percent"] = info.get("cpu_percent") or 0.0
            info["memory_percent"] = info.get("memory_percent") or 0.0
            info["num_threads"] = info.get("num_threads") or 0
            if IS_WINDOWS:
                info["handles"] = info.get("num_handles") or 0
            procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return procs


def _collect_local_data():
    """Collect all local system data in one call (runs in a background thread)."""
    procs = collect_processes()
    per_cpu = psutil.cpu_percent(percpu=True)
    if isinstance(per_cpu, float):
        per_cpu = [per_cpu]
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return procs, per_cpu, mem, swap


# ─────────────────────────────────────────────────────────
#  Main App
# ─────────────────────────────────────────────────────────
COLUMNS = [
    ("pid",             "PID",      6,  False),
    ("name",            "Name",     20, False),
    ("username",        "User",     14, False),
    ("cpu_percent",     "CPU%",     7,  True),
    ("memory_percent",  "MEM%",     7,  True),
    ("num_threads",     "Threads",  7,  True),
    ("status",          "Status",   10, False),
    ("cmdline_str",     "Command",  0,  False),  # 0 = expand
]

STATUS_COLORS = {
    "running":  "#00ff88",
    "sleeping": "#6080b0",
    "disk-sleep": "#8060b0",
    "stopped":  "#ffaa00",
    "zombie":   "#ff4444",
    "dead":     "#884444",
    "idle":     "#608060",
}


def colorize_status(status: str) -> str:
    color = STATUS_COLORS.get(status.lower(), "#a0a0c0")
    return f"[{color}]{status}[/{color}]"


def colorize_cpu(pct: float) -> str:
    color = bar_color(pct)
    return f"[{color}]{pct:6.2f}[/{color}]"


def colorize_mem(pct: float) -> str:
    color = bar_color(pct)
    return f"[{color}]{pct:6.2f}[/{color}]"


class HTopWin(App):
    """htop for Windows — a terminal process manager."""

    TITLE = "HTopWin"
    CSS = APP_CSS

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit", "Quit", show=True),
        Binding("f10", "quit", "Quit", show=False),
        Binding("f2", "server_manager", "Servers", show=True),
        Binding("f4", "disconnect_remote", "Disconnect", show=False),
        Binding("k", "kill_process", "Kill", show=True),
        Binding("f9", "signal_menu", "Signal", show=True),
        Binding("f5", "refresh_now", "Refresh", show=True),
        Binding("f6", "sort_menu", "Sort", show=True),
        Binding("f8", "settings", "Settings", show=True),
        Binding("f3", "toggle_search", "Search", show=True),
        Binding("/", "toggle_search", "Search", show=False),
        Binding("escape", "clear_search", "Clear", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
    ]

    # Reactive state
    sort_key: reactive[str] = reactive("cpu_percent")
    sort_reverse: reactive[bool] = reactive(True)
    filter_text: reactive[str] = reactive("")
    search_visible: reactive[bool] = reactive(False)

    def __init__(self):
        super().__init__()
        self._processes: list[dict] = []
        self._selected_pid: int | None = None
        self._refresh_timer = None
        self._col_keys: list[str] = []
        self._remote_monitor = None   # RemoteMonitor instance when connected
        self._remote_info = None      # Last RemoteSystemInfo
        self._server_store = None     # ServerStore instance (loaded lazily)
        self._displayed_pids: list[str] = []  # tracks current table row order

    # ── Layout ──────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Container(id="top-panel"):
            with Horizontal():
                yield CpuBarsPanel(id="cpu-panel")
                yield MemBarsPanel(id="mem-panel")

        yield Static("", id="sysinfo-bar")

        with Horizontal(id="toolbar"):
            yield Static(" Filter: ", classes="toolbar-label")
            yield Input(placeholder="type to filter...", id="search-input")
            yield Static("", id="sort-label", classes="sort-indicator")

        yield DataTable(id="process-table", cursor_type="row", zebra_stripes=True)

        yield Static("", id="status-bar")
        yield Footer()

    # ── Mount ────────────────────────────────────────────

    def on_mount(self) -> None:
        self._setup_table()
        self._do_refresh()
        self._refresh_timer = self.set_interval(2.0, self._do_refresh)

    def _setup_table(self) -> None:
        table: DataTable = self.query_one("#process-table", DataTable)
        table.clear(columns=True)
        self._col_keys = []
        for key, label, width, _ in COLUMNS:
            if width == 0:
                col_key = table.add_column(label, key=key)
            else:
                col_key = table.add_column(label, width=width, key=key)
            self._col_keys.append(key)

    # ── Refresh ──────────────────────────────────────────

    def _do_refresh(self) -> None:
        """Kick off a background worker to collect data without blocking the UI."""
        self.run_worker(self._async_refresh, exclusive=True, thread=False)

    async def _async_refresh(self) -> None:
        """Collect all data off the main thread, then update widgets."""
        if self._remote_monitor and self._remote_monitor.connected:
            # ── Remote path ──────────────────────────────────────────────
            try:
                info = await asyncio.to_thread(self._remote_monitor.collect)
            except Exception as exc:
                self.notify(f"Remote collect error: {exc}", severity="error")
                self._remote_monitor = None
                await self._collect_and_update_local()
                return

            self._remote_info = info
            if info.error:
                self.notify(f"Remote error: {info.error}", severity="error")
                self._remote_monitor = None
                await self._collect_and_update_local()
            else:
                self._update_top_panel_remote(info)
                self._update_sysinfo_remote(info)
                self._processes = info.processes
                self._update_table()
                self._update_status_bar()
        else:
            await self._collect_and_update_local()

    async def _collect_and_update_local(self) -> None:
        """Collect local system data in a thread, then update all widgets."""
        procs, per_cpu, mem, swap = await asyncio.to_thread(_collect_local_data)
        self._processes = procs
        self._update_top_panel_with(per_cpu, mem, swap)
        self._update_sysinfo()
        self._update_table()
        self._update_status_bar()

    def _update_top_panel_with(self, per_cpu: list[float], mem, swap) -> None:
        try:
            cpu_panel = self.query_one("#cpu-panel", CpuBarsPanel)
            cpu_panel.refresh_stats(per_cpu)
        except NoMatches:
            pass
        try:
            mem_panel = self.query_one("#mem-panel", MemBarsPanel)
            mem_panel.refresh_stats(mem, swap)
        except NoMatches:
            pass

    def _update_top_panel_remote(self, info) -> None:
        """Update CPU and memory bars from a RemoteSystemInfo object."""
        try:
            cpu_panel = self.query_one("#cpu-panel", CpuBarsPanel)
            cpu_panel.refresh_stats(info.cpu_percents)
        except NoMatches:
            pass

        try:
            mem_bar = self.query_one("#mem-bar", BarWidget)
            used_str  = format_bytes(info.mem_used)
            total_str = format_bytes(info.mem_total)
            mem_bar.update_bar(info.mem_percent, f"{used_str}/{total_str}")
        except NoMatches:
            pass
        try:
            swp_bar = self.query_one("#swp-bar", BarWidget)
            if info.swap_total > 0:
                used_str  = format_bytes(info.swap_used)
                total_str = format_bytes(info.swap_total)
                swp_bar.update_bar(info.swap_percent, f"{used_str}/{total_str}")
            else:
                swp_bar.update_bar(0.0, "N/A")
        except NoMatches:
            pass

    def _update_sysinfo_remote(self, info) -> None:
        """Update the sysinfo strip with remote host data."""
        uptime_str = format_uptime(info.uptime_seconds)
        load       = info.load_avg
        load_str   = f"{load[0]:.2f} {load[1]:.2f} {load[2]:.2f}"
        cpu_count  = len(info.cpu_percents)

        parts = [
            f"[bold #00ff88]REMOTE:[/bold #00ff88] [white]{info.hostname}[/white]",
            f"[bold #00d4ff]Uptime:[/bold #00d4ff] [white]{uptime_str}[/white]",
            f"[bold #00d4ff]CPUs:[/bold #00d4ff] [white]{cpu_count}[/white]",
            f"[bold #00d4ff]Load:[/bold #00d4ff] [white]{load_str}[/white]",
        ]
        try:
            sysinfo = self.query_one("#sysinfo-bar", Static)
            sysinfo.update("   " + "  |  ".join(parts))
        except NoMatches:
            pass

    def _update_sysinfo(self) -> None:
        try:
            boot_time = psutil.boot_time()
            import time
            uptime = time.time() - boot_time
            uptime_str = format_uptime(uptime)
        except Exception:
            uptime_str = "N/A"

        try:
            freq = psutil.cpu_freq()
            freq_str = f"{freq.current:.0f} MHz" if freq else "N/A"
        except Exception:
            freq_str = "N/A"

        cpu_count_logical = psutil.cpu_count(logical=True) or 0
        cpu_count_physical = psutil.cpu_count(logical=False) or 0

        load_str = "N/A"
        if not IS_WINDOWS:
            try:
                loads = psutil.getloadavg()
                load_str = f"{loads[0]:.2f} {loads[1]:.2f} {loads[2]:.2f}"
            except Exception:
                pass

        parts = [
            f"[bold #00d4ff]Uptime:[/bold #00d4ff] [white]{uptime_str}[/white]",
            f"[bold #00d4ff]CPU:[/bold #00d4ff] [white]{cpu_count_physical}C/{cpu_count_logical}T[/white]",
            f"[bold #00d4ff]Freq:[/bold #00d4ff] [white]{freq_str}[/white]",
        ]
        if not IS_WINDOWS:
            parts.append(f"[bold #00d4ff]Load:[/bold #00d4ff] [white]{load_str}[/white]")

        try:
            sysinfo = self.query_one("#sysinfo-bar", Static)
            sysinfo.update("   " + "  |  ".join(parts))
        except NoMatches:
            pass

    def _sorted_filtered_procs(self) -> list[dict]:
        try:
            procs = sorted(
                self._processes,
                key=lambda p: (p.get(self.sort_key) or 0) if isinstance(p.get(self.sort_key), (int, float))
                else str(p.get(self.sort_key) or "").lower(),
                reverse=self.sort_reverse,
            )
        except Exception:
            procs = list(self._processes)
        ft = self.filter_text.lower()
        if ft:
            procs = [
                p for p in procs
                if ft in str(p.get("name", "")).lower()
                or ft in str(p.get("username", "")).lower()
                or ft in str(p.get("cmdline_str", "")).lower()
                or ft in str(p.get("pid", ""))
            ]
        return procs

    @staticmethod
    def _make_row(proc: dict) -> tuple:
        cpu = proc.get("cpu_percent", 0.0)
        mem = proc.get("memory_percent", 0.0)
        return (
            str(proc.get("pid", 0)),
            str(proc.get("name", ""))[:20],
            str(proc.get("username", "N/A"))[:14],
            colorize_cpu(cpu),
            colorize_mem(mem),
            str(proc.get("num_threads", 0)),
            colorize_status(str(proc.get("status", ""))),
            str(proc.get("cmdline_str", ""))[:120],
        )

    def _update_table(self, force_rebuild: bool = False) -> None:
        table: DataTable = self.query_one("#process-table", DataTable)
        procs = self._sorted_filtered_procs()
        new_pids = [str(p.get("pid", 0)) for p in procs]

        if force_rebuild or new_pids != self._displayed_pids:
            # ── Full rebuild (order changed or forced) ──────────────────
            try:
                cursor_key = str(
                    table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
                )
            except Exception:
                cursor_key = None

            table.clear()
            for proc in procs:
                table.add_row(*self._make_row(proc), key=str(proc.get("pid", 0)))
            self._displayed_pids = new_pids

            if cursor_key and cursor_key in new_pids:
                try:
                    table.move_cursor(row=new_pids.index(cursor_key))
                except Exception:
                    pass
        else:
            # ── Incremental update — only touch cells that change ───────
            for proc in procs:
                pid_str = str(proc.get("pid", 0))
                try:
                    table.update_cell(pid_str, "cpu_percent",    colorize_cpu(proc.get("cpu_percent", 0.0)),    update_width=False)
                    table.update_cell(pid_str, "memory_percent", colorize_mem(proc.get("memory_percent", 0.0)), update_width=False)
                    table.update_cell(pid_str, "status",         colorize_status(str(proc.get("status", ""))),  update_width=False)
                    table.update_cell(pid_str, "num_threads",    str(proc.get("num_threads", 0)),               update_width=False)
                except Exception:
                    pass

        # Update sort label
        sort_dir = "▼" if self.sort_reverse else "▲"
        col_display = next((label for key, label, *_ in COLUMNS if key == self.sort_key), self.sort_key)
        try:
            sort_label = self.query_one("#sort-label", Static)
            sort_label.update(f"[#00d4ff]Sort:[/#00d4ff] [white]{col_display} {sort_dir}[/white]")
        except NoMatches:
            pass

    def _update_status_bar(self) -> None:
        total    = len(self._processes)
        running  = sum(1 for p in self._processes if p.get("status") == "running")
        sleeping = sum(1 for p in self._processes if p.get("status") in ("sleeping", "idle"))
        zombie   = sum(1 for p in self._processes if p.get("status") == "zombie")

        ft = self.filter_text
        filter_info = f"  [bold #ffaa00]Filter:[/bold #ffaa00] [white]{ft}[/white]" if ft else ""

        # Remote badge
        remote_badge = ""
        if self._remote_monitor and self._remote_monitor.connected and self._remote_info:
            hostname = self._remote_info.hostname or "remote"
            remote_badge = f"  [bold #00ff88][ REMOTE: {hostname} ][/bold #00ff88]"

        msg = (
            f"  [bold #00d4ff]Tasks:[/bold #00d4ff] [white]{total}[/white]"
            f"  [bold #00ff88]Running:[/bold #00ff88] [white]{running}[/white]"
            f"  [bold #6080b0]Sleeping:[/bold #6080b0] [white]{sleeping}[/white]"
        )
        if zombie:
            msg += f"  [bold #ff4444]Zombie:[/bold #ff4444] [white]{zombie}[/white]"
        msg += filter_info
        msg += remote_badge

        try:
            bar = self.query_one("#status-bar", Static)
            bar.update(msg)
        except NoMatches:
            pass

    # ── Actions ──────────────────────────────────────────

    def action_refresh_now(self) -> None:
        self._do_refresh()

    def action_quit(self) -> None:
        self.exit()

    def _get_selected_proc_info(self) -> tuple[int, str] | None:
        """Return (pid, name) of the currently selected row, or None."""
        table: DataTable = self.query_one("#process-table", DataTable)
        try:
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
            pid = int(row_key.value)  # type: ignore[arg-type]
            # Find name
            name = next(
                (str(p.get("name", "")) for p in self._processes if p.get("pid") == pid),
                "Unknown",
            )
            return pid, name
        except Exception:
            return None

    def action_kill_process(self) -> None:
        info = self._get_selected_proc_info()
        if info is None:
            self.notify("No process selected.", severity="warning")
            return
        pid, name = info

        def handle_result(confirmed: bool | None) -> None:
            if confirmed:
                self._send_signal_to_pid(pid, 9)

        self.push_screen(KillConfirmScreen(pid, name), handle_result)

    def action_signal_menu(self) -> None:
        info = self._get_selected_proc_info()
        if info is None:
            self.notify("No process selected.", severity="warning")
            return
        pid, name = info

        def handle_result(sig_val: int | None) -> None:
            if sig_val is not None:
                self._send_signal_to_pid(pid, sig_val)

        self.push_screen(SignalMenuScreen(pid, name), handle_result)

    def action_sort_menu(self) -> None:
        def handle_result(key: str | None) -> None:
            if key:
                if self.sort_key == key:
                    self.sort_reverse = not self.sort_reverse
                else:
                    self.sort_key = key
                    self.sort_reverse = True
                self._update_table(force_rebuild=True)

        self.push_screen(SortMenuScreen(), handle_result)

    def action_server_manager(self) -> None:
        """Open the server manager (F2).  Prompts for master password first."""
        def handle_password(password: str | None) -> None:
            if password is None:
                return
            try:
                from server_manager import ServerStore
            except ImportError:
                self.notify(
                    "Install cryptography: pip install cryptography",
                    severity="error",
                )
                return
            try:
                store = ServerStore(password)
            except ValueError as e:
                self.notify(str(e), severity="error")
                return
            except Exception as e:
                self.notify(f"Could not open store: {e}", severity="error")
                return

            self._server_store = store

            def handle_server(server: dict | None) -> None:
                if server:
                    self._connect_to_server(server)

            self.push_screen(ServerManagerScreen(store), handle_server)

        self.push_screen(MasterPasswordScreen(), handle_password)

    def _connect_to_server(self, server: dict) -> None:
        """Connect to *server* via SSH and start remote monitoring."""
        try:
            from remote_monitor import RemoteMonitor
        except ImportError:
            self.notify(
                "Install paramiko and cryptography: pip install paramiko cryptography",
                severity="error",
            )
            return

        # Disconnect any previous session
        if self._remote_monitor is not None:
            try:
                self._remote_monitor.disconnect()
            except Exception:
                pass
            self._remote_monitor = None
            self._remote_info    = None

        name = server.get("name", server.get("host", "server"))
        self.notify(f"Connecting to {name}...", severity="information")

        monitor = RemoteMonitor(server)
        try:
            monitor.connect()
        except ImportError:
            self.notify(
                "Install paramiko: pip install paramiko",
                severity="error",
            )
            return
        except Exception as exc:
            self.notify(f"SSH connection failed: {exc}", severity="error")
            return

        self._remote_monitor = monitor
        self.notify(f"Connected to {name}.", severity="information")
        self._do_refresh()

    def action_disconnect_remote(self) -> None:
        """Disconnect from remote host and return to local monitoring (F4)."""
        if self._remote_monitor is None:
            self.notify("Not connected to a remote host.", severity="warning")
            return
        try:
            self._remote_monitor.disconnect()
        except Exception:
            pass
        self._remote_monitor = None
        self._remote_info    = None
        self.notify("Disconnected — showing local system.", severity="information")
        self._do_refresh()

    def action_settings(self) -> None:
        self.push_screen(SettingsScreen())

    def action_toggle_search(self) -> None:
        self.search_visible = not self.search_visible
        search_input = self.query_one("#search-input", Input)
        if self.search_visible:
            search_input.add_class("visible")
            search_input.focus()
        else:
            search_input.remove_class("visible")
            self.filter_text = ""
            search_input.value = ""
            self._update_table()
            self._update_status_bar()
            self.query_one("#process-table", DataTable).focus()

    def action_clear_search(self) -> None:
        if self.search_visible:
            self.action_toggle_search()

    def action_cursor_up(self) -> None:
        table = self.query_one("#process-table", DataTable)
        table.focus()
        table.action_scroll_up()

    def action_cursor_down(self) -> None:
        table = self.query_one("#process-table", DataTable)
        table.focus()
        table.action_scroll_down()

    def _send_signal_to_pid(self, pid: int, sig: int) -> None:
        try:
            proc = psutil.Process(pid)
            if IS_WINDOWS:
                if sig == 9:
                    proc.kill()
                else:
                    proc.terminate()
            else:
                proc.send_signal(sig)
            self.notify(f"Signal {sig} sent to PID {pid}.", severity="information")
            self._do_refresh()
        except psutil.NoSuchProcess:
            self.notify(f"PID {pid} no longer exists.", severity="warning")
        except psutil.AccessDenied:
            self.notify(f"Access denied — cannot signal PID {pid}.", severity="error")
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    # ── Event handlers ───────────────────────────────────

    @on(Input.Changed, "#search-input")
    def search_changed(self, event: Input.Changed) -> None:
        self.filter_text = event.value
        self._update_table(force_rebuild=True)
        self._update_status_bar()

    @on(DataTable.HeaderSelected)
    def header_clicked(self, event: DataTable.HeaderSelected) -> None:
        col_key = str(event.column_key.value)
        if col_key == self.sort_key:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_key = col_key
            self.sort_reverse = True
        self._update_table(force_rebuild=True)

    @on(DataTable.RowSelected)
    def row_selected(self, event: DataTable.RowSelected) -> None:
        try:
            self._selected_pid = int(str(event.row_key.value))
        except Exception:
            self._selected_pid = None


# ─────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────
def main() -> None:
    if sys.platform == "win32":
        # Enable ANSI color codes on Windows
        import os
        os.system("")

    app = HTopWin()
    app.run()


if __name__ == "__main__":
    main()
