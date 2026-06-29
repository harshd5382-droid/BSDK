import { motion } from "motion/react";
import TopologyGraph from "./TopologyGraph";
import StatusPill from "./StatusPill";
import LogPanel from "./LogPanel";
import ChatTest from "./ChatTest";
import type { ClusterStatus, LauncherStatus } from "../types";

interface Props {
  status: LauncherStatus;
  cluster: ClusterStatus | null;
  logLines: string[];
  logBottomRef: React.RefObject<HTMLDivElement | null>;
  onStop: () => void;
  onRestart: () => void;
  stopping: boolean;
}

export default function LiveStatus({
  status,
  cluster,
  logLines,
  logBottomRef,
  onStop,
  onRestart,
  stopping,
}: Props) {
  const peer = cluster?.peers[0];
  const peerOk = peer?.reachable ?? false;
  const nodeOk = status.node_state === "running";
  const isCoordinator = status.role === "coordinator";

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h2 className="font-display text-2xl font-semibold">Cluster Live</h2>
        <div className="flex gap-2">
          <motion.button
            whileTap={{ scale: 0.95 }}
            onClick={onRestart}
            className="cursor-pointer px-4 py-2 text-sm border border-fabric-700 rounded-lg hover:border-accent/50 transition-colors"
          >
            Restart
          </motion.button>
          <motion.button
            whileTap={{ scale: 0.95 }}
            onClick={onStop}
            disabled={stopping}
            className="cursor-pointer px-4 py-2 text-sm bg-danger/20 border border-danger/30 text-danger rounded-lg hover:bg-danger/30 disabled:opacity-40 transition-colors"
          >
            {stopping ? "Stopping…" : "Stop"}
          </motion.button>
        </div>
      </div>

      <TopologyGraph status={status} cluster={cluster} />

      <div className="flex flex-wrap gap-2 mb-6 justify-center">
        <StatusPill label="Node" ok={nodeOk} detail={status.node_state} />
        <StatusPill
          label="Peer RPC"
          ok={peerOk}
          detail={peer ? peer.host : "none"}
        />
        {isCoordinator && (
          <StatusPill label="OpenAI API" ok={nodeOk} detail=":8000/v1" />
        )}
        <StatusPill
          label="Uptime"
          ok={nodeOk}
          detail={`${Math.floor(status.uptime_seconds)}s`}
        />
      </div>

      {status.last_error && (
        <div className="mb-4 px-4 py-3 bg-danger/10 border border-danger/30 rounded-lg text-danger text-sm">
          {status.last_error}
        </div>
      )}

      <div className="space-y-4">
        <LogPanel lines={logLines} bottomRef={logBottomRef} />
        {isCoordinator && <ChatTest />}
      </div>
    </div>
  );
}
