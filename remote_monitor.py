"""
remote_monitor.py — SSH-based remote system monitor for HTopWin.

Uses paramiko to connect to a remote Linux host and collects system
statistics by reading /proc files and running 'ps aux'.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


# ── Data class ─────────────────────────────────────────────────────────────────

@dataclass
class RemoteSystemInfo:
    hostname: str = ""
    uptime_seconds: float = 0.0
    cpu_percents: list[float] = field(default_factory=list)
    mem_total: int = 0
    mem_used: int = 0
    mem_percent: float = 0.0
    swap_total: int = 0
    swap_used: int = 0
    swap_percent: float = 0.0
    load_avg: tuple[float, float, float] = (0.0, 0.0, 0.0)
    processes: list[dict] = field(default_factory=list)
    error: str | None = None


# ── Helper parsers ─────────────────────────────────────────────────────────────

def _parse_cpu_percent(stat1: str, stat2: str) -> list[float]:
    """
    Given two /proc/stat snapshots taken ~0.2 s apart, return per-CPU
    usage percentages.  Lines that do not start with 'cpu' (lower-case
    followed by a digit) are ignored.
    """
    def _extract(lines: list[str]) -> dict[str, list[int]]:
        result: dict[str, list[int]] = {}
        for line in lines:
            parts = line.split()
            if len(parts) < 5:
                continue
            name = parts[0]
            if name == "cpu" or (name.startswith("cpu") and name[3:].isdigit()):
                result[name] = [int(x) for x in parts[1:]]
        return result

    data1 = _extract(stat1.splitlines())
    data2 = _extract(stat2.splitlines())

    percents: list[float] = []
    # Collect individual cores in order
    core_names = sorted(
        [k for k in data1 if k != "cpu" and k[3:].isdigit()],
        key=lambda k: int(k[3:]),
    )
    if not core_names:
        # Single-core — fall back to aggregate line
        core_names = ["cpu"] if "cpu" in data1 else []

    for name in core_names:
        v1 = data1.get(name)
        v2 = data2.get(name)
        if v1 is None or v2 is None:
            percents.append(0.0)
            continue

        # Pad to at least 8 elements (user nice system idle iowait irq softirq steal)
        while len(v1) < 8:
            v1.append(0)
        while len(v2) < 8:
            v2.append(0)

        idle1 = v1[3]
        idle2 = v2[3]
        total1 = sum(v1)
        total2 = sum(v2)

        delta_total = total2 - total1
        delta_idle  = idle2  - idle1

        if delta_total <= 0:
            percents.append(0.0)
        else:
            pct = 100.0 * (delta_total - delta_idle) / delta_total
            percents.append(round(max(0.0, min(100.0, pct)), 1))

    return percents


def _parse_meminfo(text: str) -> dict[str, int]:
    """
    Parse /proc/meminfo and return a dict of key → kB values.
    """
    result: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split(":")
        if len(parts) != 2:
            continue
        key = parts[0].strip()
        val_parts = parts[1].strip().split()
        try:
            result[key] = int(val_parts[0])
        except (IndexError, ValueError):
            pass
    return result


def _map_ps_status(stat_char: str) -> str:
    """Map the first character of a ps STAT column to a human-readable status."""
    mapping = {
        "R": "running",
        "S": "sleeping",
        "D": "disk-sleep",
        "Z": "zombie",
        "T": "stopped",
        "t": "stopped",
        "X": "dead",
        "I": "idle",
        "W": "paging",
    }
    return mapping.get(stat_char.upper()[:1] if stat_char else "", "unknown")


def _parse_ps_aux(text: str) -> list[dict]:
    """
    Parse the output of 'ps aux --no-headers' (or the body after the header)
    into a list of process dicts compatible with HTopWin's table schema.
    """
    procs: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 10)
        if len(parts) < 10:
            continue
        try:
            pid         = int(parts[1])
            cpu_percent = float(parts[2])
            mem_percent = float(parts[3])
            stat        = parts[7]
            status      = _map_ps_status(stat)
            username    = parts[0][:14]
            # Command is everything after the 10th field; fall back to parts[10]
            cmd         = parts[10].strip() if len(parts) > 10 else ""
            # Extract the bare executable name (basename of first token)
            name_token  = cmd.split()[0] if cmd else ""
            name        = name_token.split("/")[-1][:20] if name_token else ""

            procs.append({
                "pid":            pid,
                "name":           name,
                "username":       username,
                "cpu_percent":    cpu_percent,
                "memory_percent": mem_percent,
                "num_threads":    0,   # not available from ps aux
                "status":         status,
                "cmdline_str":    cmd[:120],
            })
        except (ValueError, IndexError):
            continue
    return procs


# ── Main class ─────────────────────────────────────────────────────────────────

class RemoteMonitor:
    """
    SSH-based system monitor.

    Parameters
    ----------
    server:
        A server dict as stored by ``ServerStore``, containing at least:
        ``host``, ``port``, ``username``, and either ``password`` or
        ``key_path`` depending on ``auth_type``.
    """

    def __init__(self, server: dict) -> None:
        self._server = server
        self._client = None  # paramiko.SSHClient
        self._connected: bool = False

    # ── Connection management ─────────────────────────────────────────────────

    def connect(self) -> None:
        """
        Open an SSH connection to the server.

        Raises
        ------
        ImportError
            If paramiko is not installed.
        Exception
            Any paramiko / socket exception on connection failure.
        """
        import paramiko  # lazy import — let caller catch ImportError

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        host     = self._server.get("host", "")
        port     = int(self._server.get("port", 22))
        username = self._server.get("username", "")
        auth_type = self._server.get("auth_type", "password")
        password  = self._server.get("password") or None
        key_path  = self._server.get("key_path") or None

        connect_kwargs: dict = dict(
            hostname=host,
            port=port,
            username=username,
            timeout=10,
        )

        if auth_type == "key" and key_path:
            connect_kwargs["key_filename"] = key_path
            if password:
                connect_kwargs["passphrase"] = password
        else:
            if password:
                connect_kwargs["password"] = password

        client.connect(**connect_kwargs)
        self._client = client
        self._connected = True

    def disconnect(self) -> None:
        """Close the SSH connection."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None
        self._connected = False

    @property
    def connected(self) -> bool:
        """True if the SSH connection is currently open."""
        return self._connected

    # ── Data collection ───────────────────────────────────────────────────────

    def _run(self, cmd: str) -> str:
        """Execute a command over SSH and return stdout as a string."""
        if self._client is None:
            raise RuntimeError("Not connected.")
        _, stdout, _ = self._client.exec_command(cmd, timeout=15)
        return stdout.read().decode("utf-8", errors="replace")

    def collect(self) -> RemoteSystemInfo:
        """
        Collect system statistics from the remote host.

        On any error the returned ``RemoteSystemInfo.error`` field is set and
        ``self._connected`` is set to ``False``.
        """
        info = RemoteSystemInfo()
        try:
            # ── Hostname ──────────────────────────────────────────────────────
            info.hostname = self._run("hostname").strip()

            # ── CPU usage — two /proc/stat snapshots 0.2 s apart ─────────────
            stat1 = self._run("cat /proc/stat")
            time.sleep(0.2)
            stat2 = self._run("cat /proc/stat")
            info.cpu_percents = _parse_cpu_percent(stat1, stat2)

            # ── Memory ────────────────────────────────────────────────────────
            meminfo_text = self._run("cat /proc/meminfo")
            mem = _parse_meminfo(meminfo_text)

            mem_total_kb    = mem.get("MemTotal",     0)
            mem_free_kb     = mem.get("MemFree",      0)
            mem_buffers_kb  = mem.get("Buffers",      0)
            mem_cached_kb   = mem.get("Cached",       0)
            mem_sreclaimable= mem.get("SReclaimable", 0)
            mem_shmem_kb    = mem.get("Shmem",        0)

            mem_available_kb = mem.get(
                "MemAvailable",
                mem_free_kb + mem_buffers_kb + mem_cached_kb,
            )
            mem_used_kb = mem_total_kb - mem_available_kb

            info.mem_total   = mem_total_kb * 1024
            info.mem_used    = max(0, mem_used_kb * 1024)
            info.mem_percent = (
                round(info.mem_used / info.mem_total * 100, 1)
                if info.mem_total > 0 else 0.0
            )

            swap_total_kb = mem.get("SwapTotal", 0)
            swap_free_kb  = mem.get("SwapFree",  0)
            swap_used_kb  = max(0, swap_total_kb - swap_free_kb)
            info.swap_total   = swap_total_kb * 1024
            info.swap_used    = swap_used_kb  * 1024
            info.swap_percent = (
                round(info.swap_used / info.swap_total * 100, 1)
                if info.swap_total > 0 else 0.0
            )

            # ── Uptime ────────────────────────────────────────────────────────
            uptime_text = self._run("cat /proc/uptime").strip()
            try:
                info.uptime_seconds = float(uptime_text.split()[0])
            except (ValueError, IndexError):
                info.uptime_seconds = 0.0

            # ── Load average ──────────────────────────────────────────────────
            loadavg_text = self._run("cat /proc/loadavg").strip()
            try:
                parts = loadavg_text.split()
                info.load_avg = (
                    float(parts[0]),
                    float(parts[1]),
                    float(parts[2]),
                )
            except (ValueError, IndexError):
                info.load_avg = (0.0, 0.0, 0.0)

            # ── Process list ──────────────────────────────────────────────────
            try:
                ps_out = self._run("ps aux --no-headers")
            except Exception:
                # Fallback: skip the header line
                ps_out = self._run("ps aux | tail -n +2")
            info.processes = _parse_ps_aux(ps_out)

        except Exception as exc:
            info.error = str(exc)
            self._connected = False

        return info
