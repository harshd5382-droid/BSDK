import { useState } from "react";
import { motion } from "motion/react";
import type { SystemInfo } from "../types";

interface Props {
  system: SystemInfo;
  onStart: (discovery: boolean) => void;
  onBack: () => void;
  loading: boolean;
  error: string | null;
}

export default function ConnectWorker({
  system,
  onStart,
  onBack,
  loading,
  error,
}: Props) {
  const [autoDiscovery, setAutoDiscovery] = useState(true);
  return (
    <div className="max-w-xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <span className="h-4 w-1.5 m-stripe" aria-hidden="true" />
        <span className="label-caps text-muted">Worker · Setup</span>
      </div>

      <h2 className="display text-4xl md:text-5xl mb-4">Share This PC's Power</h2>
      <p className="text-body text-base font-light mb-10">
        Tell the other PC to connect to this address.
      </p>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-surface-soft border border-hairline mb-8"
      >
        <div className="h-1 w-full m-stripe" aria-hidden="true" />
        <div className="px-8 py-10">
          <label className="flex items-center gap-3 cursor-pointer mb-6 bg-surface-card border border-hairline px-4 py-3">
            <input
              type="checkbox"
              checked={autoDiscovery}
              onChange={(e) => setAutoDiscovery(e.target.checked)}
              className="w-4 h-4 accent-m-blue-dark"
            />
            <span className="text-sm font-light text-body">
              <span className="text-on-dark">Auto Discovery</span> —{" "}
              {autoDiscovery
                ? "this PC will be found automatically by the coordinator via mDNS"
                : "join cluster via mDNS"}
            </span>
          </label>
          <div className="label-caps text-[12px] text-muted mb-4">
            {autoDiscovery
              ? "This PC's LAN address (advertised via mDNS)"
              : "Share this address"}
          </div>
          <div className="font-display text-3xl md:text-4xl font-bold text-on-dark select-all break-all">
            {system.lan_ip}:50052
          </div>
          <div className="text-body text-sm font-light mt-4">
            {autoDiscovery
              ? "No need to share this address — the coordinator will discover it automatically. Just make sure port 50052 is open in your firewall."
              : "Port 50052 must be open in your firewall."}
          </div>
        </div>
      </motion.div>

      <div className="bg-surface-soft border border-hairline px-5 py-4 text-sm font-light text-body mb-10">
        {autoDiscovery ? (
          <>
            <span className="text-on-dark">Steps on the other PC:</span>
            <ol className="mt-3 space-y-2 list-decimal list-inside marker:text-muted">
              <li>Open this dashboard on the other computer</li>
              <li>Choose "Run the AI here (Coordinator)"</li>
              <li>Enable "Auto Discovery" and click Connect and Start</li>
            </ol>
          </>
        ) : (
          <>
            <span className="text-on-dark">Steps on the other PC:</span>
            <ol className="mt-3 space-y-2 list-decimal list-inside marker:text-muted">
              <li>Open this dashboard on the other computer</li>
              <li>Choose "Run the AI here (Coordinator)"</li>
              <li>
                Enter{" "}
                <span className="font-display text-on-dark">
                  {system.lan_ip}
                </span>{" "}
                as the worker IP
              </li>
            </ol>
          </>
        )}
      </div>

      {error && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="mb-6 bg-surface-soft border-l-2 border-m-red px-4 py-3 text-sm font-light text-body-strong"
        >
          {error}
        </motion.div>
      )}

      <motion.button
        whileTap={{ scale: 0.98 }}
        disabled={loading}
        onClick={() => onStart(autoDiscovery)}
        className="btn-m w-full"
      >
        {loading ? "Starting…" : "Start Worker"}
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
