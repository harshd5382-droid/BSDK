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
        <div className="label-caps text-[12px] text-muted text-center mb-6">
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
          <div className="text-center mt-6 label-caps text-[11px] text-muted">
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
    <div
      className={`w-36 p-5 border ${
        active
          ? highlight
            ? "border-on-dark bg-surface-card"
            : "border-body bg-surface-card"
          : "border-hairline bg-surface-soft"
      }`}
    >
      <div
        className={`mb-3 h-2.5 w-2.5 ${
          active ? (highlight ? "m-stripe" : "bg-on-dark") : "bg-hairline"
        }`}
        aria-hidden="true"
      />
      <div className="font-display text-sm font-bold text-on-dark truncate">
        {label}
      </div>
      <div className="label-caps text-[11px] text-muted mt-1.5">{sub}</div>
    </div>
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
      <div className="relative w-full h-1 bg-hairline overflow-hidden">
        {connected && (
          <motion.div
            className="absolute inset-y-0 left-0 w-1/3 m-stripe"
            animate={{ x: ["-100%", "400%"] }}
            transition={{ repeat: Infinity, duration: 1.5, ease: "linear" }}
          />
        )}
      </div>
      <span className="label-caps text-[11px] text-muted mt-3">
        {connected
          ? latency != null
            ? `${latency.toFixed(0)} ms`
            : "connected"
          : idleLabel}
      </span>
    </div>
  );
}
