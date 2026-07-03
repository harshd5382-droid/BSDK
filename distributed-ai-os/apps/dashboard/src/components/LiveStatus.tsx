import { useCallback, useState } from "react";
import { motion } from "motion/react";
import { updateLauncher } from "../api/launcher";
import TopologyGraph from "./TopologyGraph";
import StatusPill from "./StatusPill";
import ResourcePanel from "./ResourcePanel";
import DistributionPanel from "./DistributionPanel";
import LiveTabBar from "./LiveTabBar";
import ChatBot from "./ChatBot";
import ModelManager from "./ModelManager";
import WorkerPanel from "./WorkerPanel";
import type { ClusterStatus, LauncherStatus, LiveTab, SystemInfo } from "../types";

interface Props {
  status: LauncherStatus;
  cluster: ClusterStatus | null;
  system: SystemInfo;
  onStop: () => void;
  onRestart: () => void;
  stopping: boolean;
  restarting?: boolean;
}

export default function LiveStatus({
  status,
  cluster,
  system,
  onStop,
  onRestart,
  stopping,
  restarting = false,
}: Props) {
  const peers = cluster?.peers ?? [];
  const reachablePeers = peers.filter((p) => p.reachable);
  // Aggregate over every configured peer. Using only peers[0] hid the second
  // worker in a 2-worker cluster and reported a healthy peer as unreachable.
  const anyPeerOk = reachablePeers.length > 0;
  const unreachablePeer = peers.find((p) => !p.reachable);
  const nodeOk = status.node_state === "running";
  const isCoordinator = status.role === "coordinator";
  const isWorker = status.role === "worker";
  const inboundClients = cluster?.inbound_rpc_clients ?? 0;
  const coordinatorIp = cluster?.coordinator_ip ?? null;

  const tabs = isCoordinator
    ? [
        { id: "cluster" as LiveTab, label: "Cluster" },
        { id: "chat" as LiveTab, label: "AI Chat" },
        { id: "models" as LiveTab, label: "Models" },
      ]
    : [{ id: "cluster" as LiveTab, label: "Cluster" }];

  const [activeTab, setActiveTab] = useState<LiveTab>("cluster");
  const [copied, setCopied] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [updateError, setUpdateError] = useState<string | null>(null);

  const versionLabel = system.version?.commit
    ? `${system.version.commit}${system.version.dirty ? " (dirty)" : ""}`
    : null;

  const handleUpdate = useCallback(async () => {
    setUpdating(true);
    setUpdateError(null);
    try {
      await updateLauncher(true);
    } catch (e) {
      setUpdateError(e instanceof Error ? e.message : "Update failed");
      setUpdating(false);
    }
  }, []);

  const apiPort = status.api_port ?? 8000;
  const apiUrl = `http://${system.lan_ip}:${apiPort}/v1`;

  const handleCopyApiUrl = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(apiUrl);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      const el = document.createElement("textarea");
      el.value = apiUrl;
      el.style.position = "fixed";
      el.style.opacity = "0";
      document.body.appendChild(el);
      el.select();
      document.execCommand("copy");
      document.body.removeChild(el);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    }
  }, [apiUrl]);

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex flex-wrap items-end justify-between gap-6 mb-10 pb-8 border-b border-hairline">
        <div>
          <div className="flex items-center gap-3 mb-3">
            <span className="inline-flex h-px w-8 m-stripe" aria-hidden="true" />
            <span className="label-caps text-muted">
              Live / {isCoordinator ? "Coordinator" : "Worker"}
            </span>
          </div>
          <h2 className="display text-4xl md:text-6xl">Cluster online</h2>
        </div>
        <div className="flex gap-3 flex-wrap">
          {versionLabel && (
            <span className="text-xs text-muted self-center font-display">
              {versionLabel}
            </span>
          )}
          <motion.button
            whileTap={{ scale: 0.98 }}
            onClick={handleUpdate}
            disabled={updating || stopping}
            className="btn-m px-5"
          >
            {updating ? "Updating…" : "Update"}
          </motion.button>
          <motion.button
            whileTap={{ scale: 0.98 }}
            onClick={onRestart}
            disabled={stopping || restarting}
            className="btn-m px-5"
          >
            {restarting ? "Restarting…" : "Restart"}
          </motion.button>
          <motion.button
            whileTap={{ scale: 0.98 }}
            onClick={onStop}
            disabled={stopping}
            className="btn-m btn-m-danger px-5"
          >
            {stopping ? "Stopping…" : "Stop"}
          </motion.button>
        </div>
      </div>

      <LiveTabBar tabs={tabs} active={activeTab} onChange={setActiveTab} />

      <div
        role="tabpanel"
        aria-label="Cluster monitoring"
        aria-hidden={activeTab !== "cluster"}
        hidden={activeTab !== "cluster"}
      >
        <TopologyGraph status={status} cluster={cluster} />

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-px my-6 bg-hairline border border-hairline">
          <StatusPill label="Node" ok={nodeOk} detail={status.node_state} />
          {isWorker ? (
            <StatusPill
              label="Coordinator"
              ok={inboundClients > 0}
              detail={
                inboundClients > 0
                  ? coordinatorIp
                    ? coordinatorIp
                    : `${inboundClients} attached`
                  : "listening"
              }
            />
          ) : (
            <StatusPill
              label="Peer RPC"
              ok={anyPeerOk}
              detail={
                peers.length === 0
                  ? "none"
                  : reachablePeers.length === peers.length
                    ? `${reachablePeers.length}/${peers.length} up`
                    : `${reachablePeers.length}/${peers.length} up`
              }
            />
          )}
          {isCoordinator && (
            <StatusPill
              label="OpenAI API"
              ok={nodeOk}
              detail={`:${apiPort}/v1`}
            />
          )}
          <StatusPill
            label="Uptime"
            ok={nodeOk}
            detail={`${Math.floor(status.uptime_seconds)}s`}
          />
        </div>

        {isCoordinator && unreachablePeer && (
        <div className="mb-4 bg-surface-soft border-l-2 border-warning rounded-xl px-4 py-3 text-body text-sm font-light backdrop-blur-xl">
            Worker at{" "}
            <span className="font-display text-on-dark">
              {unreachablePeer.host}:{unreachablePeer.rpc_port}
            </span>{" "}
            is not reachable
            {unreachablePeer.error ? ` (${unreachablePeer.error})` : ""}.
            <ol className="mt-2 list-decimal list-inside space-y-1 marker:text-muted">
              <li>
                On the worker PC: open this dashboard →{" "}
                <span className="text-on-dark">Help another PC</span> →{" "}
                <span className="text-on-dark">Start Worker</span>
              </li>
              <li>
                Confirm it shows address{" "}
                <span className="font-display text-on-dark">
                  {unreachablePeer.host}:50052
                </span>
              </li>
              <li>Then click Restart on this Coordinator PC</li>
            </ol>
          </div>
        )}

        {isWorker && (
        <div className="mb-4 bg-surface-soft border border-hairline rounded-xl px-4 py-3 text-body text-sm font-light backdrop-blur-xl">
            {inboundClients > 0 ? (
              <>
                Coordinator
                {coordinatorIp ? (
                  <>
                    {" "}
                    at{" "}
                    <span className="font-display text-on-dark">
                      {coordinatorIp}
                    </span>
                  </>
                ) : null}{" "}
                is <span className="text-on-dark">connected</span>
                {inboundClients > 1
                  ? ` (${inboundClients} active RPC links)`
                  : ""}
                .
              </>
            ) : (
              <>
                Worker is running and listening. On the{" "}
                <span className="text-on-dark">other PC</span>, choose
                Coordinator and enter this machine's IP as the worker address.
                This panel shows "connected" once the coordinator starts.
              </>
            )}
          </div>
        )}

        {updateError && (
          <div className="mb-4 bg-surface-soft border-l-2 border-m-red rounded-xl px-4 py-3 text-body-strong text-sm font-light backdrop-blur-xl">
            {updateError}
          </div>
        )}

        {status.last_error && (
          <div className="mb-4 bg-surface-soft border-l-2 border-m-red rounded-xl px-4 py-3 text-body-strong text-sm font-light backdrop-blur-xl">
            {status.last_error}
          </div>
        )}

        {isCoordinator && nodeOk && (
          <div className="mb-6 bg-surface-soft border border-hairline rounded-2xl backdrop-blur-xl overflow-hidden">
            <div className="h-1 w-full m-stripe opacity-70" aria-hidden="true" />
            <div className="px-5 py-4">
              <div className="label-caps text-[12px] text-muted mb-2">
                Use in Cursor or VS Code
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <code className="font-display text-sm md:text-base text-on-dark break-all">
                  {apiUrl}
                </code>
                <motion.button
                  whileTap={{ scale: 0.97 }}
                  type="button"
                  onClick={handleCopyApiUrl}
                  className="cursor-pointer shrink-0 px-4 min-h-[40px] label-caps text-[11px] rounded-full border border-hairline text-muted hover:text-on-dark hover:border-hairline-strong transition-colors"
                >
                  {copied ? "Copied" : "Copy URL"}
                </motion.button>
              </div>
              <p className="text-body text-xs font-light mt-3">
                Paste as the OpenAI-compatible base URL. API key can be any
                value — it is not validated locally.
              </p>
            </div>
          </div>
        )}

        <div className="space-y-4">
          {isCoordinator && (
            <WorkerPanel
              cluster={cluster}
              clusterToken={system.cluster_token ?? null}
              localLanIp={system.lan_ip}
            />
          )}
          <ResourcePanel status={status} cluster={cluster} />
          {isCoordinator && cluster?.distribution && (
            <DistributionPanel distribution={cluster.distribution} />
          )}
        </div>
      </div>

      {isCoordinator && (
        <div
          role="tabpanel"
          aria-label="Model manager"
          aria-hidden={activeTab !== "models"}
          hidden={activeTab !== "models"}
        >
          <ModelManager />
        </div>
      )}

      {isCoordinator && (
        <div
          role="tabpanel"
          aria-label="AI chat"
          aria-hidden={activeTab !== "chat"}
          hidden={activeTab !== "chat"}
        >
          <ChatBot />
        </div>
      )}
    </div>
  );
}
