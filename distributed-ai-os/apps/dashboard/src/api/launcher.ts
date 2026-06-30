import type {
  ClusterStatus,
  ChatMessage,
  DownloadStatus,
  LauncherStatus,
  ModelInfo,
  StartRequest,
  SystemInfo,
  VersionInfo,
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
  messages: ChatMessage[],
  stream: boolean,
): Promise<Response> {
  return fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, stream }),
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

export async function getVersion(): Promise<VersionInfo> {
  return fetchJson(`${BASE}/version`);
}

export async function updateLauncher(reexec = true): Promise<unknown> {
  return fetchJson(`${BASE}/update`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reexec }),
  });
}

export async function listModels(): Promise<{ models: ModelInfo[] }> {
  return fetchJson(`${BASE}/models`);
}

export async function getDownloadStatus(): Promise<DownloadStatus> {
  return fetchJson(`${BASE}/models/download/status`);
}

export async function downloadModel(body: {
  url?: string;
  hf_repo?: string;
  filename?: string;
}): Promise<unknown> {
  return fetchJson(`${BASE}/models/download`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function selectModel(name: string): Promise<unknown> {
  return fetchJson(`${BASE}/models/select`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export async function deleteModel(name: string): Promise<unknown> {
  return fetchJson(`${BASE}/models/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
}
