export interface SystemInfo {
  hostname: string;
  lan_ip: string;
  local_ips: string[];
  cpu_count: number;
  ram_total_gb: number;
  ram_available_gb: number;
  models: string[];
}

export interface LauncherStatus {
  launcher: string;
  node_state: "stopped" | "starting" | "running" | "failed";
  role: string | null;
  node_id: string | null;
  api_port: number | null;
  uptime_seconds: number;
  last_error: string | null;
}

export interface PeerStatus {
  id: string;
  host: string;
  rpc_port: number;
  reachable: boolean;
  latency_ms: number | null;
  error: string | null;
}

export interface ClusterStatus {
  coordinator_node_id: string;
  peers: PeerStatus[];
  rpc_endpoints: string[];
  generation: number;
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
}

export type WizardStep = "welcome" | "role" | "connect" | "live";
