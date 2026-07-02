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
      <div className="relative py-8 rounded-2xl border border-hairline bg-surface-soft backdrop-blur-xl overflow-hidden">
        <MeshBackdrop />
        <div className="relative label-caps text-[12px] text-muted text-center mb-6">
          Cluster members ({remoteMembers.length + 1} nodes)
        </div>
        <div className="relative flex flex-wrap items-center justify-center gap-3">
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
          <div className="relative text-center mt-6 label-caps text-[11px] text-muted">
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
    <div className="relative flex items-center justify-center gap-0 py-10 rounded-2xl border border-hairline bg-surface-soft backdrop-blur-xl overflow-hidden">
      <MeshBackdrop />
      <div className="relative flex items-center">
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
    </div>
  );
}

/* Faint ambient dot-field behind the node graph — reinforces "live mesh"
   without competing with the node/link foreground. */
function MeshBackdrop() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 opacity-40"
      style={{
        backgroundImage: "radial-gradient(rgba(255,255,255,0.14) 1px, transparent 1.4px)",
        backgroundSize: "22px 22px",
        maskImage: "radial-gradient(ellipse 70% 80% at 50% 50%, #000 0%, transparent 100%)",
        WebkitMaskImage:
          "radial-gradient(ellipse 70% 80% at 50% 50%, #000 0%, transparent 100%)",
      }}
    />
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
      initial={{ opacity: 0, scale: 0.94 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className={`relative w-36 p-5 rounded-2xl border backdrop-blur-xl transition-colors duration-300 ${
        active
          ? highlight
            ? "border-hairline-strong bg-surface-card shadow-[0_0_0_1px_rgba(109,94,240,0.2),0_0_28px_-8px_rgba(109,94,240,0.45)]"
            : "border-hairline-strong bg-surface-card"
          : "border-hairline bg-surface-soft"
      }`}
    >
      <span className="relative mb-3 flex h-2.5 w-2.5" aria-hidden="true">
        {active && highlight && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full m-stripe opacity-60" />
        )}
        <span
          className={`relative inline-flex h-2.5 w-2.5 rounded-full ${
            active ? (highlight ? "m-stripe" : "bg-body-strong") : "bg-hairline-strong"
          }`}
        />
      </span>
      <div className="font-display text-sm font-semibold text-on-dark truncate">
        {label}
      </div>
      <div className="label-caps text-[11px] text-muted mt-1.5 text-center">{sub}</div>
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
    <div className="flex flex-col items-center w-28 mx-2">
      <div className="relative w-full h-[3px] rounded-full bg-hairline overflow-hidden">
        {connected ? (
          <>
            <div className="absolute inset-0 rounded-full m-stripe opacity-30" />
            <motion.div
              className="absolute inset-y-0 left-0 w-1/3 rounded-full m-stripe"
              animate={{ x: ["-100%", "400%"] }}
              transition={{ repeat: Infinity, duration: 1.6, ease: "linear" }}
            />
          </>
        ) : (
          <motion.div
            className="absolute inset-y-0 left-0 w-1/4 rounded-full bg-hairline-strong"
            animate={{ x: ["-100%", "500%"] }}
            transition={{ repeat: Infinity, duration: 2.2, ease: "easeInOut" }}
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
