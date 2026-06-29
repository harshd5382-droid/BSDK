import { useCallback, useEffect, useState } from "react";
import { getCluster, getStatus } from "../api/launcher";
import type { ClusterStatus, LauncherStatus } from "../types";

export function useStatus(pollMs = 2000) {
  const [status, setStatus] = useState<LauncherStatus | null>(null);
  const [cluster, setCluster] = useState<ClusterStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const s = await getStatus();
      setStatus(s);
      setError(null);
      if (s.node_state !== "stopped") {
        try {
          const c = await getCluster();
          setCluster(c);
        } catch {
          setCluster(null);
        }
      } else {
        setCluster(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch status");
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, pollMs);
    return () => clearInterval(id);
  }, [refresh, pollMs]);

  return { status, cluster, error, refresh };
}
