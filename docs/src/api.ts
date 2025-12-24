export type SystemSummary = {
  hostname: string;
  platform: string;
  kernel: string;
  uptime_s: number;
  loadavg: [number, number, number] | null;
  cpu_percent: number;
  cpu_freq_mhz: number | null;
  mem_total: number;
  mem_used: number;
  mem_available: number;
  swap_total: number;
  swap_used: number;
  disk_total: number;
  disk_used: number;
  disk_free: number;
  net_sent: number;
  net_recv: number;
  package_power_w: number | null;
};

export type ProcRow = {
  pid: number;
  name: string;
  user: string | null;
  cpu: number;
  mem: number;
  read_b: number | null;
  write_b: number | null;
};

export type ServiceRow = {
  name: string;
  description: string;
  active: string;
};

export type BackendCapabilities = {
  version: string;
  runner_enabled: boolean;
  diagnostics_enabled: boolean;
  services_enabled: boolean;
};

export type PermissionLevel = "readonly" | "execute";

export type ConnectionState = {
  status: "disconnected" | "connecting" | "connected" | "error";
  backendUrl: string;
  capabilities: BackendCapabilities | null;
  grantedPermissions: PermissionLevel[];
  error: string | null;
};

// Default backend URL (localhost)
const DEFAULT_BACKEND = "http://127.0.0.1:8765";

// Connection state management
let currentBackendUrl = DEFAULT_BACKEND;

export function setBackendUrl(url: string) {
  currentBackendUrl = url.replace(/\/$/, ""); // Remove trailing slash
}

export function getBackendUrl(): string {
  return currentBackendUrl;
}

export function formatBytes(n: number): string {
  const units = ["B", "KB", "MB", "GB", "TB", "PB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  if (i === 0) return `${Math.floor(v)}${units[i]}`;
  return `${v.toFixed(1)}${units[i]}`;
}

export function formatUptime(seconds: number): string {
  seconds = Math.max(0, Math.floor(seconds));
  const s = seconds % 60;
  const m0 = Math.floor(seconds / 60);
  const m = m0 % 60;
  const h0 = Math.floor(m0 / 60);
  const h = h0 % 24;
  const d = Math.floor(h0 / 24);
  const pad = (x: number) => x.toString().padStart(2, "0");
  if (d > 0) return `${d}d ${pad(h)}:${pad(m)}:${pad(s)}`;
  return `${pad(h)}:${pad(m)}:${pad(s)}`;
}

async function getJson<T>(path: string): Promise<T> {
  const url = path.startsWith("http") ? path : `${currentBackendUrl}${path}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

export const api = {
  // Test connection to backend
  testConnection: async (): Promise<BackendCapabilities> => {
    try {
      // Try to get capabilities from the backend
      const res = await fetch(`${currentBackendUrl}/api/capabilities`, {
        method: "GET",
        signal: AbortSignal.timeout(5000),
      });
      if (res.ok) {
        return await res.json();
      }
      // Fallback: try summary endpoint to check if backend is alive
      const summaryRes = await fetch(`${currentBackendUrl}/api/summary`, {
        method: "GET",
        signal: AbortSignal.timeout(5000),
      });
      if (summaryRes.ok) {
        return {
          version: "unknown",
          runner_enabled: false,
          diagnostics_enabled: true,
          services_enabled: true,
        };
      }
      throw new Error("Backend not responding");
    } catch (e) {
      if (e instanceof Error && e.name === "TimeoutError") {
        throw new Error("Connection timeout - is the backend running?");
      }
      throw e;
    }
  },

  summary: () => getJson<SystemSummary>("/api/summary"),
  processes: (limit = 25) => getJson<{ processes: ProcRow[] }>(`/api/processes?limit=${limit}`),
  services: (limit = 25) => getJson<{ services: ServiceRow[] }>(`/api/services?limit=${limit}`),
  diagnostics: (limit = 120) => getJson<{ lines: string[] }>(`/api/diagnostics?limit=${limit}`),
  
  run: async (cmd: string) => {
    const res = await fetch(`${currentBackendUrl}/api/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cmd, timeout_s: 120 }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = (body && (body.detail as string)) || `${res.status} ${res.statusText}`;
      throw new Error(msg);
    }
    return body as { cmd: string; returncode: number; stdout: string; stderr: string };
  },
};

// Permission descriptions for user consent
export const PERMISSION_INFO = {
  readonly: {
    name: "Read System Information",
    description: "View CPU, memory, disk, and network statistics",
    details: [
      "Read CPU usage and frequency",
      "Read memory and swap usage",
      "Read disk space information",
      "Read network transfer statistics",
      "View running processes (name, CPU%, memory%)",
      "View system services status",
    ],
    risk: "low",
  },
  execute: {
    name: "Execute Commands",
    description: "Run shell commands on your system",
    details: [
      "Execute arbitrary shell commands",
      "Read command output (stdout/stderr)",
      "Commands run with your user permissions",
    ],
    risk: "high",
    warning: "Only grant this permission if you trust the commands you will run. Commands execute with your user's full permissions.",
  },
} as const;
