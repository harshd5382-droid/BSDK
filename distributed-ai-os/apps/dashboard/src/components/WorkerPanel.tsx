import { useCallback, useEffect, useState } from "react";
import { motion } from "motion/react";
import {
  getWorkerStatus,
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
          results.push({
            host,
            launcher: status.launcher,
            node_state: status.node_state,
            role: status.role,
            error: null,
            remote_control: status.remote_control,
            api_port: apiPort,
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

  const runAction = async (host: string, action: "stop" | "start" | "update") => {
    if (!clusterToken) {
      setError("Cluster token not configured on this coordinator");
      return;
    }
    setBusy(host);
    setError(null);
    try {
      if (action === "stop") {
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
        await updateWorker(host);
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
      <div className="text-sm text-muted font-light border border-hairline px-4 py-3">
        Set a cluster token on worker PCs to enable remote control from here.
      </div>
    );
  }

  if (workers.length === 0) {
    return (
      <div className="text-sm text-muted font-light border border-hairline px-4 py-3">
        No remote workers discovered yet. Workers appear here when they join the
        cluster via Auto Discovery.
      </div>
    );
  }

  return (
    <div className="bg-surface-soft border border-hairline">
      <div className="h-1 w-full m-stripe" aria-hidden="true" />
      <div className="px-5 py-4">
        <div className="label-caps text-[12px] text-muted mb-3">Remote Workers</div>
        {error && (
          <div className="mb-3 text-sm text-m-red border-l-2 border-m-red pl-3">
            {error}
          </div>
        )}
        <ul className="space-y-3">
          {workers.map((w) => {
            const remoteOk = w.remote_control === "launcher";
            const statusLine = w.error
              ? w.error
              : w.remote_control === "node_only"
                ? `${w.node_state ?? "unknown"} · ${w.role ?? "worker"} · node only (launcher offline)`
                : `${w.node_state ?? "unknown"} · ${w.role ?? "worker"}`;

            return (
              <li
                key={w.host}
                className="flex flex-wrap items-center justify-between gap-3 border border-hairline px-3 py-3"
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
                    disabled={busy === w.host || !remoteOk}
                    title={
                      remoteOk
                        ? "Start worker node"
                        : "Worker launcher offline — start dashboard on worker PC"
                    }
                    onClick={() => runAction(w.host, "start")}
                    className="cursor-pointer label-caps text-[10px] border border-hairline px-2 py-1 min-h-[32px] disabled:opacity-40"
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
                    className="cursor-pointer label-caps text-[10px] border border-hairline px-2 py-1 min-h-[32px] disabled:opacity-40"
                  >
                    Stop
                  </motion.button>
                  <motion.button
                    whileTap={{ scale: 0.97 }}
                    type="button"
                    disabled={busy === w.host || !remoteOk}
                    title={
                      remoteOk
                        ? "Update worker software"
                        : "Worker launcher offline — start dashboard on worker PC"
                    }
                    onClick={() => runAction(w.host, "update")}
                    className="cursor-pointer label-caps text-[10px] border border-hairline px-2 py-1 min-h-[32px] disabled:opacity-40"
                  >
                    Update
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
