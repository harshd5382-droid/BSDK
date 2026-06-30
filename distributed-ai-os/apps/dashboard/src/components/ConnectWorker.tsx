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
    <div className="max-w-lg mx-auto text-center">
      <h2 className="font-display text-2xl font-semibold mb-2">
        Share this PC's power
      </h2>
      <p className="text-fabric-600 mb-8 text-sm">
        Tell the other PC to connect to this address.
      </p>

      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="bg-fabric-800 border border-accent/30 rounded-xl p-8 mb-8"
      >
        <label className="flex items-center justify-center gap-3 cursor-pointer mb-4">
          <input
            type="checkbox"
            checked={autoDiscovery}
            onChange={(e) => setAutoDiscovery(e.target.checked)}
            className="w-4 h-4 accent-accent"
          />
          <span className="text-sm text-fabric-600">
            <strong className="text-white">Auto Discovery</strong> — join cluster via mDNS
          </span>
        </label>
        <div className="text-xs uppercase tracking-wider text-fabric-600 mb-2">
          {autoDiscovery ? "LAN address (auto-discovered)" : "Share this address"}
        </div>
        <div className="font-display text-3xl text-accent font-semibold select-all">
          {system.lan_ip}:50052
        </div>
        <div className="text-fabric-600 text-sm mt-3">
          Port 50052 must be open in your firewall
        </div>
      </motion.div>

      <div className="bg-fabric-800/50 border border-fabric-700 rounded-lg px-4 py-3 text-sm text-fabric-600 mb-8 text-left">
        <strong className="text-white">Steps on the other PC:</strong>
        <ol className="mt-2 space-y-1 list-decimal list-inside">
          <li>Open this dashboard on the other computer</li>
          <li>Choose "Run the AI here (Coordinator)"</li>
          <li>Enter <span className="font-display text-accent">{system.lan_ip}</span> as the worker IP</li>
        </ol>
      </div>

      {error && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="mb-4 px-4 py-3 bg-danger/10 border border-danger/30 rounded-lg text-danger text-sm"
        >
          {error}
        </motion.div>
      )}

      <motion.button
        whileTap={{ scale: 0.97 }}
        disabled={loading}
        onClick={() => onStart(autoDiscovery)}
        className="cursor-pointer w-full py-4 bg-accent text-fabric-950 font-semibold rounded-lg text-lg hover:bg-accent-dim disabled:opacity-40 transition-colors duration-200"
      >
        {loading ? "Starting…" : "Start Worker"}
      </motion.button>

      <div className="mt-4">
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
