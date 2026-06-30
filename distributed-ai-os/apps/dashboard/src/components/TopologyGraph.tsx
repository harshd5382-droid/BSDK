import { motion } from "motion/react";
import type { ClusterStatus, LauncherStatus } from "../types";

interface Props {
  status: LauncherStatus;
  cluster: ClusterStatus | null;
}

export default function TopologyGraph({ status, cluster }: Props) {
  const isWorker = status.role === "worker";
  const inbound = cluster?.inbound_rpc_clients ?? 0;
  const gen2 = (cluster?.generation ?? 1) >= 2;
  const members = cluster?.membership?.members ?? [];
  const remoteMembers = members.filter(
    (m) => m.node_id !== cluster?.membership?.local_node_id,
  );
  const activeLeases = cluster?.membership?.active_leases ?? [];

  if (gen2 && remoteMembers.length > 0) {
    return (
      <div className="py-6">
        <div className="text-xs uppercase tracking-wider text-fabric-600 text-center mb-4">
          Cluster members ({remoteMembers.length + 1} nodes)
        </div>
        <div className="flex flex-wrap items-center justify-center gap-3">
          <NodeBox
            label="This PC"
            sub={status.role ?? "node"}
            active={status.node_state === "running"}
            highlight
          />
          {remoteMembers.map((m) => (
            <div key={m.node_id} className="flex items-center gap-2">
              <ConnectionLine
                connected={m.status === "alive" || m.status === "suspect"}
                latency={null}
              />
              <NodeBox
                label={m.host}
                sub={m.role}
                active={m.status === "alive"}
              />
            </div>
          ))}
        </div>
        {activeLeases.length > 0 && (
          <div className="text-center mt-4 text-xs text-fabric-600">
            {activeLeases.length} active coordinator lease
            {activeLeases.length > 1 ? "s" : ""}
          </div>
        )}
      </div>
    );
  }

  const peer = cluster?.peers[0];
  const connected = isWorker ? inbound > 0 : (peer?.reachable ?? false);

  return (
    <div className="flex items-center justify-center gap-0 py-8">
      <NodeBox
        label="This PC"
        sub={isWorker ? "Worker" : "Coordinator"}
        active={status.node_state === "running"}
        highlight
      />

      <ConnectionLine
        connected={connected}
        latency={isWorker ? null : peer?.latency_ms}
        idleLabel={isWorker ? "listening…" : "waiting…"}
      />

      <NodeBox
        label={
          isWorker
            ? (cluster?.coordinator_ip ?? "Remote PC")
            : (peer?.host ?? "Other PC")
        }
        sub={isWorker ? "Coordinator" : "Worker"}
        active={connected}
      />
    </div>
  );
}

function NodeBox({
  label,
  sub,
  active,
  highlight = false,
}: {
  label: string;
  sub: string;
  active: boolean;
  highlight?: boolean;
}) {
  return (
    <motion.div
      animate={active ? { boxShadow: "0 0 20px rgba(61,214,195,0.15)" } : {}}
      className={`w-36 text-center p-4 rounded-xl border ${
        active
          ? highlight
            ? "border-accent/50 bg-fabric-800"
            : "border-accent/30 bg-fabric-800"
          : "border-fabric-700 bg-fabric-800/50"
      }`}
    >
      <div className="font-display text-2xl text-accent mb-2">
        {active ? "●" : "○"}
      </div>
      <div className="font-display text-sm font-medium truncate">{label}</div>
      <div className="text-xs text-fabric-600 uppercase tracking-wider mt-1">
        {sub}
      </div>
    </motion.div>
  );
}

function ConnectionLine({
  connected,
  latency,
  idleLabel = "waiting…",
}: {
  connected: boolean;
  latency?: number | null;
  idleLabel?: string;
}) {
  return (
    <div className="flex flex-col items-center w-24 mx-2">
      <div className="relative w-full h-0.5 bg-fabric-700 overflow-hidden rounded">
        {connected && (
          <motion.div
            className="absolute inset-y-0 left-0 w-1/3 bg-accent rounded"
            animate={{ x: ["-100%", "400%"] }}
            transition={{ repeat: Infinity, duration: 1.5, ease: "linear" }}
          />
        )}
      </div>
      <span className="text-xs text-fabric-600 mt-2 font-display">
        {connected
          ? latency != null
            ? `${latency.toFixed(0)} ms`
            : "connected"
          : idleLabel}
      </span>
    </div>
  );
}
