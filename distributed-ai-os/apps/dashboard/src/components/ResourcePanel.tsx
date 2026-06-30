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
    <div className="bg-fabric-900 border border-fabric-700 rounded-lg overflow-hidden">
      <div className="px-4 py-2 border-b border-fabric-700 text-xs uppercase tracking-wider text-fabric-600 font-display flex items-center justify-between">
        <span>Resource Usage — All PCs</span>
        <span className="text-fabric-700 normal-case tracking-normal">
          {nodes.length} {nodes.length === 1 ? "node" : "nodes"}
        </span>
      </div>
      <div className="divide-y divide-fabric-800">
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
        <div className="flex items-center gap-2">
          <span
            className={`inline-block w-2 h-2 rounded-full ${
              node.online ? "bg-accent" : "bg-fabric-700"
            }`}
          />
          <span className="font-display text-sm font-medium truncate">
            {node.label}
          </span>
          <span className="text-xs text-fabric-600 uppercase tracking-wider">
            {node.sub}
          </span>
        </div>
        {r?.cpu_count != null && (
          <span className="text-xs text-fabric-600 font-display">
            {r.cpu_count} cores
          </span>
        )}
      </div>

      {!node.online || !r ? (
        <div className="text-xs text-fabric-700">
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
  const pct = Math.max(0, Math.min(100, usage?.usage_percent ?? 0));
  const active = usage?.status === "active";
  const idle = usage?.status === "idle";
  const detail =
    usage?.detail ??
    (usage?.status === "offline" ? "Offline" : "—");
  const modelHint = usage?.model_name ? ` · ${usage.model_name}` : "";

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-fabric-600 font-display uppercase tracking-wider">
          AI Model
        </span>
        <span
          className={`text-xs font-display ${
            active ? "text-accent" : idle ? "text-white/80" : "text-white/50"
          }`}
        >
          {detail}
          {modelHint}
        </span>
      </div>
      <div className="h-2 bg-fabric-800 rounded overflow-hidden">
        <motion.div
          className={`h-full rounded ${active ? "bg-accent" : idle ? "bg-accent/40" : "bg-fabric-700"}`}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.5, ease: "easeOut" }}
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
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-fabric-600 font-display uppercase tracking-wider">
          {label}
        </span>
        <span className="text-xs text-white/80 font-display">{detail}</span>
      </div>
      <div className="h-2 bg-fabric-800 rounded overflow-hidden">
        <motion.div
          className={`h-full rounded ${hot ? "bg-warm" : "bg-accent"}`}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.5, ease: "easeOut" }}
        />
      </div>
    </div>
  );
}
