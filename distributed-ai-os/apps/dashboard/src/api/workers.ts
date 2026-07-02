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
): Promise<{ commit: string | null; branch: string | null; exe_sha256?: string | null }> {
  return workerFetch(host, "/version");
}

async function clusterPauseFetch(action: "pause" | "resume", host: string): Promise<string[]> {
  const res = await fetch(`/api/launcher/cluster/workers/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ host }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(
      typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail),
    );
  }
  const data = (await res.json()) as { paused: string[] };
  return data.paused;
}

/** Temporarily stop pooling this worker's resources (the worker keeps running). */
export async function pauseWorker(host: string): Promise<string[]> {
  return clusterPauseFetch("pause", host.split(":")[0]);
}

/** Resume pooling a previously paused worker's resources. */
export async function resumeWorker(host: string): Promise<string[]> {
  return clusterPauseFetch("resume", host.split(":")[0]);
}

export interface WorkerExeInfo {
  sha256: string;
  size_bytes: number;
  modified: string;
  path: string;
}

/** Info about the worker exe build this coordinator can push to worker PCs. */
export async function getWorkerExeInfo(): Promise<WorkerExeInfo | null> {
  const res = await fetch("/api/launcher/worker-exe/info");
  if (res.status === 404) return null;
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(
      typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail),
    );
  }
  return res.json() as Promise<WorkerExeInfo>;
}
