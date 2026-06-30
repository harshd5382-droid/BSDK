import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import TopologyGraph from "./TopologyGraph";
import StatusPill from "./StatusPill";
import LogPanel from "./LogPanel";
import ResourcePanel from "./ResourcePanel";
import LiveTabBar from "./LiveTabBar";
import ChatBot from "./ChatBot";
import type { ClusterStatus, LauncherStatus, LiveTab } from "../types";

interface Props {
  status: LauncherStatus;
  cluster: ClusterStatus | null;
  logLines: string[];
  logBottomRef: React.RefObject<HTMLDivElement | null>;
  onStop: () => void;
  onRestart: () => void;
  stopping: boolean;
  restarting?: boolean;
}

const tabVariants = {
  enter: { opacity: 0, y: 12 },
  center: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
};

export default function LiveStatus({
  status,
  cluster,
  logLines,
  logBottomRef,
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
      <div className="flex items-center justify-between mb-6">
        <h2 className="font-display text-2xl font-semibold">Cluster Live</h2>
        <div className="flex gap-2">
          <motion.button
            whileTap={{ scale: 0.95 }}
            onClick={onRestart}
            disabled={stopping || restarting}
            className="cursor-pointer px-4 py-2 text-sm border border-fabric-700 rounded-lg hover:border-accent/50 disabled:opacity-40 transition-colors min-h-[44px]"
          >
            {restarting ? "Restarting…" : "Restart"}
          </motion.button>
          <motion.button
            whileTap={{ scale: 0.95 }}
            onClick={onStop}
            disabled={stopping}
            className="cursor-pointer px-4 py-2 text-sm bg-danger/20 border border-danger/30 text-danger rounded-lg hover:bg-danger/30 disabled:opacity-40 transition-colors min-h-[44px]"
          >
            {stopping ? "Stopping…" : "Stop"}
          </motion.button>
        </div>
      </div>

      <LiveTabBar tabs={tabs} active={activeTab} onChange={setActiveTab} />

      <AnimatePresence mode="wait">
        {activeTab === "cluster" && (
          <motion.div
            key="cluster"
            role="tabpanel"
            aria-label="Cluster monitoring"
            variants={tabVariants}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
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
              <div className="mb-4 px-4 py-3 bg-warm/10 border border-warm/30 rounded-lg text-warm text-sm">
                Worker at{" "}
                <span className="font-display">
                  {peer.host}:{peer.rpc_port}
                </span>{" "}
                is not reachable
                {peer.error ? ` (${peer.error})` : ""}.
                <ol className="mt-2 list-decimal list-inside space-y-1">
                  <li>
                    On the worker PC: open this dashboard →{" "}
                    <strong>Help another PC</strong> → <strong>Start Worker</strong>
                  </li>
                  <li>
                    Confirm it shows address{" "}
                    <span className="font-display">{peer.host}:50052</span>
                  </li>
                  <li>Then click Restart on this Coordinator PC</li>
                </ol>
              </div>
            )}

            {isWorker && (
              <div className="mb-4 px-4 py-3 bg-accent/10 border border-accent/30 rounded-lg text-fabric-600 text-sm">
                {inboundClients > 0 ? (
                  <>
                    Coordinator
                    {coordinatorIp ? (
                      <>
                        {" "}
                        at{" "}
                        <span className="font-display text-white">
                          {coordinatorIp}
                        </span>
                      </>
                    ) : null}{" "}
                    is <strong className="text-white">connected</strong>
                    {inboundClients > 1
                      ? ` (${inboundClients} active RPC links)`
                      : ""}
                    .
                  </>
                ) : (
                  <>
                    Worker is running and listening. On the{" "}
                    <strong className="text-white">other PC</strong>, choose
                    Coordinator and enter this machine's IP as the worker address.
                    This panel shows "connected" once the coordinator starts.
                  </>
                )}
              </div>
            )}

            {status.last_error && (
              <div className="mb-4 px-4 py-3 bg-danger/10 border border-danger/30 rounded-lg text-danger text-sm">
                {status.last_error}
              </div>
            )}

            <div className="space-y-4">
              <ResourcePanel status={status} cluster={cluster} />
              <LogPanel lines={logLines} bottomRef={logBottomRef} />
            </div>
          </motion.div>
        )}

        {activeTab === "chat" && isCoordinator && (
          <motion.div
            key="chat"
            role="tabpanel"
            aria-label="AI chat"
            variants={tabVariants}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
          >
            <ChatBot />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
