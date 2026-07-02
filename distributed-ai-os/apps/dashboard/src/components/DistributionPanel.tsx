import { motion } from "motion/react";
import type { DeviceAllocation, DistributionDiagnostics } from "../types";

interface Props {
  distribution: DistributionDiagnostics;
}

/** Where model tensors are placed across devices/nodes, and topology health. */
export default function DistributionPanel({ distribution: d }: Props) {
  const policyLabel = d.policy ?? "default (llama.cpp proportional)";
  const included = d.devices.filter((dev) => dev.excluded_reason == null);
  const excluded = d.devices.filter((dev) => dev.excluded_reason != null);
  const excludedEndpoints = Object.entries(d.excluded_endpoints);

  return (
    <div className="bg-surface-soft border border-hairline rounded-2xl backdrop-blur-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-hairline flex items-center justify-between gap-3">
        <span className="label-caps text-[12px] text-body-strong">
          Model Distribution
        </span>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted font-display font-light">
            policy: {policyLabel}
          </span>
          <RestartBadge state={d.restart_state} stale={d.topology_stale} />
        </div>
      </div>

      <div className="p-4 space-y-3">
        {d.topology_stale && (
          <div className="text-xs text-warning font-light">
            Topology changed — model reload pending (waits for active requests).
          </div>
        )}
        {d.restart_error && (
          <div className="text-xs text-warning font-light">
            Last reload failed: {d.restart_error}
          </div>
        )}
        {d.fallback_reason && (
          <div className="text-xs text-muted font-light">{d.fallback_reason}</div>
        )}

        {included.length === 0 && !d.fallback_reason ? (
          <div className="text-xs text-muted font-light">
            No device allocation yet
            {d.rpc_endpoints.length > 0
              ? ` — RPC endpoints: ${d.rpc_endpoints.join(", ")}`
              : ""}
          </div>
        ) : (
          included.map((dev, i) => <DeviceRow key={dev.name} device={dev} index={i} />)
        )}

        {excluded.map((dev) => (
          <div key={dev.name} className="text-xs text-muted font-light">
            <span className="text-body">{dev.name}</span> excluded: {dev.excluded_reason}
          </div>
        ))}
        {excludedEndpoints.map(([ep, reason]) => (
          <div key={ep} className="text-xs text-muted font-light">
            <span className="text-body">{ep}</span> excluded: {reason}
          </div>
        ))}
      </div>
    </div>
  );
}

function DeviceRow({ device, index }: { device: DeviceAllocation; index: number }) {
  const share = device.share_percent ?? 0;
  const memLabel =
    device.memory_type === "vram"
      ? "VRAM"
      : device.memory_type === "ram"
        ? "RAM"
        : "mem";
  const whereLabel =
    device.kind === "rpc"
      ? `worker ${device.endpoint ?? ""}`
      : device.kind === "local_gpu"
        ? "this PC (GPU)"
        : "this PC";
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04 }}
    >
      <div className="flex items-center justify-between mb-1.5 gap-2">
        <span className="label-caps text-[11px] text-muted truncate">
          {device.name} · {whereLabel}
        </span>
        <span className="text-xs text-body font-display font-light whitespace-nowrap">
          {share.toFixed(1)}% · {device.usable_gb.toFixed(1)} GB {memLabel} usable
          <span className="text-muted"> ({device.source === "measured" ? "measured" : "estimated"})</span>
        </span>
      </div>
      <div className="h-1.5 bg-surface-elevated overflow-hidden">
        <motion.div
          className="h-full bg-on-dark"
          animate={{ width: `${Math.max(0, Math.min(100, share))}%` }}
          transition={{ type: "spring", stiffness: 60, damping: 20, mass: 1 }}
        />
      </div>
    </motion.div>
  );
}

function RestartBadge({ state, stale }: { state: string; stale: boolean }) {
  if (state === "idle" && !stale) return null;
  const label =
    state === "running"
      ? "reloading"
      : state === "pending"
        ? "reload pending"
        : state === "failed"
          ? "reload failed"
          : state === "success"
            ? "reloaded"
            : state;
  const cls =
    state === "failed"
      ? "text-warning"
      : state === "running" || state === "pending"
        ? "text-body"
        : "text-muted";
  return (
    <span className={`label-caps text-[11px] ${cls}`}>{label}</span>
  );
}
