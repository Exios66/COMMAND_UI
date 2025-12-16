from __future__ import annotations

import os
import platform
import time
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
    import subprocess

    limit = max(1, int(limit))

    journalctl = _which("journalctl")
    if journalctl is not None:
        try:
            out = subprocess.check_output(
                [
                    journalctl,
                    "--no-pager",
                    "--output",
                    "short-iso",
                    "-p",
                    "0..4",  # emerg..warning
                    "-n",
                    str(limit),
                ],
                stderr=subprocess.STDOUT,
                text=True,
                timeout=2.0,
            )
            lines = [ln.rstrip() for ln in out.splitlines() if ln.strip()]
            return lines[-limit:]
        except Exception:
            pass

    dmesg = _which("dmesg")
    if dmesg is None:
        return []

    # Try a few common dmesg flag variants across distros.
    candidates: list[list[str]] = [
        [dmesg, "--color=never", "--level=err,warn", "--ctime"],
        [dmesg, "--color=never", "--level=err,warn"],
        [dmesg, "--ctime"],
        [dmesg],
    ]
    for argv in candidates:
        try:
            out = subprocess.check_output(
                argv,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=2.0,
            )
            lines = [ln.rstrip() for ln in out.splitlines() if ln.strip()]
            return lines[-limit:]
        except Exception:
            continue

    return []


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
