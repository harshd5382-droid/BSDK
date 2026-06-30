import { useState } from "react";
import { motion } from "motion/react";
import type { SystemInfo } from "../types";

interface Props {
  system: SystemInfo;
  onStart: (peerHost: string, modelPath: string, discovery: boolean) => void;
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
  const [peerHost, setPeerHost] = useState("");
  const [modelPath, setModelPath] = useState(system.models[0] ?? "");
  const [autoDiscovery, setAutoDiscovery] = useState(false);

  const peerIsSelf = peerHost.trim() ? isLocalPeer(peerHost, system) : false;
  const canStart =
    autoDiscovery ||
    (peerHost.trim() && !peerIsSelf && (modelPath || system.models.length === 0));

  return (
    <div className="max-w-xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <span className="h-4 w-1.5 m-stripe" aria-hidden="true" />
        <span className="label-caps text-muted">Coordinator · Setup</span>
      </div>

      <h2 className="display text-4xl md:text-5xl mb-4">Connect To Another PC</h2>
      <p className="text-body text-base font-light mb-10">
        Enter the LAN IP of the PC running as Worker.
      </p>

      <div className="space-y-6 mb-10">
        <label className="flex items-center gap-3 cursor-pointer bg-surface-soft border border-hairline px-4 py-3">
          <input
            type="checkbox"
            checked={autoDiscovery}
            onChange={(e) => setAutoDiscovery(e.target.checked)}
            className="w-4 h-4 accent-m-blue-dark"
          />
          <span className="text-sm font-light text-body">
            <span className="text-on-dark">Auto Discovery</span> — find workers
            on LAN via mDNS
          </span>
        </label>

        {!autoDiscovery && (
        <Field label="Other PC's IP address">
          <input
            type="text"
            placeholder="e.g. 192.168.1.42"
            value={peerHost}
            onChange={(e) => setPeerHost(e.target.value)}
            className="w-full bg-surface-card border border-hairline px-4 h-12 font-display text-sm text-on-dark placeholder:text-muted focus:outline-none focus:border-on-dark transition-colors"
          />
        </Field>
        )}

        {system.models.length > 0 ? (
          <Field label="Model">
            <select
              value={modelPath}
              onChange={(e) => setModelPath(e.target.value)}
              className="w-full bg-surface-card border border-hairline px-4 h-12 font-display text-sm text-on-dark focus:outline-none focus:border-on-dark cursor-pointer transition-colors"
            >
              {system.models.map((m) => (
                <option key={m} value={`models/${m}`}>
                  {m}
                </option>
              ))}
            </select>
          </Field>
        ) : (
          <div className="bg-surface-soft border-l-2 border-warning px-4 py-3 text-sm font-light text-body">
            No GGUF models found in{" "}
            <code className="font-display text-on-dark">models/</code>. Mock mode
            will be used for testing.
          </div>
        )}

        <div className="bg-surface-soft border border-hairline px-4 py-3 text-sm font-light text-body">
          This PC is the <span className="text-on-dark">Coordinator</span> — its
          address is{" "}
          <span className="font-display text-on-dark">{system.lan_ip}</span>.
          Enter the <span className="text-on-dark">other</span> PC's worker IP
          above.
        </div>

        {peerIsSelf && (
          <div className="bg-surface-soft border-l-2 border-warning px-4 py-3 text-sm font-light text-body">
            That IP is this computer. Run as{" "}
            <span className="text-on-dark">Worker</span> here instead, and
            Coordinator on the other PC.
          </div>
        )}
      </div>

      {error && (
        <motion.div
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          className="mb-6 bg-surface-soft border-l-2 border-m-red px-4 py-3 text-sm font-light text-body-strong"
        >
          {error}
        </motion.div>
      )}

      <motion.button
        whileTap={{ scale: 0.98 }}
        disabled={!canStart || loading}
        onClick={() =>
          onStart(peerHost.trim(), modelPath ? modelPath : "", autoDiscovery)
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
