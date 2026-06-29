import { useState } from "react";
import { motion } from "motion/react";
import type { SystemInfo } from "../types";

interface Props {
  system: SystemInfo;
  onStart: (peerHost: string, modelPath: string) => void;
  onBack: () => void;
  loading: boolean;
  error: string | null;
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

  const canStart = peerHost.trim() && (modelPath || system.models.length === 0);

  return (
    <div className="max-w-lg mx-auto">
      <h2 className="font-display text-2xl font-semibold text-center mb-2">
        Connect to another PC
      </h2>
      <p className="text-fabric-600 text-center mb-8 text-sm">
        Enter the LAN IP of the PC running as Worker.
      </p>

      <div className="space-y-5 mb-8">
        <Field label="Other PC's IP address">
          <input
            type="text"
            placeholder="e.g. 192.168.1.42"
            value={peerHost}
            onChange={(e) => setPeerHost(e.target.value)}
            className="w-full bg-fabric-800 border border-fabric-700 rounded-lg px-4 py-3 font-display text-sm text-white placeholder:text-fabric-600 focus:outline-none focus:border-accent"
          />
        </Field>

        {system.models.length > 0 ? (
          <Field label="Model">
            <select
              value={modelPath}
              onChange={(e) => setModelPath(e.target.value)}
              className="w-full bg-fabric-800 border border-fabric-700 rounded-lg px-4 py-3 font-display text-sm text-white focus:outline-none focus:border-accent cursor-pointer"
            >
              {system.models.map((m) => (
                <option key={m} value={`models/${m}`}>
                  {m}
                </option>
              ))}
            </select>
          </Field>
        ) : (
          <div className="bg-warm/10 border border-warm/30 rounded-lg px-4 py-3 text-sm text-warm">
            No GGUF models found in <code className="font-display">models/</code>.
            Mock mode will be used for testing.
          </div>
        )}

        <div className="bg-fabric-800/50 border border-fabric-700 rounded-lg px-4 py-3 text-sm text-fabric-600">
          This PC's address:{" "}
          <span className="font-display text-accent">{system.lan_ip}</span>
        </div>
      </div>

      {error && (
        <motion.div
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          className="mb-4 px-4 py-3 bg-danger/10 border border-danger/30 rounded-lg text-danger text-sm"
        >
          {error}
        </motion.div>
      )}

      <motion.button
        whileTap={{ scale: 0.97 }}
        disabled={!canStart || loading}
        onClick={() =>
          onStart(
            peerHost.trim(),
            modelPath ? modelPath : "",
          )
        }
        className="cursor-pointer w-full py-4 bg-accent text-fabric-950 font-semibold rounded-lg text-lg hover:bg-accent-dim disabled:opacity-40 disabled:cursor-not-allowed transition-colors duration-200"
      >
        {loading ? "Starting…" : "Connect and Start"}
      </motion.button>

      <div className="text-center mt-4">
        <button
          onClick={onBack}
          className="cursor-pointer text-fabric-600 hover:text-white text-sm transition-colors"
        >
          ← Back
        </button>
      </div>
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
      <label className="block text-xs uppercase tracking-wider text-fabric-600 mb-2">
        {label}
      </label>
      {children}
    </div>
  );
}
