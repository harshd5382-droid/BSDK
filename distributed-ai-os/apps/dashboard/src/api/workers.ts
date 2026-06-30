import type { LauncherStatus, StartRequest } from "../types";

function workerHostPath(host: string): string {
  return encodeURIComponent(host.split(":")[0]);
}

async function workerFetch<T>(
  host: string,
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`/api/launcher/workers/${workerHostPath(host)}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(
      typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail),
    );
  }
  return res.json() as Promise<T>;
}

export async function getWorkerStatus(
  host: string,
  apiPort = 8001,
): Promise<LauncherStatus> {
  return workerFetch(host, `/status?api_port=${apiPort}`);
}

export async function stopWorker(host: string): Promise<unknown> {
  return workerFetch(host, "/stop", { method: "POST" });
}

export async function startWorker(
  host: string,
  req: StartRequest,
): Promise<unknown> {
  return workerFetch(host, "/start", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function updateWorker(host: string): Promise<unknown> {
  return workerFetch(host, "/update", { method: "POST" });
}

export async function getWorkerVersion(
  host: string,
): Promise<{ commit: string | null; branch: string | null }> {
  return workerFetch(host, "/version");
}
