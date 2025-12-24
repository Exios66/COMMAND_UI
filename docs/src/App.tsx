import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  formatBytes,
  formatUptime,
  getBackendUrl,
  setBackendUrl,
  PERMISSION_INFO,
  ProcRow,
  ServiceRow,
  SystemSummary,
  BackendCapabilities,
  PermissionLevel,
  ConnectionState,
} from "./api";

type RunResult = { cmd: string; returncode: number; stdout: string; stderr: string };

// Connection Setup Modal
function ConnectionModal({
  onConnect,
  connectionState,
}: {
  onConnect: (url: string) => void;
  connectionState: ConnectionState;
}) {
  const [url, setUrl] = useState(getBackendUrl());
  const [showInstructions, setShowInstructions] = useState(false);

  return (
    <div className="modal-overlay">
      <div className="modal">
        <div className="modal-header">
          <h2>🔌 Connect to DiagTerm Backend</h2>
        </div>

        <div className="modal-body">
          <p className="modal-description">
            DiagTerm Web needs to connect to a local backend server to monitor your system.
            The backend runs on your machine and provides system information.
          </p>

          <div className="form-group">
            <label htmlFor="backend-url">Backend URL</label>
            <input
              id="backend-url"
              type="text"
              className="input"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="http://127.0.0.1:8765"
            />
            <small className="hint">Default: http://127.0.0.1:8765</small>
          </div>

          {connectionState.status === "error" && (
            <div className="alert">
              <strong>Connection failed:</strong> {connectionState.error}
            </div>
          )}

          <button
            className="btn btn-primary btn-full"
            onClick={() => onConnect(url)}
            disabled={connectionState.status === "connecting"}
          >
            {connectionState.status === "connecting" ? "Connecting..." : "Connect to Backend"}
          </button>

          <div className="divider">
            <span>Need help?</span>
          </div>

          <button
            className="btn btn-secondary btn-full"
            onClick={() => setShowInstructions(!showInstructions)}
          >
            {showInstructions ? "Hide" : "Show"} Setup Instructions
          </button>

          {showInstructions && (
            <div className="instructions">
              <h4>How to start the backend:</h4>
              <ol>
                <li>
                  <strong>Install DiagTerm:</strong>
                  <pre className="code-block">pip install diagterm</pre>
                  <small>Or clone the repo and run: <code>pip install -e .</code></small>
                </li>
                <li>
                  <strong>Start the web server:</strong>
                  <pre className="code-block">diagterm-web</pre>
                  <small>This starts the backend on port 8765</small>
                </li>
                <li>
                  <strong>Optional - Enable command runner:</strong>
                  <pre className="code-block">DIAGTERM_WEB_ENABLE_RUNNER=1 diagterm-web</pre>
                  <small className="warning">⚠️ Only enable if you need to run commands</small>
                </li>
              </ol>

              <h4>Security Notes:</h4>
              <ul>
                <li>The backend only listens on localhost (127.0.0.1)</li>
                <li>No data is sent to external servers</li>
                <li>All processing happens locally on your machine</li>
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Permission Request Modal
function PermissionModal({
  permission,
  onGrant,
  onDeny,
}: {
  permission: PermissionLevel;
  onGrant: () => void;
  onDeny: () => void;
}) {
  const info = PERMISSION_INFO[permission];
  const [understood, setUnderstood] = useState(false);

  return (
    <div className="modal-overlay">
      <div className="modal">
        <div className="modal-header">
          <h2>🔐 Permission Request</h2>
        </div>

        <div className="modal-body">
          <div className={`permission-badge ${info.risk}`}>
            {info.risk === "high" ? "⚠️ High Risk" : "ℹ️ Low Risk"}
          </div>

          <h3>{info.name}</h3>
          <p className="modal-description">{info.description}</p>

          <div className="permission-details">
            <h4>This permission allows:</h4>
            <ul>
              {info.details.map((detail, i) => (
                <li key={i}>{detail}</li>
              ))}
            </ul>
          </div>

          {info.risk === "high" && "warning" in info && (
            <div className="warning-box">
              <strong>⚠️ Warning:</strong> {info.warning}
            </div>
          )}

          {info.risk === "high" && (
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={understood}
                onChange={(e) => setUnderstood(e.target.checked)}
              />
              I understand the risks and want to proceed
            </label>
          )}

          <div className="modal-actions">
            <button className="btn btn-secondary" onClick={onDeny}>
              Deny
            </button>
            <button
              className="btn btn-primary"
              onClick={onGrant}
              disabled={info.risk === "high" && !understood}
            >
              Grant Permission
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Main Dashboard
function Dashboard({
  connectionState,
  onDisconnect,
  onRequestPermission,
}: {
  connectionState: ConnectionState;
  onDisconnect: () => void;
  onRequestPermission: (perm: PermissionLevel) => void;
}) {
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
  const hasReadPermission = connectionState.grantedPermissions.includes("readonly");
  const hasExecutePermission = connectionState.grantedPermissions.includes("execute");

  const refreshOnce = useCallback(async () => {
    if (!hasReadPermission) return;
    
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
  }, [hasReadPermission]);

  useEffect(() => {
    if (!hasReadPermission) return;
    
    refreshOnce();
    const t = window.setInterval(refreshOnce, refreshMs);
    return () => window.clearInterval(t);
  }, [hasReadPermission, refreshOnce]);

  const highPower = useMemo(() => procs.filter((p) => p.cpu >= 25).slice(0, 10), [procs]);

  async function runCommand() {
    if (!hasExecutePermission) {
      onRequestPermission("execute");
      return;
    }

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

  // Show permission request if not granted
  if (!hasReadPermission) {
    return (
      <div className="wrap">
        <header className="header">
          <div>
            <div className="title">DiagTerm Web</div>
            <div className="sub">Connected to {connectionState.backendUrl}</div>
          </div>
          <button className="btn btn-secondary" onClick={onDisconnect}>
            Disconnect
          </button>
        </header>

        <div className="permission-request-card">
          <div className="permission-icon">🔍</div>
          <h2>System Access Required</h2>
          <p>
            To monitor your system, DiagTerm needs permission to read system information.
            This includes CPU, memory, disk, and process data.
          </p>
          <button
            className="btn btn-primary"
            onClick={() => onRequestPermission("readonly")}
          >
            Grant Read Access
          </button>
          <p className="hint">
            All data stays local. Nothing is sent to external servers.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="wrap">
      <header className="header">
        <div>
          <div className="title">DiagTerm Web</div>
          <div className="sub">
            <span className="status-dot connected"></span>
            Connected to {connectionState.backendUrl}
          </div>
        </div>
        <div className="header-actions">
          <button className="btn" onClick={refreshOnce}>
            Refresh
          </button>
          <button className="btn btn-secondary" onClick={onDisconnect}>
            Disconnect
          </button>
        </div>
      </header>

      {/* Permission badges */}
      <div className="permission-badges">
        <span className="badge granted">✓ Read Access</span>
        {hasExecutePermission ? (
          <span className="badge granted">✓ Execute Access</span>
        ) : (
          <span className="badge pending">○ Execute Access (not granted)</span>
        )}
      </div>

      {err && <div className="alert">API error: {err}</div>}

      <section className="card">
        <div className="cardTitle">System</div>
        {!summary ? (
          <div className="muted">Loading…</div>
        ) : (
          <div className="grid">
            <div>
              <b>Host</b>: {summary.hostname}
            </div>
            <div>
              <b>OS</b>: {summary.platform}
            </div>
            <div>
              <b>Uptime</b>: {formatUptime(summary.uptime_s)}
            </div>
            <div>
              <b>Load</b>:{" "}
              {summary.loadavg ? summary.loadavg.map((x) => x.toFixed(2)).join(" ") : "N/A"}
            </div>
            <div>
              <b>CPU</b>: {summary.cpu_percent.toFixed(1)}%
              {summary.cpu_freq_mhz ? ` @ ${summary.cpu_freq_mhz.toFixed(0)}MHz` : ""}
            </div>
            <div>
              <b>Package power</b>:{" "}
              {summary.package_power_w == null ? "N/A" : `${summary.package_power_w.toFixed(1)} W`}
            </div>
            <div>
              <b>RAM</b>: {formatBytes(summary.mem_used)} / {formatBytes(summary.mem_total)} (avail{" "}
              {formatBytes(summary.mem_available)})
            </div>
            <div>
              <b>Swap</b>: {formatBytes(summary.swap_used)} / {formatBytes(summary.swap_total)}
            </div>
            <div>
              <b>Disk(/)</b>: {formatBytes(summary.disk_used)} / {formatBytes(summary.disk_total)}{" "}
              (free {formatBytes(summary.disk_free)})
            </div>
            <div>
              <b>Net</b>: ↑ {formatBytes(summary.net_sent)} | ↓ {formatBytes(summary.net_recv)}
            </div>
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
              <tr>
                <th>PID</th>
                <th>Name</th>
                <th>User</th>
                <th>CPU%</th>
                <th>MEM%</th>
              </tr>
            </thead>
            <tbody>
              {highPower.length ? (
                highPower.map((p) => (
                  <tr key={p.pid}>
                    <td>{p.pid}</td>
                    <td className="mono">{p.name}</td>
                    <td className="mono">{p.user ?? ""}</td>
                    <td>{p.cpu.toFixed(1)}</td>
                    <td>{p.mem.toFixed(1)}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5} className="muted">
                    No high-CPU processes right now.
                  </td>
                </tr>
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
              <tr>
                <th>PID</th>
                <th>Name</th>
                <th>User</th>
                <th>CPU%</th>
                <th>MEM%</th>
                <th>IO R</th>
                <th>IO W</th>
              </tr>
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
              <tr>
                <th>Service</th>
                <th>Active</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              {services.length ? (
                services.map((s) => (
                  <tr key={s.name}>
                    <td className="mono">{s.name}</td>
                    <td>{s.active}</td>
                    <td>{s.description}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={3} className="muted">
                    (systemd unavailable)
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <div className="cardTitle">
          Command runner
          {!hasExecutePermission && (
            <span className="badge-inline warning">Requires permission</span>
          )}
        </div>

        {!hasExecutePermission ? (
          <div className="permission-inline">
            <p>
              Command execution requires additional permission. This allows running shell commands
              on your system.
            </p>
            <button
              className="btn btn-warning"
              onClick={() => onRequestPermission("execute")}
            >
              🔓 Request Execute Permission
            </button>
          </div>
        ) : (
          <>
            <div className="muted">
              ⚠️ Commands run with your user permissions. Be careful what you execute.
            </div>

            <div className="runner">
              <input
                className="input"
                value={cmd}
                onChange={(e) => setCmd(e.target.value)}
                placeholder="Example: df -h && free -h"
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
                <div className="mono">
                  <b>$</b> {runOut.cmd}
                </div>
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
          </>
        )}
      </section>

      <footer className="footer">
        Polling every {Math.round(refreshMs / 100) / 10}s. Backend:{" "}
        <span className="mono">{connectionState.backendUrl}</span>
      </footer>
    </div>
  );
}

// Main App with connection and permission management
export function App() {
  const [connectionState, setConnectionState] = useState<ConnectionState>({
    status: "disconnected",
    backendUrl: getBackendUrl(),
    capabilities: null,
    grantedPermissions: [],
    error: null,
  });

  const [pendingPermission, setPendingPermission] = useState<PermissionLevel | null>(null);

  // Check for saved connection on mount
  useEffect(() => {
    const saved = localStorage.getItem("diagterm_connection");
    if (saved) {
      try {
        const { backendUrl, permissions } = JSON.parse(saved);
        if (backendUrl) {
          setBackendUrl(backendUrl);
          // Auto-reconnect with saved permissions
          handleConnect(backendUrl, permissions || []);
        }
      } catch {
        // Invalid saved data, ignore
      }
    }
  }, []);

  async function handleConnect(url: string, savedPermissions: PermissionLevel[] = []) {
    setBackendUrl(url);
    setConnectionState((s) => ({
      ...s,
      status: "connecting",
      backendUrl: url,
      error: null,
    }));

    try {
      const capabilities = await api.testConnection();
      setConnectionState((s) => ({
        ...s,
        status: "connected",
        capabilities,
        grantedPermissions: savedPermissions,
      }));

      // Save connection info
      localStorage.setItem(
        "diagterm_connection",
        JSON.stringify({ backendUrl: url, permissions: savedPermissions })
      );
    } catch (e) {
      setConnectionState((s) => ({
        ...s,
        status: "error",
        error: (e as Error).message,
      }));
    }
  }

  function handleDisconnect() {
    localStorage.removeItem("diagterm_connection");
    setConnectionState({
      status: "disconnected",
      backendUrl: getBackendUrl(),
      capabilities: null,
      grantedPermissions: [],
      error: null,
    });
  }

  function handleRequestPermission(perm: PermissionLevel) {
    setPendingPermission(perm);
  }

  function handleGrantPermission() {
    if (!pendingPermission) return;

    const newPermissions = [...connectionState.grantedPermissions, pendingPermission];
    setConnectionState((s) => ({
      ...s,
      grantedPermissions: newPermissions,
    }));

    // Update saved permissions
    localStorage.setItem(
      "diagterm_connection",
      JSON.stringify({
        backendUrl: connectionState.backendUrl,
        permissions: newPermissions,
      })
    );

    setPendingPermission(null);
  }

  function handleDenyPermission() {
    setPendingPermission(null);
  }

  // Show connection modal if not connected
  if (connectionState.status !== "connected") {
    return (
      <ConnectionModal
        onConnect={(url) => handleConnect(url)}
        connectionState={connectionState}
      />
    );
  }

  // Show permission modal if pending
  if (pendingPermission) {
    return (
      <>
        <Dashboard
          connectionState={connectionState}
          onDisconnect={handleDisconnect}
          onRequestPermission={handleRequestPermission}
        />
        <PermissionModal
          permission={pendingPermission}
          onGrant={handleGrantPermission}
          onDeny={handleDenyPermission}
        />
      </>
    );
  }

  return (
    <Dashboard
      connectionState={connectionState}
      onDisconnect={handleDisconnect}
      onRequestPermission={handleRequestPermission}
    />
  );
}
