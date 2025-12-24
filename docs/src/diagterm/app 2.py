from __future__ import annotations

from datetime import datetime

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Log, Static

from diagterm.collectors import (
    DiagnosticsFeed,
    PowerReader,
    format_bytes,
    format_uptime,
    get_running_services,
    get_system_summary,
    get_top_processes,
    prime_process_cpu,
)
from diagterm.executor import run_shell_command


class ConfirmRun(ModalScreen[bool]):
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, cmd: str) -> None:
        super().__init__()
        self.cmd = cmd

    def compose(self) -> ComposeResult:
        yield Container(
            Static("Confirm command execution", classes="title"),
            Static(self.cmd, classes="cmd"),
            Horizontal(
                Button("Cancel", variant="default", id="cancel"),
                Button("Run", variant="error", id="run"),
                classes="buttons",
            ),
            classes="modal",
        )

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#run")
    def _run(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class DiagTermApp(App):
    """Live diagnostics terminal UI + command runner."""

    CSS = """
    Screen { layout: vertical; }

    .grid { height: 1fr; }

    .modal {
      width: 90%;
      max-width: 120;
      padding: 1;
      border: solid $accent;
      background: $panel;
    }

    .title { content-align: center middle; text-style: bold; padding-bottom: 1; }
    .cmd { padding: 0 1; }

    .buttons { height: auto; content-align: center middle; padding-top: 1; }

    #summary { height: auto; border: solid $primary; padding: 1; }
    #diag_panel { height: 12; border: solid $primary; }
    #services { height: 1fr; border: solid $primary; }
    #procs { height: 1fr; border: solid $primary; }
    #runner { height: 12; border: solid $primary; }

    #cmd_input { width: 1fr; }
    #run_btn { width: 12; }

    Log { height: 1fr; }
    """

    BINDINGS = [
        ("ctrl+r", "refresh", "Refresh now"),
        ("ctrl+l", "clear_log", "Clear log"),
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self, refresh_interval: float = 1.0) -> None:
        super().__init__()
        self.refresh_interval = max(0.5, float(refresh_interval))
        self.power = PowerReader()
        self.diag_feed = DiagnosticsFeed(limit=200)
        self._busy = False
        self._diag_initialized = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Vertical(classes="grid"):
            yield Static("", id="summary")
            with Vertical(id="diag_panel"):
                yield Static("Diagnostics feed (warnings/errors)", id="diag_title")
                yield Log(id="diag_log", highlight=False)

            with Horizontal():
                yield DataTable(id="procs")
                yield DataTable(id="services")

            with Vertical(id="runner"):
                yield Static("Command runner (executes in your shell).", id="runner_title")
                with Horizontal():
                    yield Input(placeholder="Enter a command, e.g.: df -h && free -h", id="cmd_input")
                    yield Button("Run", id="run_btn", variant="primary")
                yield Log(id="cmd_log", highlight=True)

        yield Footer()

    async def on_mount(self) -> None:
        self.title = "DiagTerm"
        prime_process_cpu()

        procs = self.query_one("#procs", DataTable)
        procs.add_columns("PID", "Name", "User", "CPU%", "MEM%", "IO R", "IO W")
        procs.cursor_type = "row"

        services = self.query_one("#services", DataTable)
        services.add_columns("Service", "Active", "Description")
        services.cursor_type = "row"

        self.set_interval(self.refresh_interval, self._update_display)
        self._update_display()

    def action_refresh(self) -> None:
        self._update_display()

    def action_clear_log(self) -> None:
        self.query_one("#cmd_log", Log).clear()

    def _set_summary(self) -> None:
        s = get_system_summary(self.power)
        load = (
            f"{s.loadavg[0]:.2f} {s.loadavg[1]:.2f} {s.loadavg[2]:.2f}"
            if s.loadavg
            else "N/A"
        )
        power = f"{s.package_power_w:.1f} W" if s.package_power_w is not None else "N/A"

        summary = (
            f"[b]{s.hostname}[/b]  |  {s.platform}\n"
            f"Uptime: {format_uptime(s.uptime_s)}  |  Load: {load}\n"
            f"CPU: {s.cpu_percent:.1f}%"
            + (f" @ {s.cpu_freq_mhz:.0f}MHz" if s.cpu_freq_mhz else "")
            + f"  |  Package power: {power}\n"
            f"RAM: {format_bytes(s.mem_used)} / {format_bytes(s.mem_total)}  (avail {format_bytes(s.mem_available)})\n"
            f"Swap: {format_bytes(s.swap_used)} / {format_bytes(s.swap_total)}\n"
            f"Disk(/): {format_bytes(s.disk_used)} / {format_bytes(s.disk_total)}  (free {format_bytes(s.disk_free)})\n"
            f"Net: ↑ sent {format_bytes(s.net_sent)}  |  ↓ recv {format_bytes(s.net_recv)}\n"
        )
        self.query_one("#summary", Static).update(summary)

    def _set_procs(self) -> None:
        table = self.query_one("#procs", DataTable)
        rows = get_top_processes(limit=25)
        table.clear()
        for r in rows:
            table.add_row(
                str(r.pid),
                r.name,
                r.user or "",
                f"{r.cpu:.1f}",
                f"{r.mem:.1f}",
                format_bytes(r.read_b or 0) if r.read_b is not None else "",
                format_bytes(r.write_b or 0) if r.write_b is not None else "",
            )

    def _set_services(self) -> None:
        table = self.query_one("#services", DataTable)
        rows = get_running_services(limit=25)
        table.clear()
        if not rows:
            table.add_row("(systemd unavailable)", "", "")
            return
        for r in rows:
            table.add_row(r.name, r.active, r.description)

    def _update_display(self) -> None:
        self._set_summary()
        self._set_diagnostics()
        self._set_procs()
        self._set_services()

    def _set_diagnostics(self) -> None:
        log = self.query_one("#diag_log", Log)
        lines, reset_required = self.diag_feed.poll()

        if reset_required or not self._diag_initialized:
            self._diag_initialized = True
            log.clear()
            snap = lines if reset_required else self.diag_feed.snapshot()
            if not snap:
                log.write("(no recent warnings/errors found, or journal/dmesg unavailable)")
                return
            log.write("\n".join(snap))
            return

        if not lines:
            return

        for ln in lines:
            log.write_line(ln)

    @on(Button.Pressed, "#run_btn")
    async def _run_pressed(self) -> None:
        await self._run_from_input()

    @on(Input.Submitted, "#cmd_input")
    async def _run_submitted(self) -> None:
        await self._run_from_input()

    async def _run_from_input(self) -> None:
        if self._busy:
            return
        cmd_in = self.query_one("#cmd_input", Input)
        cmd = (cmd_in.value or "").strip()
        if not cmd:
            return

        ok = await self.push_screen_wait(ConfirmRun(cmd))
        if not ok:
            return

        self._busy = True
        cmd_in.value = ""
        log = self.query_one("#cmd_log", Log)

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log.write_line(f"[{ts}] $ {cmd}")
        log.write_line("Running...\n")

        try:
            res = await run_shell_command(cmd, timeout_s=120.0)
        except Exception as e:
            log.write_line(f"Executor error: {e}\n")
            self._busy = False
            return

        if res.stdout:
            log.write(res.stdout)
        if res.stderr:
            log.write("\n[stderr]\n")
            log.write(res.stderr)
        log.write_line(f"\nExit code: {res.returncode}\n")

        self._busy = False
