import { useCallback, useEffect, useState } from "react";
import { getCluster, getStatus } from "../api/launcher";
import type { ClusterStatus, LauncherStatus } from "../types";

export function useStatus(pollMs = 2000) {
  const [status, setStatus] = useState<LauncherStatus | null>(null);
  const [cluster, setCluster] = useState<ClusterStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    // Fire both requests together. Chaining them made every refresh cost two
    // serial round trips, so the cluster view always lagged the node state by
    // a full request — visible as stale peer counts while workers connect.
    const [statusResult, clusterResult] = await Promise.allSettled([
      getStatus(),
      getCluster(),
    ]);

    if (statusResult.status === "rejected") {
      const e = statusResult.reason;
      setError(e instanceof Error ? e.message : "Failed to fetch status");
      return;
    }

    const s = statusResult.value;
    setStatus(s);
    setError(null);
    setCluster(
      s.node_state !== "stopped" && clusterResult.status === "fulfilled"
        ? clusterResult.value
        : null,
    );
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, pollMs);
    return () => clearInterval(id);
  }, [refresh, pollMs]);

  return { status, cluster, error, refresh };
}
