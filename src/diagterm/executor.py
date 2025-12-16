from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass(frozen=True)
class ExecResult:
    cmd: str
    returncode: int
    stdout: str
    stderr: str


async def run_shell_command(cmd: str, timeout_s: float = 60.0) -> ExecResult:
    """Run a shell command and capture stdout/stderr.

    Note: This intentionally uses the user's shell for flexibility.
    """
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return ExecResult(cmd=cmd, returncode=124, stdout="", stderr=f"Timed out after {timeout_s}s")

    stdout = (stdout_b or b"").decode(errors="replace")
    stderr = (stderr_b or b"").decode(errors="replace")
    return ExecResult(cmd=cmd, returncode=int(proc.returncode or 0), stdout=stdout, stderr=stderr)
