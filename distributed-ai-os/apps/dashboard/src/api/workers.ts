import type { LauncherStatus, StartRequest } from "../types";

const WORKER_LAUNCHER_PORT = 8090;

function workerBase(host: string): string {
  const normalized = host.split(":")[0];
  return `http://${normalized}:${WORKER_LAUNCHER_PORT}/api/launcher`;
}

async function workerFetch<T>(
  host: string,
  token: string,
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${workerBase(host)}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-DAIOS-Token": token,
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
  token: string,
): Promise<LauncherStatus> {
  return workerFetch(host, token, "/status");
}

export async function stopWorker(host: string, token: string): Promise<unknown> {
  return workerFetch(host, token, "/stop", { method: "POST" });
}

export async function startWorker(
  host: string,
  token: string,
  req: StartRequest,
): Promise<unknown> {
  return workerFetch(host, token, "/start", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function updateWorker(host: string, token: string): Promise<unknown> {
  return workerFetch(host, token, "/update", {
    method: "POST",
    body: JSON.stringify({ reexec: true }),
  });
}

export async function getWorkerVersion(
  host: string,
  token: string,
): Promise<{ commit: string | null; branch: string | null }> {
  return workerFetch(host, token, "/version");
}
