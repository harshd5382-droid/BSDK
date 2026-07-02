import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import {
  deleteModel,
  downloadModel,
  getDownloadStatus,
  listModels,
  selectModel,
} from "../api/launcher";
import type { DownloadStatus, ModelInfo } from "../types";

function formatBytes(n: number | null): string {
  if (n == null) return "—";
  const gb = n / 1_000_000_000;
  if (gb >= 1) return `${gb.toFixed(2)} GB`;
  const mb = n / 1_000_000;
  if (mb >= 1) return `${mb.toFixed(1)} MB`;
  return `${(n / 1000).toFixed(0)} KB`;
}

export default function ModelManager() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [url, setUrl] = useState("");
  const [hfRepo, setHfRepo] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [download, setDownload] = useState<DownloadStatus | null>(null);
  const reduced = useReducedMotion();

  const refresh = useCallback(async () => {
    try {
      const data = await listModels();
      setModels(data.models);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load models");
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const status = await getDownloadStatus();
        if (!active) return;
        if (status.status === "downloading") {
          setDownload(status);
        } else if (status.status === "complete") {
          setDownload(null);
          setLoading(false);
          refresh();
        } else if (status.status === "error") {
          setDownload(null);
          setLoading(false);
          setError(status.error);
        }
      } catch {
        /* ignore */
      }
    };
    const id = setInterval(poll, 1500);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [refresh, loading]);

  const handleDownload = async () => {
    setLoading(true);
    setError(null);
    try {
      const directUrl = url.trim();
      const hfInput = hfRepo.trim();
      const looksLikeUrl = /^https?:\/\//i.test(hfInput);

      if (directUrl) {
        await downloadModel({ url: directUrl });
      } else if (looksLikeUrl) {
        await downloadModel({ url: hfInput });
      } else if (hfInput) {
        await downloadModel({ hf_repo: hfInput });
      } else {
        throw new Error("Enter a URL or HuggingFace repo (org/model:file.gguf)");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Download failed");
      setLoading(false);
    }
  };

  const handleSelect = async (name: string) => {
    setError(null);
    try {
      await selectModel(name);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Select failed");
    }
  };

  const handleDelete = async (name: string) => {
    setError(null);
    try {
      await deleteModel(name);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  };

  return (
    <div className="bg-surface-soft border border-hairline rounded-2xl backdrop-blur-xl overflow-hidden">
      <div className="h-1 w-full m-stripe opacity-70" aria-hidden="true" />
      <div className="px-5 py-4">
        <div className="label-caps text-[12px] text-muted mb-3">Model Manager</div>

        <div className="space-y-3 mb-4">
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Direct GGUF URL (https://huggingface.co/.../resolve/main/model.gguf)"
            className="w-full bg-surface-card border border-hairline rounded-xl px-3 py-2 text-sm font-light text-on-dark focus:outline-none focus:border-hairline-strong backdrop-blur-xl transition-colors"
          />
          <input
            type="text"
            value={hfRepo}
            onChange={(e) => setHfRepo(e.target.value)}
            placeholder="HuggingFace: org/model:filename.gguf"
            className="w-full bg-surface-card border border-hairline rounded-xl px-3 py-2 text-sm font-light text-on-dark focus:outline-none focus:border-hairline-strong backdrop-blur-xl transition-colors"
          />
          <motion.button
            whileTap={{ scale: 0.98 }}
            type="button"
            onClick={handleDownload}
            disabled={loading}
            className="btn-m px-4"
          >
            {loading ? "Downloading…" : "Download Model"}
          </motion.button>
          <AnimatePresence>
            {download && (
              <DownloadProgress status={download} reduced={!!reduced} />
            )}
          </AnimatePresence>
        </div>

        {error && (
          <div className="mb-3 text-sm text-m-red border-l-2 border-m-red rounded-lg pl-3 py-1">
            {error}
          </div>
        )}

        <ul className="space-y-2">
          {models.length === 0 && (
            <li className="text-sm text-muted font-light">No models in models/</li>
          )}
          {models.map((m) => (
            <li
              key={m.name}
              className="flex flex-wrap items-center justify-between gap-2 border border-hairline rounded-xl px-3 py-2 bg-surface-card/40"
            >
              <div>
                <span className="font-display text-sm text-on-dark">{m.name}</span>
                <span className="text-xs text-muted ml-2">{m.size_gb} GB</span>
                {m.active && (
                  <span className="ml-2 text-[10px] uppercase tracking-wider text-m-blue-dark">
                    Active
                  </span>
                )}
              </div>
              <div className="flex gap-2">
                {!m.active && (
                  <button
                    type="button"
                    onClick={() => handleSelect(m.name)}
                    className="cursor-pointer label-caps text-[10px] rounded-full border border-hairline px-3 py-1 hover:border-hairline-strong"
                  >
                    Select
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => handleDelete(m.name)}
                  className="cursor-pointer label-caps text-[10px] rounded-full border border-hairline px-3 py-1 text-m-red hover:border-m-red"
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function DownloadProgress({
  status,
  reduced,
}: {
  status: DownloadStatus;
  reduced: boolean;
}) {
  const hasPercent = status.percent !== null && !Number.isNaN(status.percent);
  const percent = hasPercent ? Math.min(100, Math.max(0, status.percent ?? 0)) : 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className="border border-hairline rounded-2xl bg-surface-card backdrop-blur-xl px-3 py-3"
    >
      {/* Header row: status + filename / percentage readout */}
      <div className="flex items-baseline justify-between gap-3 mb-2.5">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <motion.span
              aria-hidden="true"
              className="inline-block h-1.5 w-1.5 rounded-full m-stripe"
              animate={reduced ? undefined : { opacity: [1, 0.25, 1] }}
              transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut" }}
            />
            <span className="label-caps text-[10px] text-muted">Downloading</span>
          </div>
          {status.filename && (
            <div className="mt-1 truncate font-display text-xs text-body-strong">
              {status.filename}
            </div>
          )}
        </div>
        <div className="shrink-0 text-right leading-none">
          <span className="font-display text-2xl font-bold tabular-nums text-on-dark">
            {hasPercent ? percent.toFixed(1) : "—"}
          </span>
          <span className="ml-0.5 font-display text-sm font-bold text-muted">%</span>
        </div>
      </div>

      {/* Track */}
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={hasPercent ? Math.round(percent) : undefined}
        aria-label="Model download progress"
        className="relative h-2.5 w-full rounded-full overflow-hidden border border-hairline bg-canvas"
      >
        {hasPercent ? (
          <motion.div
            className="relative h-full rounded-full m-stripe"
            initial={{ width: 0 }}
            animate={{ width: `${percent}%` }}
            transition={{ duration: 0.5, ease: "easeOut" }}
          >
            {/* Telemetry scan highlight sweeping across the filled track */}
            {!reduced && (
              <motion.div
                aria-hidden="true"
                className="absolute inset-y-0 w-1/3"
                style={{
                  background:
                    "linear-gradient(90deg, transparent, rgba(255,255,255,0.55), transparent)",
                }}
                animate={{ x: ["-120%", "320%"] }}
                transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
              />
            )}
          </motion.div>
        ) : (
          // Indeterminate: no content-length reported, sweep a segment instead.
          <motion.div
            aria-hidden="true"
            className="absolute inset-y-0 w-1/3 rounded-full m-stripe"
            animate={reduced ? { x: "0%" } : { x: ["-40%", "260%"] }}
            transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut" }}
          />
        )}
      </div>

      {/* Byte counts */}
      <div className="mt-2 flex items-center justify-between font-display text-[11px] tabular-nums text-muted">
        <span>{formatBytes(status.bytes_done)}</span>
        <span>{status.bytes_total ? formatBytes(status.bytes_total) : "size unknown"}</span>
      </div>
    </motion.div>
  );
}
