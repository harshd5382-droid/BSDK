import { motion } from "motion/react";
import type { ClusterStatus, LauncherStatus, ModelUsage, ResourceUsage } from "../types";

interface Props {
  status: LauncherStatus;
  cluster: ClusterStatus | null;
}

interface NodeResource {
  label: string;
  sub: string;
  online: boolean;
  resources: ResourceUsage | null;
  modelUsage: ModelUsage | null;
}

export default function ResourcePanel({ status, cluster }: Props) {
  const isWorker = status.role === "worker";
  const nodes: NodeResource[] = [
    {
      label: "This PC",
      sub: isWorker ? "Worker" : "Coordinator",
      online: status.node_state === "running",
      resources: cluster?.local_resources ?? null,
      modelUsage: cluster?.local_model_usage ?? null,
    },
    ...(cluster?.peers ?? []).map((peer) => ({
      label: peer.host,
      sub: isWorker ? "Coordinator" : "Worker",
      online: peer.reachable,
      resources: peer.resources,
      modelUsage: peer.model_usage,
    })),
  ];

  return (
    <div className="bg-surface-soft border border-hairline overflow-hidden">
      <div className="px-4 py-3 border-b border-hairline flex items-center justify-between">
        <span className="label-caps text-[12px] text-on-dark">
          Resource Usage — All PCs
        </span>
        <span className="font-display text-xs font-light text-muted">
          {nodes.length} {nodes.length === 1 ? "node" : "nodes"}
        </span>
      </div>
      <div className="divide-y divide-hairline-strong">
        {nodes.map((node, i) => (
          <NodeResourceRow key={`${node.label}-${i}`} node={node} index={i} />
        ))}
      </div>
    </div>
  );
}

function NodeResourceRow({
  node,
  index,
}: {
  node: NodeResource;
  index: number;
}) {
  const r = node.resources;
  const m = node.modelUsage;
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
      className="p-4"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2.5">
          <span
            className={`inline-block w-2 h-2 ${
              node.online ? "bg-on-dark" : "bg-hairline"
            }`}
            aria-hidden="true"
          />
          <span className="font-display text-sm font-bold text-on-dark truncate">
            {node.label}
          </span>
          <span className="label-caps text-[11px] text-muted">{node.sub}</span>
        </div>
        {r?.cpu_count != null && (
          <span className="text-xs text-muted font-display font-light">
            {r.cpu_count} cores
          </span>
        )}
      </div>

      {!node.online || !r ? (
        <div className="text-xs text-muted font-light">
          {node.online ? "No resource data" : "Offline"}
        </div>
      ) : (
        <div className="space-y-3">
          <UsageBar
            label="CPU"
            percent={r.cpu_percent}
            detail={r.cpu_percent != null ? `${r.cpu_percent.toFixed(0)}%` : "—"}
          />
          <UsageBar
            label="RAM"
            percent={r.ram_percent}
            detail={
              r.ram_used_gb != null && r.ram_total_gb != null
                ? `${r.ram_used_gb.toFixed(1)} / ${r.ram_total_gb.toFixed(1)} GB`
                : "—"
            }
          />
          <ModelUsageBar usage={m} />
        </div>
      )}
    </motion.div>
  );
}

function ModelUsageBar({ usage }: { usage: ModelUsage | null }) {
  const active = usage?.status === "active";
  const idle = usage?.status === "idle";
  const detail =
    usage?.detail ??
    (usage?.status === "offline" ? "Offline" : "—");
  const modelHint = usage?.model_name ? ` · ${usage.model_name}` : "";

  // usage_percent is binary (0 or 100) — animating the width causes a visible
  // back-and-forth wipe on every state change.  Instead we snap the width
  // instantly and animate only the opacity so the state change feels
  // intentional rather than glitchy.
  const fillClass = active ? "m-stripe" : idle ? "bg-body" : "bg-hairline";

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="label-caps text-[11px] text-muted">AI Model</span>
        <motion.span
          key={usage?.status ?? "none"}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.25 }}
          className={`text-xs font-display font-light ${
            active ? "text-on-dark" : idle ? "text-body" : "text-muted"
          }`}
        >
          {detail}
          {modelHint}
        </motion.span>
      </div>
      <div className="h-1.5 bg-surface-elevated overflow-hidden">
        <motion.div
          className={`h-full ${fillClass}`}
          animate={{ opacity: active || idle ? 1 : 0.35 }}
          style={{ width: active ? "100%" : idle ? "30%" : "0%" }}
          transition={{ duration: 0.2 }}
        />
      </div>
    </div>
  );
}

function UsageBar({
  label,
  percent,
  detail,
}: {
  label: string;
  percent: number | null;
  detail: string;
}) {
  const pct = Math.max(0, Math.min(100, percent ?? 0));
  const hot = pct >= 85;
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="label-caps text-[11px] text-muted">{label}</span>
        <span className="text-xs text-body font-display font-light">
          {detail}
        </span>
      </div>
      <div className="h-1.5 bg-surface-elevated overflow-hidden">
        <motion.div
          className={`h-full ${hot ? "bg-warning" : "bg-on-dark"}`}
          animate={{ width: `${pct}%` }}
          transition={{ type: "spring", stiffness: 60, damping: 20, mass: 1 }}
        />
      </div>
    </div>
  );
}
