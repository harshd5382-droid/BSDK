import { useCallback, useEffect, useState } from "react";
import { motion } from "motion/react";
import {
  getWorkerExeInfo,
  getWorkerStatus,
  getWorkerVersion,
  pauseWorker,
  resumeWorker,
  startWorker,
  stopWorker,
  updateWorker,
} from "../api/workers";
import type { ClusterStatus, WorkerRemoteStatus } from "../types";

interface Props {
  cluster: ClusterStatus | null;
  clusterToken: string | null;
  localLanIp: string;
}

function resolveApiPort(host: string, cluster: ClusterStatus | null): number {
  for (const member of cluster?.membership?.members ?? []) {
    if (member.host === host) {
      return member.api_port;
    }
  }
  return 8001;
}

export default function WorkerPanel({ cluster, clusterToken, localLanIp }: Props) {
  const [workers, setWorkers] = useState<WorkerRemoteStatus[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [localExeSha, setLocalExeSha] = useState<string | null>(null);

  useEffect(() => {
    getWorkerExeInfo()
      .then((info) => setLocalExeSha(info?.sha256 ?? null))
      .catch(() => setLocalExeSha(null));
  }, []);

  const discoverWorkers = useCallback(async () => {
    if (!clusterToken) return;
    const hosts = new Map<string, number>();

    for (const peer of cluster?.peers ?? []) {
      if (peer.host && peer.host !== localLanIp && peer.host !== "127.0.0.1") {
        hosts.set(peer.host, resolveApiPort(peer.host, cluster));
      }
    }
    for (const member of cluster?.membership?.members ?? []) {
      if (
        member.role === "worker" &&
        member.host &&
        member.host !== localLanIp &&
        member.host !== "127.0.0.1"
      ) {
        hosts.set(member.host, member.api_port);
      }
    }

    const results: WorkerRemoteStatus[] = [];
    await Promise.all(
      [...hosts.entries()].map(async ([host, apiPort]) => {
        try {
          const status = await getWorkerStatus(host, apiPort);
          let exeSha: string | null = null;
          if (status.remote_control === "launcher") {
            exeSha = await getWorkerVersion(host)
              .then((v) => v.exe_sha256 ?? null)
              .catch(() => null);
          }
          results.push({
            host,
            launcher: status.launcher,
            node_state: status.node_state,
            role: status.role,
            error: null,
            remote_control: status.remote_control,
            api_port: apiPort,
            exe_sha256: exeSha,
          });
        } catch (e) {
          results.push({
            host,
            launcher: null,
            node_state: null,
            role: null,
            error: e instanceof Error ? e.message : "Unreachable",
            api_port: apiPort,
          });
        }
      }),
    );
    setWorkers(results);
  }, [cluster, clusterToken, localLanIp]);

  useEffect(() => {
    discoverWorkers();
    const id = setInterval(discoverWorkers, 5000);
    return () => clearInterval(id);
  }, [discoverWorkers]);

  const runAction = async (
    host: string,
    action: "stop" | "start" | "update" | "pause" | "resume",
  ) => {
    if (!clusterToken) {
      setError("Cluster token not configured on this coordinator");
      return;
    }
    setBusy(host);
    setError(null);
    setNotice(null);
    try {
      if (action === "pause") {
        await pauseWorker(host);
        setNotice(
          `${host} disconnected — its resources are no longer pooled. ` +
            "The worker keeps running and can be reconnected anytime.",
        );
      } else if (action === "resume") {
        await resumeWorker(host);
        setNotice(`${host} reconnected — its resources are pooled again.`);
      } else if (action === "stop") {
        await stopWorker(host);
      } else if (action === "start") {
        await startWorker(host, {
          role: "worker",
          backend: "llama.cpp",
          api_port: 8001,
          rpc_port: 50052,
          discovery_enabled: true,
        });
      } else {
        const result = (await updateWorker(host)) as {
          restarting?: boolean;
          up_to_date?: boolean;
        };
        if (result?.up_to_date) {
          setNotice(`${host} is already up to date.`);
        } else if (result?.restarting) {
          setNotice(`${host} is installing the update and restarting — it will reappear shortly.`);
        }
      }
      await discoverWorkers();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(null);
    }
  };

  if (!clusterToken) {
    return (
      <div className="text-sm text-muted font-light border border-hairline rounded-xl px-4 py-3 backdrop-blur-xl bg-surface-soft">
        Set a cluster token on worker PCs to enable remote control from here.
      </div>
    );
  }

  if (workers.length === 0) {
    return (
      <div className="text-sm text-muted font-light border border-hairline rounded-xl px-4 py-3 backdrop-blur-xl bg-surface-soft">
        No remote workers discovered yet. Workers appear here when they join the
        cluster via Auto Discovery.
      </div>
    );
  }

  return (
    <div className="bg-surface-soft border border-hairline rounded-2xl backdrop-blur-xl overflow-hidden">
      <div className="h-1 w-full m-stripe opacity-70" aria-hidden="true" />
      <div className="px-5 py-4">
        <div className="label-caps text-[12px] text-muted mb-3">Remote Workers</div>
        {error && (
          <div className="mb-3 text-sm text-m-red border-l-2 border-m-red pl-3">
            {error}
          </div>
        )}
        {notice && (
          <div className="mb-3 text-sm text-muted border-l-2 border-hairline pl-3">
            {notice}
          </div>
        )}
        <ul className="space-y-3">
          {workers.map((w) => {
            const remoteOk = w.remote_control === "launcher";
            const paused = (cluster?.paused_workers ?? []).includes(w.host.split(":")[0]);
            const updateAvailable = Boolean(
              localExeSha && w.exe_sha256 && localExeSha !== w.exe_sha256,
            );
            const statusLine = w.error
              ? w.error
              : w.remote_control === "node_only"
                ? `${w.node_state ?? "unknown"} · ${w.role ?? "worker"} · node only (launcher offline)`
                : `${w.node_state ?? "unknown"} · ${w.role ?? "worker"}${paused ? " · disconnected (not pooled)" : ""}${updateAvailable ? " · update available" : ""}`;

            return (
              <li
                key={w.host}
                className="flex flex-wrap items-center justify-between gap-3 border border-hairline rounded-xl px-3 py-3 bg-surface-card/40"
              >
                <div>
                  <div className="font-display text-on-dark">{w.host}</div>
                  <div className="text-xs text-muted">{statusLine}</div>
                  {!remoteOk && !w.error && (
                    <div className="text-xs text-muted mt-1 max-w-md">
                      Remote Start/Stop needs the worker dashboard running (
                      <span className="text-on-dark">make dashboard</span> → Help
                      another PC → Start Worker).
                    </div>
                  )}
                </div>
                <div className="flex gap-2">
                  <motion.button
                    whileTap={{ scale: 0.97 }}
                    type="button"
                    disabled={busy === w.host}
                    title={
                      paused
                        ? "Resume pooling this worker's resources (reloads the model)"
                        : "Stop pooling this worker's resources — the worker keeps running"
                    }
                    onClick={() => runAction(w.host, paused ? "resume" : "pause")}
                    className={`cursor-pointer label-caps text-[10px] border px-2 py-1 min-h-[32px] disabled:opacity-40 ${
                      paused ? "border-m-red text-m-red" : "border-hairline"
                    }`}
                  >
                    {paused ? "Reconnect" : "Disconnect"}
                  </motion.button>
                  <motion.button
                    whileTap={{ scale: 0.97 }}
                    type="button"
                    disabled={busy === w.host || !remoteOk}
                    title={
                      remoteOk
                        ? "Start worker node"
                        : "Worker launcher offline — start dashboard on worker PC"
                    }
                    onClick={() => runAction(w.host, "start")}
                    className="cursor-pointer label-caps text-[10px] rounded-full border border-hairline px-3 py-1 min-h-[32px] disabled:opacity-40"
                  >
                    Start
                  </motion.button>
                  <motion.button
                    whileTap={{ scale: 0.97 }}
                    type="button"
                    disabled={busy === w.host || !remoteOk}
                    title={
                      remoteOk
                        ? "Stop worker node"
                        : "Worker launcher offline — start dashboard on worker PC"
                    }
                    onClick={() => runAction(w.host, "stop")}
                    className="cursor-pointer label-caps text-[10px] rounded-full border border-hairline px-3 py-1 min-h-[32px] disabled:opacity-40"
                  >
                    Stop
                  </motion.button>
                  <motion.button
                    whileTap={{ scale: 0.97 }}
                    type="button"
                    disabled={busy === w.host || !remoteOk}
                    title={
                      remoteOk
                        ? updateAvailable
                          ? "New build available — push it to this worker"
                          : "Update worker software"
                        : "Worker launcher offline — start dashboard on worker PC"
                    }
                    onClick={() => runAction(w.host, "update")}
                    className={`cursor-pointer label-caps text-[10px] border px-2 py-1 min-h-[32px] disabled:opacity-40 ${
                      updateAvailable ? "border-m-red text-m-red" : "border-hairline"
                    }`}
                  >
                    {updateAvailable ? "Update ●" : "Update"}
                  </motion.button>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
