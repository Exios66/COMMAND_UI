from __future__ import annotations

import os
import platform
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import psutil


@dataclass(frozen=True)
class SystemSummary:
    hostname: str
    platform: str
    kernel: str
    uptime_s: float
    loadavg: tuple[float, float, float] | None
    cpu_percent: float
    cpu_freq_mhz: float | None
    mem_total: int
    mem_used: int
    mem_available: int
    swap_total: int
    swap_used: int
    disk_total: int
    disk_used: int
    disk_free: int
    net_sent: int
    net_recv: int
    package_power_w: float | None


@dataclass(frozen=True)
class ProcRow:
    pid: int
    name: str
    user: str | None
    cpu: float
    mem: float
    read_b: int | None
    write_b: int | None


@dataclass(frozen=True)
class ServiceRow:
    name: str
    description: str
    active: str


class PowerReader:
    """Best-effort package power estimation on Linux.

    - Intel RAPL (energy_uj): /sys/class/powercap/**/energy_uj
    - Battery power_now if present: /sys/class/power_supply/BAT*/power_now

    If unavailable, returns None.
    """

    def __init__(self) -> None:
        self._prev_energy_uj: int | None = None
        self._prev_t: float | None = None
        self._rapl_paths: list[Path] = self._discover_rapl_energy_paths()

    def _discover_rapl_energy_paths(self) -> list[Path]:
        root = Path("/sys/class/powercap")
        if not root.exists():
            return []
        return sorted(root.glob("**/energy_uj"))

    def _read_int(self, path: Path) -> int | None:
        try:
            return int(path.read_text().strip())
        except Exception:
            return None

    def read_package_power_w(self) -> float | None:
        # Prefer direct battery power if available
        for bat in Path("/sys/class/power_supply").glob("BAT*/power_now"):
            v = self._read_int(bat)
            # power_now is typically in microwatts
            if v is not None and v > 0:
                return v / 1_000_000.0

        # Fall back to RAPL energy delta if available
        if not self._rapl_paths:
            return None
        energies: list[int] = []
        for p in self._rapl_paths:
            v = self._read_int(p)
            if v is not None:
                energies.append(v)
        if not energies:
            return None

        total_energy_uj = sum(energies)
        now = time.time()

        if self._prev_energy_uj is None or self._prev_t is None:
            self._prev_energy_uj = total_energy_uj
            self._prev_t = now
            return None

        dt = now - self._prev_t
        de = total_energy_uj - self._prev_energy_uj
        self._prev_energy_uj = total_energy_uj
        self._prev_t = now

        if dt <= 0 or de < 0:
            return None

        joules = de / 1_000_000.0
        return joules / dt


def _safe_loadavg() -> tuple[float, float, float] | None:
    try:
        return os.getloadavg()
    except Exception:
        return None


def _uptime_s() -> float:
    try:
        return time.time() - psutil.boot_time()
    except Exception:
        return 0.0


def get_system_summary(power: PowerReader) -> SystemSummary:
    vm = psutil.virtual_memory()
    sm = psutil.swap_memory()
    du = psutil.disk_usage("/")
    net = psutil.net_io_counters()

    cpu_percent = psutil.cpu_percent(interval=None)

    freq = None
    try:
        f = psutil.cpu_freq()
        if f is not None:
            freq = float(f.current)
    except Exception:
        freq = None

    return SystemSummary(
        hostname=platform.node(),
        platform=f"{platform.system()} {platform.release()}",
        kernel=platform.version(),
        uptime_s=_uptime_s(),
        loadavg=_safe_loadavg(),
        cpu_percent=float(cpu_percent),
        cpu_freq_mhz=freq,
        mem_total=int(vm.total),
        mem_used=int(vm.used),
        mem_available=int(vm.available),
        swap_total=int(sm.total),
        swap_used=int(sm.used),
        disk_total=int(du.total),
        disk_used=int(du.used),
        disk_free=int(du.free),
        net_sent=int(net.bytes_sent),
        net_recv=int(net.bytes_recv),
        package_power_w=power.read_package_power_w(),
    )


def prime_process_cpu() -> None:
    """Prime psutil per-process CPU so the first refresh isn't all zeros."""
    try:
        for p in psutil.process_iter(attrs=[]):
            try:
                p.cpu_percent(interval=None)
            except Exception:
                continue
    except Exception:
        return


def get_top_processes(limit: int = 25) -> list[ProcRow]:
    rows: list[ProcRow] = []
    for p in psutil.process_iter(
        attrs=["pid", "name", "username", "cpu_percent", "memory_percent"],
        ad_value=None,
    ):
        try:
            info = p.info
            io = None
            try:
                io = p.io_counters()
            except Exception:
                io = None
            rows.append(
                ProcRow(
                    pid=int(info.get("pid") or 0),
                    name=str(info.get("name") or ""),
                    user=(info.get("username") if info.get("username") else None),
                    cpu=float(info.get("cpu_percent") or 0.0),
                    mem=float(info.get("memory_percent") or 0.0),
                    read_b=(int(io.read_bytes) if io else None),
                    write_b=(int(io.write_bytes) if io else None),
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        except Exception:
            continue

    rows.sort(key=lambda r: (r.cpu, r.mem), reverse=True)
    return rows[:limit]


def _which(cmd: str) -> str | None:
    for p in os.environ.get("PATH", "").split(os.pathsep):
        cand = Path(p) / cmd
        if cand.exists() and os.access(cand, os.X_OK):
            return str(cand)
    return None


class DiagnosticsFeed:
    """Incremental diagnostics feed from journalctl (preferred) or dmesg fallback.

    This is stateful: it keeps a rolling buffer and uses journal cursors (or a
    dmesg tail diff) to return only new lines between polls.
    """

    def __init__(self, limit: int = 120) -> None:
        self.limit = max(1, int(limit))
        self._buffer: deque[str] = deque(maxlen=self.limit)

        self._backend: str | None = None  # "journal" | "dmesg"
        self._journalctl = _which("journalctl")
        self._dmesg = _which("dmesg")

        self._cursor: str | None = None
        self._journal_tail: str | None = None
        self._dmesg_tail: str | None = None

    def snapshot(self) -> list[str]:
        """Return the current buffer, oldest-first."""
        return list(self._buffer)

    def poll(self) -> tuple[list[str], bool]:
        """Poll for new diagnostics.

        Returns (lines, reset_required). If reset_required is True, `lines`
        contains a full snapshot to display (e.g., initial fill or backend
        switch). Otherwise, `lines` contains only new entries to append.
        """
        if self._backend is None:
            if self._journalctl is not None:
                self._backend = "journal"
            elif self._dmesg is not None:
                self._backend = "dmesg"
            else:
                return ([], True)

        if self._backend == "journal" and self._journalctl is not None:
            lines, reset = self._poll_journalctl()
            if lines or reset:
                return (lines, reset)
            # If journal is empty, keep using it; caller can keep prior view.
            return ([], False)

        if self._backend == "dmesg" and self._dmesg is not None:
            return self._poll_dmesg(force_reset=False)

        # Tool disappeared or was never available; force a reset to empty.
        self._buffer.clear()
        self._backend = None
        self._cursor = None
        self._dmesg_tail = None
        return ([], True)

    def _extract_cursor(self, raw_lines: list[str]) -> str | None:
        for ln in reversed(raw_lines):
            if ln.startswith("-- cursor:"):
                v = ln.split(":", 1)[1].strip()
                return v or None
        return None

    def _filter_journal_lines(self, raw_lines: list[str]) -> list[str]:
        out: list[str] = []
        for ln in raw_lines:
            ln = ln.rstrip()
            if not ln:
                continue
            if ln == "-- No entries --":
                continue
            if ln.startswith("-- cursor:"):
                continue
            out.append(ln)
        return out

    def _poll_journalctl(self) -> tuple[list[str], bool]:
        import subprocess

        # `-p 0..4` => emerg..warning (includes errors).
        argv: list[str] = [
            self._journalctl or "journalctl",
            "--no-pager",
            "--output",
            "short-iso",
            "-p",
            "0..4",
            "--show-cursor",
        ]

        reset_required = False
        if self._cursor:
            argv += ["--after-cursor", self._cursor]
        else:
            argv += ["-n", str(self.limit)]
            # If we don't have a cursor (or it's unsupported), avoid treating
            # every poll as a full reset. We'll diff by the last seen line.
            reset_required = len(self._buffer) == 0

        try:
            out = subprocess.check_output(
                argv,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=1.5,
            )
        except Exception:
            # Fall back to dmesg if available; otherwise surface empty reset.
            if self._dmesg is not None:
                self._backend = "dmesg"
                self._cursor = None
                return self._poll_dmesg(force_reset=True)
            self._buffer.clear()
            self._cursor = None
            return ([], True)

        raw_lines = out.splitlines()
        cursor = self._extract_cursor(raw_lines)
        if cursor:
            self._cursor = cursor

        lines = self._filter_journal_lines(raw_lines)

        if reset_required:
            self._buffer.clear()
            for ln in lines[-self.limit :]:
                self._buffer.append(ln)
            self._journal_tail = self._buffer[-1] if self._buffer else None
            return (self.snapshot(), True)

        if self._cursor:
            # Incremental update: append only new lines returned by after-cursor.
            new_lines = lines
            for ln in new_lines:
                self._buffer.append(ln)
            if new_lines:
                self._journal_tail = self._buffer[-1] if self._buffer else None
            return (new_lines, False)

        # Cursor unavailable (common when there are no matching entries or older
        # setups). Fall back to tail diff similar to dmesg.
        if self._journal_tail is None:
            self._buffer.clear()
            for ln in lines[-self.limit :]:
                self._buffer.append(ln)
            self._journal_tail = self._buffer[-1] if self._buffer else None
            return (self.snapshot(), True)

        last = self._journal_tail
        last_idx: int | None = None
        for i in range(len(lines) - 1, -1, -1):
            if lines[i] == last:
                last_idx = i
                break
        if last_idx is None:
            self._buffer.clear()
            for ln in lines[-self.limit :]:
                self._buffer.append(ln)
            self._journal_tail = self._buffer[-1] if self._buffer else None
            return (self.snapshot(), True)

        new_lines = lines[last_idx + 1 :]
        for ln in new_lines:
            self._buffer.append(ln)
        self._journal_tail = self._buffer[-1] if self._buffer else None
        return (new_lines, False)

    def _poll_dmesg(self, force_reset: bool) -> tuple[list[str], bool]:
        import subprocess

        if self._dmesg is None:
            self._buffer.clear()
            self._dmesg_tail = None
            return ([], True)

        candidates: list[list[str]] = [
            [self._dmesg, "--color=never", "--level=err,warn", "--ctime"],
            [self._dmesg, "--color=never", "--level=err,warn"],
            [self._dmesg, "--level=err,warn", "--ctime"],
            [self._dmesg, "--level=err,warn"],
            [self._dmesg, "--ctime"],
            [self._dmesg],
        ]

        out: str | None = None
        for argv in candidates:
            try:
                out = subprocess.check_output(
                    argv,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=1.5,
                )
                break
            except Exception:
                continue

        if out is None:
            self._buffer.clear()
            self._dmesg_tail = None
            return ([], True)

        all_lines = [ln.rstrip() for ln in out.splitlines() if ln.strip()]
        tail = all_lines[-self.limit :]

        if force_reset or self._dmesg_tail is None:
            self._buffer.clear()
            for ln in tail:
                self._buffer.append(ln)
            self._dmesg_tail = tail[-1] if tail else None
            return (self.snapshot(), True)

        # Find the last previously-seen line and return everything after it.
        last = self._dmesg_tail
        last_idx: int | None = None
        for i in range(len(all_lines) - 1, -1, -1):
            if all_lines[i] == last:
                last_idx = i
                break

        if last_idx is None:
            # Lost sync (ring buffer wrapped or output format changed).
            self._buffer.clear()
            for ln in tail:
                self._buffer.append(ln)
            self._dmesg_tail = tail[-1] if tail else None
            return (self.snapshot(), True)

        new_lines = all_lines[last_idx + 1 :]
        for ln in new_lines:
            self._buffer.append(ln)
        self._dmesg_tail = self._buffer[-1] if self._buffer else None
        return (new_lines, False)


def get_running_services(limit: int = 25) -> list[ServiceRow]:
    """Best-effort 'background operations' via systemd services."""
    systemctl = _which("systemctl")
    if systemctl is None:
        return []

    import subprocess

    try:
        out = subprocess.check_output(
            [
                systemctl,
                "--no-pager",
                "--plain",
                "--state=running",
                "--type=service",
                "list-units",
            ],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=2.0,
        )
    except Exception:
        return []

    rows: list[ServiceRow] = []
    for line in out.splitlines():
        if not line or line.startswith("UNIT ") or line.startswith("LOAD "):
            continue
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        unit, _load, active, _sub, desc = parts
        rows.append(ServiceRow(name=unit, description=desc, active=active))
        if len(rows) >= limit:
            break
    return rows


def get_recent_diagnostics(limit: int = 120) -> list[str]:
    """Best-effort recent warnings/errors for the live diagnostics feed.

    Prefers systemd journal when available; falls back to dmesg.
    Returns newest-last lines (chronological display).
    """
    feed = DiagnosticsFeed(limit=limit)
    lines, _reset = feed.poll()
    return lines[-max(1, int(limit)) :]


def format_bytes(n: int) -> str:
    if n < 0:
        return "0B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    v = float(n)
    i = 0
    while v >= 1024.0 and i < len(units) - 1:
        v /= 1024.0
        i += 1
    if i == 0:
        return f"{int(v)}{units[i]}"
    return f"{v:.1f}{units[i]}"


def format_uptime(seconds: float) -> str:
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    if d:
        return f"{d}d {h:02d}:{m:02d}:{s:02d}"
    return f"{h:02d}:{m:02d}:{s:02d}"
