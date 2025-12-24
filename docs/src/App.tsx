import React, { useEffect, useMemo, useState } from "react";
import { api, formatBytes, formatUptime, ProcRow, ServiceRow, SystemSummary } from "./api";

type RunResult = { cmd: string; returncode: number; stdout: string; stderr: string };

export function App() {
  const [summary, setSummary] = useState<SystemSummary | null>(null);
  const [procs, setProcs] = useState<ProcRow[]>([]);
  const [services, setServices] = useState<ServiceRow[]>([]);
  const [diag, setDiag] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const [cmd, setCmd] = useState<string>("");
  const [runOut, setRunOut] = useState<RunResult | null>(null);
  const [runErr, setRunErr] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const refreshMs = 1000;

  async function refreshOnce() {
    try {
      setErr(null);
      const [s, p, sv, d] = await Promise.all([
        api.summary(),
        api.processes(25),
        api.services(25),
        api.diagnostics(160),
      ]);
      setSummary(s);
      setProcs(p.processes);
      setServices(sv.services);
      setDiag(d.lines);
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  useEffect(() => {
    refreshOnce();
    const t = window.setInterval(refreshOnce, refreshMs);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const highPower = useMemo(() => procs.filter((p) => p.cpu >= 25).slice(0, 10), [procs]);

  async function runCommand() {
    const c = cmd.trim();
    if (!c) return;
    if (!window.confirm(`Run this command?\n\n${c}`)) return;

    setRunning(true);
    setRunErr(null);
    setRunOut(null);
    try {
      const res = await api.run(c);
      setRunOut(res);
      setCmd("");
    } catch (e) {
      setRunErr((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="wrap">
      <header className="header">
        <div>
          <div className="title">DiagTerm Web</div>
          <div className="sub">Live diagnostics + processes + services + command runner (localhost)</div>
        </div>
        <button className="btn" onClick={refreshOnce}>Refresh</button>
      </header>

      {err && <div className="alert">API error: {err}</div>}

      <section className="card">
        <div className="cardTitle">System</div>
        {!summary ? (
          <div className="muted">Loading…</div>
        ) : (
          <div className="grid">
            <div><b>Host</b>: {summary.hostname}</div>
            <div><b>OS</b>: {summary.platform}</div>
            <div><b>Uptime</b>: {formatUptime(summary.uptime_s)}</div>
            <div><b>Load</b>: {summary.loadavg ? summary.loadavg.map((x) => x.toFixed(2)).join(" ") : "N/A"}</div>
            <div><b>CPU</b>: {summary.cpu_percent.toFixed(1)}%{summary.cpu_freq_mhz ? ` @ ${summary.cpu_freq_mhz.toFixed(0)}MHz` : ""}</div>
            <div><b>Package power</b>: {summary.package_power_w == null ? "N/A" : `${summary.package_power_w.toFixed(1)} W`}</div>
            <div><b>RAM</b>: {formatBytes(summary.mem_used)} / {formatBytes(summary.mem_total)} (avail {formatBytes(summary.mem_available)})</div>
            <div><b>Swap</b>: {formatBytes(summary.swap_used)} / {formatBytes(summary.swap_total)}</div>
            <div><b>Disk(/)</b>: {formatBytes(summary.disk_used)} / {formatBytes(summary.disk_total)} (free {formatBytes(summary.disk_free)})</div>
            <div><b>Net</b>: ↑ {formatBytes(summary.net_sent)} | ↓ {formatBytes(summary.net_recv)}</div>
          </div>
        )}
      </section>

      <section className="cols">
        <div className="card">
          <div className="cardTitle">Diagnostics feed (warnings/errors)</div>
          <pre className="log">{diag.length ? diag.join("\n") : "(none / unavailable)"}</pre>
        </div>

        <div className="card">
          <div className="cardTitle">High CPU ("power")</div>
          <table className="table">
            <thead>
              <tr><th>PID</th><th>Name</th><th>User</th><th>CPU%</th><th>MEM%</th></tr>
            </thead>
            <tbody>
              {highPower.length ? highPower.map((p) => (
                <tr key={p.pid}>
                  <td>{p.pid}</td>
                  <td className="mono">{p.name}</td>
                  <td className="mono">{p.user ?? ""}</td>
                  <td>{p.cpu.toFixed(1)}</td>
                  <td>{p.mem.toFixed(1)}</td>
                </tr>
              )) : (
                <tr><td colSpan={5} className="muted">No high-CPU processes right now.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="cols">
        <div className="card">
          <div className="cardTitle">Top processes</div>
          <table className="table">
            <thead>
              <tr><th>PID</th><th>Name</th><th>User</th><th>CPU%</th><th>MEM%</th><th>IO R</th><th>IO W</th></tr>
            </thead>
            <tbody>
              {procs.map((p) => (
                <tr key={p.pid}>
                  <td>{p.pid}</td>
                  <td className="mono">{p.name}</td>
                  <td className="mono">{p.user ?? ""}</td>
                  <td>{p.cpu.toFixed(1)}</td>
                  <td>{p.mem.toFixed(1)}</td>
                  <td className="mono">{p.read_b == null ? "" : formatBytes(p.read_b)}</td>
                  <td className="mono">{p.write_b == null ? "" : formatBytes(p.write_b)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card">
          <div className="cardTitle">Running services (background operations)</div>
          <table className="table">
            <thead>
              <tr><th>Service</th><th>Active</th><th>Description</th></tr>
            </thead>
            <tbody>
              {services.length ? services.map((s) => (
                <tr key={s.name}>
                  <td className="mono">{s.name}</td>
                  <td>{s.active}</td>
                  <td>{s.description}</td>
                </tr>
              )) : (
                <tr><td colSpan={3} className="muted">(systemd unavailable)</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <div className="cardTitle">Command runner</div>
        <div className="muted">
          Disabled by default on the backend. Enable with <span className="mono">DIAGTERM_WEB_ENABLE_RUNNER=1</span>.
        </div>

        <div className="runner">
          <input
            className="input"
            value={cmd}
            onChange={(e) => setCmd(e.target.value)}
            placeholder='Example: df -h && free -h'
            onKeyDown={(e) => {
              if (e.key === "Enter") runCommand();
            }}
          />
          <button className="btn" disabled={running} onClick={runCommand}>
            {running ? "Running…" : "Run"}
          </button>
        </div>

        {runErr && <div className="alert">Run error: {runErr}</div>}
        {runOut && (
          <div className="runOut">
            <div className="mono"><b>$</b> {runOut.cmd}</div>
            <div className="muted">Exit code: {runOut.returncode}</div>
            {runOut.stdout && (
              <>
                <div className="muted">stdout</div>
                <pre className="log">{runOut.stdout}</pre>
              </>
            )}
            {runOut.stderr && (
              <>
                <div className="muted">stderr</div>
                <pre className="log">{runOut.stderr}</pre>
              </>
            )}
          </div>
        )}
      </section>

      <footer className="footer">
        Polling every {Math.round(refreshMs / 100) / 10}s. Backend: <span className="mono">127.0.0.1:8765</span>
      </footer>
    </div>
  );
}
