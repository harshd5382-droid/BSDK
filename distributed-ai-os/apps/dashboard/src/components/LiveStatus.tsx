import { useState } from "react";
import { motion } from "motion/react";
import TopologyGraph from "./TopologyGraph";
import StatusPill from "./StatusPill";
import ResourcePanel from "./ResourcePanel";
import LiveTabBar from "./LiveTabBar";
import ChatBot from "./ChatBot";
import type { ClusterStatus, LauncherStatus, LiveTab } from "../types";

interface Props {
  status: LauncherStatus;
  cluster: ClusterStatus | null;
  onStop: () => void;
  onRestart: () => void;
  stopping: boolean;
  restarting?: boolean;
}

export default function LiveStatus({
  status,
  cluster,
  onStop,
  onRestart,
  stopping,
  restarting = false,
}: Props) {
  const peer = cluster?.peers[0];
  const peerOk = peer?.reachable ?? false;
  const nodeOk = status.node_state === "running";
  const isCoordinator = status.role === "coordinator";
  const isWorker = status.role === "worker";
  const inboundClients = cluster?.inbound_rpc_clients ?? 0;
  const coordinatorIp = cluster?.coordinator_ip ?? null;

  const tabs = isCoordinator
    ? [
        { id: "cluster" as LiveTab, label: "Cluster" },
        { id: "chat" as LiveTab, label: "AI Chat" },
      ]
    : [{ id: "cluster" as LiveTab, label: "Cluster" }];

  const [activeTab, setActiveTab] = useState<LiveTab>("cluster");

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex flex-wrap items-end justify-between gap-4 mb-8">
        <div>
          <div className="flex items-center gap-3 mb-3">
            <span className="h-4 w-1.5 m-stripe" aria-hidden="true" />
            <span className="label-caps text-muted">
              {isCoordinator ? "Coordinator" : "Worker"}
            </span>
          </div>
          <h2 className="display text-4xl md:text-5xl">Cluster Live</h2>
        </div>
        <div className="flex gap-3">
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

        <div className="flex flex-wrap gap-2 my-6 justify-center">
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
              ok={peerOk}
              detail={peer ? peer.host : "none"}
            />
          )}
          {isCoordinator && (
            <StatusPill label="OpenAI API" ok={nodeOk} detail=":8000/v1" />
          )}
          <StatusPill
            label="Uptime"
            ok={nodeOk}
            detail={`${Math.floor(status.uptime_seconds)}s`}
          />
        </div>

        {peer && !peerOk && isCoordinator && (
          <div className="mb-4 bg-surface-soft border-l-2 border-warning px-4 py-3 text-body text-sm font-light">
            Worker at{" "}
            <span className="font-display text-on-dark">
              {peer.host}:{peer.rpc_port}
            </span>{" "}
            is not reachable
            {peer.error ? ` (${peer.error})` : ""}.
            <ol className="mt-2 list-decimal list-inside space-y-1 marker:text-muted">
              <li>
                On the worker PC: open this dashboard →{" "}
                <span className="text-on-dark">Help another PC</span> →{" "}
                <span className="text-on-dark">Start Worker</span>
              </li>
              <li>
                Confirm it shows address{" "}
                <span className="font-display text-on-dark">
                  {peer.host}:50052
                </span>
              </li>
              <li>Then click Restart on this Coordinator PC</li>
            </ol>
          </div>
        )}

        {isWorker && (
          <div className="mb-4 bg-surface-soft border border-hairline px-4 py-3 text-body text-sm font-light">
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

        {status.last_error && (
          <div className="mb-4 bg-surface-soft border-l-2 border-m-red px-4 py-3 text-body-strong text-sm font-light">
            {status.last_error}
          </div>
        )}

        <div className="space-y-4">
          <ResourcePanel status={status} cluster={cluster} />
        </div>
      </div>

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
