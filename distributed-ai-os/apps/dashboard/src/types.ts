export interface SystemInfo {
  hostname: string;
  lan_ip: string;
  local_ips: string[];
  cpu_count: number;
  ram_total_gb: number;
  ram_available_gb: number;
  models: string[];
  role?: string;
  cluster_token?: string | null;
  version?: VersionInfo | null;
  autostart_task?: boolean;
}

export interface VersionInfo {
  commit: string | null;
  branch: string | null;
  dirty: boolean;
  error?: string | null;
}

export interface ModelInfo {
  name: string;
  path: string;
  size_gb: number;
  active: boolean;
}

export interface DownloadStatus {
  status: "idle" | "downloading" | "complete" | "error";
  filename: string | null;
  bytes_done: number;
  bytes_total: number | null;
  error: string | null;
  percent: number | null;
}

export interface WorkerRemoteStatus {
  host: string;
  launcher: string | null;
  node_state: string | null;
  role: string | null;
  error: string | null;
}

export interface LauncherStatus {
  launcher: string;
  node_state: "stopped" | "starting" | "running" | "failed";
  role: string | null;
  node_id: string | null;
  api_port: number | null;
  uptime_seconds: number;
  last_error: string | null;
  launcher_role?: string | null;
}

export interface ResourceUsage {
  cpu_percent: number | null;
  cpu_count: number | null;
  ram_used_gb: number | null;
  ram_total_gb: number | null;
  ram_percent: number | null;
}

export interface ModelUsage {
  status: "offline" | "idle" | "active" | string;
  usage_percent: number | null;
  detail: string | null;
  model_name: string | null;
}

export interface PeerStatus {
  id: string;
  host: string;
  rpc_port: number;
  reachable: boolean;
  latency_ms: number | null;
  error: string | null;
  resources: ResourceUsage | null;
  model_usage: ModelUsage | null;
}

export interface ClusterStatus {
  coordinator_node_id: string | null;
  peers: PeerStatus[];
  rpc_endpoints: string[];
  inbound_rpc_clients: number;
  generation: number;
  local_resources: ResourceUsage | null;
  local_model_usage: ModelUsage | null;
  coordinator_ip: string | null;
  membership?: MembershipView | null;
}

export interface MemberInfo {
  node_id: string;
  host: string;
  api_port: number;
  rpc_port: number;
  role: string;
  status: string;
  resources: ResourceUsage | null;
}

export interface CoordinatorLease {
  request_id: string;
  coordinator_node_id: string;
  worker_endpoints: string[];
}

export interface MembershipView {
  local_node_id: string;
  members: MemberInfo[];
  generation: number;
  membership_version: number;
  active_leases: CoordinatorLease[];
  cluster_name: string | null;
}

export type NodeRole = "coordinator" | "worker" | "hybrid";

export interface StartRequest {
  role: NodeRole;
  peer_host?: string;
  peer_rpc_port?: number;
  peer_api_port?: number;
  model_path?: string;
  backend?: string;
  api_port?: number;
  rpc_port?: number;
  discovery_enabled?: boolean;
  cluster_name?: string;
}

export type WizardStep = "welcome" | "role" | "connect" | "live";

export type LiveTab = "cluster" | "chat" | "models";

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}
