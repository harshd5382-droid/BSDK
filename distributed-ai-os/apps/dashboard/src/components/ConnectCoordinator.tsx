import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import type { SystemInfo } from "../types";

interface Props {
  system: SystemInfo;
  onStart: (peerHosts: string[], modelPath: string, discovery: boolean) => void;
  onBack: () => void;
  loading: boolean;
  error: string | null;
}

function isLocalPeer(host: string, system: SystemInfo): boolean {
  const normalized = host.trim().toLowerCase().split(":")[0];
  if (!normalized || normalized === "localhost" || normalized === "127.0.0.1") {
    return true;
  }
  if (normalized === system.lan_ip.toLowerCase()) return true;
  return (system.local_ips ?? []).some((ip) => ip.toLowerCase() === normalized);
}

export default function ConnectCoordinator({
  system,
  onStart,
  onBack,
  loading,
  error,
}: Props) {
  const [peerHosts, setPeerHosts] = useState<string[]>([""]);
  const [modelPath, setModelPath] = useState(system.models[0] ?? "");
  const [autoDiscovery, setAutoDiscovery] = useState(false);

  const cleanHosts = peerHosts.map((h) => h.trim()).filter(Boolean);
  const anyLocal = cleanHosts.some((h) => isLocalPeer(h, system));
  const canStart =
    autoDiscovery ||
    (cleanHosts.length > 0 && !anyLocal && (modelPath || system.models.length === 0));

  const addHost = () => setPeerHosts((prev) => [...prev, ""]);
  const removeHost = (idx: number) =>
    setPeerHosts((prev) => (prev.length === 1 ? [""] : prev.filter((_, i) => i !== idx)));
  const updateHost = (idx: number, value: string) =>
    setPeerHosts((prev) => prev.map((h, i) => (i === idx ? value : h)));

  return (
    <div className="max-w-xl mx-auto">
      <div className="flex items-center gap-3 mb-8">
        <span className="inline-flex h-px w-8 m-stripe" aria-hidden="true" />
        <span className="label-caps text-muted">Setup / 02 / Coordinator</span>
      </div>

      <h2 className="display text-4xl md:text-5xl mb-4">Connect To Other PCs</h2>
      <p className="text-body text-base font-light mb-10">
        Enter the LAN IP of each PC running as Worker. Add as many as you want.
      </p>

      <div className="space-y-6 mb-10">
        <label className="flex items-center gap-3 cursor-pointer bg-surface-soft border border-hairline rounded-xl px-4 py-3 backdrop-blur-xl">
          <input
            type="checkbox"
            checked={autoDiscovery}
            onChange={(e) => setAutoDiscovery(e.target.checked)}
            className="w-4 h-4 accent-m-blue-dark rounded"
          />
          <span className="text-sm font-light text-body">
            <span className="text-on-dark">Auto Discovery</span> — find workers
            on LAN via mDNS
          </span>
        </label>

        {!autoDiscovery && (
          <Field label="Worker PC IP addresses">
            <div className="space-y-2">
              <AnimatePresence initial={false}>
                {peerHosts.map((host, idx) => (
                  <motion.div
                    key={idx}
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="flex items-center gap-2"
                  >
                    <input
                      type="text"
                      placeholder={
                        idx === 0 ? "e.g. 192.168.1.42" : "another worker IP"
                      }
                      value={host}
                      onChange={(e) => updateHost(idx, e.target.value)}
                      className="w-full bg-surface-card border border-hairline rounded-xl px-4 h-12 font-display text-sm text-on-dark placeholder:text-muted focus:outline-none focus:border-hairline-strong backdrop-blur-xl transition-colors"
                    />
                    <motion.button
                      whileTap={{ scale: 0.97 }}
                      type="button"
                      onClick={() => removeHost(idx)}
                      className="cursor-pointer shrink-0 label-caps text-[11px] text-muted hover:text-m-red border border-hairline rounded-full w-10 h-10 transition-colors"
                      title="Remove this worker"
                    >
                      &times;
                    </motion.button>
                  </motion.div>
                ))}
              </AnimatePresence>
              <motion.button
                whileTap={{ scale: 0.98 }}
                type="button"
                onClick={addHost}
                className="cursor-pointer label-caps text-[11px] text-muted hover:text-on-dark border border-dashed border-hairline rounded-xl w-full h-10 transition-colors"
              >
                + Add another worker PC
              </motion.button>
            </div>
          </Field>
        )}

        {system.models.length > 0 ? (
          <Field label="Model">
            <select
              value={modelPath}
              onChange={(e) => setModelPath(e.target.value)}
              className="w-full bg-surface-card border border-hairline rounded-xl px-4 h-12 font-display text-sm text-on-dark focus:outline-none focus:border-hairline-strong cursor-pointer backdrop-blur-xl transition-colors"
            >
              {system.models.map((m) => (
                <option key={m} value={`models/${m}`}>
                  {m}
                </option>
              ))}
            </select>
          </Field>
        ) : (
          <div className="bg-surface-soft border-l-2 border-warning rounded-xl px-4 py-3 text-sm font-light text-body backdrop-blur-xl">
            No GGUF models found in{" "}
            <code className="font-display text-on-dark">models/</code>. Mock mode
            will be used for testing.
          </div>
        )}

        <div className="bg-surface-soft border border-hairline rounded-xl px-4 py-3 text-sm font-light text-body backdrop-blur-xl">
          This PC is the <span className="text-on-dark">Coordinator</span> — its
          address is{" "}
          <span className="font-display text-on-dark">{system.lan_ip}</span>.
          Enter the <span className="text-on-dark">other</span> PCs' worker IPs
          above.
        </div>

        {anyLocal && !autoDiscovery && (
          <div className="bg-surface-soft border-l-2 border-warning rounded-xl px-4 py-3 text-sm font-light text-body backdrop-blur-xl">
            One of those IPs is this computer. Run as{" "}
            <span className="text-on-dark">Worker</span> here instead, and
            Coordinator on the other PC.
          </div>
        )}
      </div>

      {error && (
        <motion.div
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          className="mb-6 bg-surface-soft border-l-2 border-m-red rounded-xl px-4 py-3 text-sm font-light text-body-strong backdrop-blur-xl"
        >
          {error}
        </motion.div>
      )}

      <motion.button
        whileTap={{ scale: 0.98 }}
        disabled={!canStart || loading}
        onClick={() =>
          onStart(
            autoDiscovery ? [] : cleanHosts,
            modelPath ? modelPath : "",
            autoDiscovery,
          )
        }
        className="btn-m w-full"
      >
        {loading ? "Starting…" : "Connect And Start"}
      </motion.button>

      <button
        onClick={onBack}
        className="mt-6 cursor-pointer label-caps text-[12px] text-muted hover:text-on-dark transition-colors"
      >
        &larr; Back
      </button>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block label-caps text-[12px] text-muted mb-3">
        {label}
      </label>
      {children}
    </div>
  );
}
