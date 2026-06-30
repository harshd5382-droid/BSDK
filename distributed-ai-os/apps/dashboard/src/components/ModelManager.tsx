import { useCallback, useEffect, useState } from "react";
import { motion } from "motion/react";
import {
  deleteModel,
  downloadModel,
  getDownloadStatus,
  listModels,
  selectModel,
} from "../api/launcher";
import type { ModelInfo } from "../types";

export default function ModelManager() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [url, setUrl] = useState("");
  const [hfRepo, setHfRepo] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [downloadPercent, setDownloadPercent] = useState<number | null>(null);

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
          setDownloadPercent(status.percent);
        } else if (status.status === "complete") {
          setDownloadPercent(null);
          setLoading(false);
          refresh();
        } else if (status.status === "error") {
          setDownloadPercent(null);
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
      if (url.trim()) {
        await downloadModel({ url: url.trim() });
      } else if (hfRepo.trim()) {
        await downloadModel({ hf_repo: hfRepo.trim() });
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
    <div className="bg-surface-soft border border-hairline">
      <div className="h-1 w-full m-stripe" aria-hidden="true" />
      <div className="px-5 py-4">
        <div className="label-caps text-[12px] text-muted mb-3">Model Manager</div>

        <div className="space-y-3 mb-4">
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Direct GGUF URL"
            className="w-full bg-surface border border-hairline px-3 py-2 text-sm font-light text-on-dark"
          />
          <input
            type="text"
            value={hfRepo}
            onChange={(e) => setHfRepo(e.target.value)}
            placeholder="HuggingFace: org/model:filename.gguf"
            className="w-full bg-surface border border-hairline px-3 py-2 text-sm font-light text-on-dark"
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
          {downloadPercent !== null && (
            <div className="text-xs text-muted">{downloadPercent}% complete</div>
          )}
        </div>

        {error && (
          <div className="mb-3 text-sm text-m-red border-l-2 border-m-red pl-3">
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
              className="flex flex-wrap items-center justify-between gap-2 border border-hairline px-3 py-2"
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
                    className="cursor-pointer label-caps text-[10px] border border-hairline px-2 py-1 hover:border-on-dark"
                  >
                    Select
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => handleDelete(m.name)}
                  className="cursor-pointer label-caps text-[10px] border border-hairline px-2 py-1 text-m-red hover:border-m-red"
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
