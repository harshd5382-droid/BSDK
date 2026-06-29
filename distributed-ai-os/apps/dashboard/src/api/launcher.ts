import type {
  ClusterStatus,
  LauncherStatus,
  StartRequest,
  SystemInfo,
} from "../types";

const BASE = "/api/launcher";

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(
      typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail),
    );
  }
  return res.json() as Promise<T>;
}

export async function getSystem(): Promise<SystemInfo> {
  return fetchJson(`${BASE}/system`);
}

export async function getStatus(): Promise<LauncherStatus> {
  return fetchJson(`${BASE}/status`);
}

export async function getCluster(): Promise<ClusterStatus> {
  return fetchJson(`${BASE}/cluster`);
}

export async function startNode(req: StartRequest): Promise<unknown> {
  return fetchJson(`${BASE}/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export async function stopNode(): Promise<unknown> {
  return fetchJson(`${BASE}/stop`, { method: "POST" });
}

export async function sendChat(
  message: string,
  stream: boolean,
): Promise<Response> {
  return fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, max_tokens: 80, stream }),
  });
}

export function subscribeLogs(onLine: (line: string) => void): () => void {
  const es = new EventSource(`${BASE}/logs`);
  es.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data) as { line: string };
      onLine(data.line);
    } catch {
      /* ignore */
    }
  };
  return () => es.close();
}
