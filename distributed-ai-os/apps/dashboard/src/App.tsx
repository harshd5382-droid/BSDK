import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  getSystem,
  startNode,
  stopNode,
} from "./api/launcher";
import { useStatus } from "./hooks/useStatus";
import { useLogs } from "./hooks/useLogs";
import WelcomeScreen from "./components/WelcomeScreen";
import RoleSelect from "./components/RoleSelect";
import ConnectCoordinator from "./components/ConnectCoordinator";
import ConnectWorker from "./components/ConnectWorker";
import LiveStatus from "./components/LiveStatus";
import LogPanel from "./components/LogPanel";
import type { NodeRole, StartRequest, SystemInfo, WizardStep } from "./types";

const stepVariants = {
  enter: { opacity: 0, x: 40 },
  center: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -40 },
};

const drawerVariants = {
  hidden: { opacity: 0, y: -12, scale: 0.98 },
  visible: { opacity: 1, y: 0, scale: 1 },
};

function isLocalPeer(host: string, system: SystemInfo): boolean {
  const normalized = host.trim().toLowerCase().split(":")[0];
  if (!normalized || normalized === "localhost") return true;
  if (normalized === "127.0.0.1") return true;
  if (normalized === system.lan_ip.toLowerCase()) return true;
  return (system.local_ips ?? []).some((ip) => ip.toLowerCase() === normalized);
}

export default function App() {
  const [step, setStep] = useState<WizardStep>("welcome");
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [role, setRole] = useState<NodeRole | null>(null);
  const [loading, setLoading] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [stopping, setStopping] = useState(false);
  const [lastStart, setLastStart] = useState<StartRequest | null>(null);
  const [showLogs, setShowLogs] = useState(false);

  const { status, cluster, refresh } = useStatus(
    step === "live" ? 2000 : 5000,
  );
  const { lines, bottomRef } = useLogs(step === "live");

  useEffect(() => {
    getSystem()
      .then(setSystem)
      .catch(() =>
        setSystem({
          hostname: "unknown",
          lan_ip: "127.0.0.1",
          local_ips: ["127.0.0.1"],
          cpu_count: 1,
          ram_total_gb: 0,
          ram_available_gb: 0,
          models: [],
        }),
      );
  }, []);

  useEffect(() => {
    if (status?.node_state === "running" && step !== "live") {
      setStep("live");
    }
  }, [status, step]);

  useEffect(() => {
    if (step !== "live") setShowLogs(false);
  }, [step]);

  const handleStartCoordinator = useCallback(
    async (peerHost: string, modelPath: string, discovery: boolean) => {
      if (!system) return;
      if (!discovery && isLocalPeer(peerHost, system)) {
        setStartError(
          `Worker IP cannot be this PC (${system.lan_ip}). Choose Worker on this machine and Coordinator on the other PC.`,
        );
        return;
      }

      setLoading(true);
      setStartError(null);
      const req: StartRequest = {
        role: "coordinator",
        peer_host: discovery ? undefined : peerHost.trim(),
        peer_rpc_port: 50052,
        peer_api_port: 8001,
        model_path: modelPath || undefined,
        backend: modelPath ? "llama.cpp" : "mock",
        api_port: 8000,
        discovery_enabled: discovery,
      };
      try {
        await startNode(req);
        setLastStart(req);
        setRole("coordinator");
        setStep("live");
        refresh();
      } catch (e) {
        setStartError(e instanceof Error ? e.message : "Start failed");
      } finally {
        setLoading(false);
      }
    },
    [refresh, system],
  );

  const handleStartWorker = useCallback(async (discovery: boolean) => {
    setLoading(true);
    setStartError(null);
    const req: StartRequest = {
      role: "worker",
      backend: "llama.cpp",
      api_port: 8001,
      rpc_port: 50052,
      discovery_enabled: discovery,
    };
    try {
      await startNode(req);
      setLastStart(req);
      setRole("worker");
      setStep("live");
      refresh();
    } catch (e) {
      setStartError(e instanceof Error ? e.message : "Start failed");
    } finally {
      setLoading(false);
    }
  }, [refresh]);

  const handleStop = useCallback(async () => {
    setStopping(true);
    try {
      await stopNode();
      setStep("welcome");
      setRole(null);
      setLastStart(null);
      refresh();
    } finally {
      setStopping(false);
    }
  }, [refresh]);

  const handleRestart = useCallback(async () => {
    if (!lastStart) {
      await handleStop();
      setStep("role");
      return;
    }
    setStopping(true);
    setLoading(true);
    setStartError(null);
    try {
      await stopNode();
      await startNode(lastStart);
      setStep("live");
      refresh();
    } catch (e) {
      setStartError(e instanceof Error ? e.message : "Restart failed");
      setStep("connect");
    } finally {
      setStopping(false);
      setLoading(false);
    }
  }, [handleStop, lastStart, refresh]);

  if (!system) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4">
        <div className="h-1 w-24 m-stripe" />
        <div className="label-caps text-muted animate-pulse">Loading</div>
      </div>
    );
  }

  const isLive = step === "live";
  const logCount = Math.min(lines.length, 20);

  return (
    <div className="min-h-screen">
      <div className="h-1 w-full m-stripe" aria-hidden="true" />
      <header className="relative z-50 h-16 border-b border-hairline px-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="h-6 w-1.5 m-stripe" aria-hidden="true" />
          <span
            className="display text-lg leading-none"
            title="Beyond Single Device Kernel"
          >
            BSDK
          </span>
          <span className="hidden md:inline text-[10px] uppercase tracking-[0.18em] text-muted font-display max-w-56 leading-tight">
            Beyond Single Device Kernel
          </span>
        </div>
        <div className="flex items-center gap-4">
          {isLive && (
            <motion.button
              type="button"
              whileTap={{ scale: 0.97 }}
              onClick={() => setShowLogs((v) => !v)}
              aria-expanded={showLogs}
              aria-controls="log-drawer"
              className={`cursor-pointer flex items-center gap-2 px-4 min-h-[44px] label-caps text-[12px] tracking-[1.5px] border transition-colors ${
                showLogs
                  ? "border-on-dark text-on-dark"
                  : "border-hairline text-muted hover:border-on-dark hover:text-on-dark"
              }`}
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M4 6h16M4 12h16M4 18h10" />
              </svg>
              <span>Logs</span>
              {logCount > 0 && (
                <span className="ml-0.5 px-1.5 py-0.5 bg-surface-elevated text-[10px] leading-none text-on-dark/80">
                  {logCount}
                </span>
              )}
            </motion.button>
          )}
          <div className="text-xs text-muted font-display tracking-wide">
            {system.lan_ip}
          </div>
        </div>

        <AnimatePresence>
          {isLive && showLogs && (
            <>
              <motion.div
                key="log-backdrop"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onClick={() => setShowLogs(false)}
                className="fixed inset-0 z-40 bg-black/60"
                aria-hidden="true"
              />
              <motion.div
                id="log-drawer"
                key="log-drawer"
                variants={drawerVariants}
                initial="hidden"
                animate="visible"
                exit="hidden"
                transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
                className="absolute right-6 top-full mt-2 z-50 w-[min(92vw,640px)] shadow-2xl shadow-black/50"
              >
                <LogPanel lines={lines} bottomRef={bottomRef} />
              </motion.div>
            </>
          )}
        </AnimatePresence>
      </header>

      <main className="px-6 py-16 md:py-24">
        <AnimatePresence mode="wait">
          <motion.div
            key={step}
            variants={stepVariants}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
          >
            {step === "welcome" && (
              <WelcomeScreen
                system={system}
                onNext={() => setStep("role")}
              />
            )}
            {step === "role" && (
              <RoleSelect
                onSelect={(r) => {
                  setRole(r);
                  setStep("connect");
                }}
                onBack={() => setStep("welcome")}
              />
            )}
            {step === "connect" && role === "coordinator" && (
              <ConnectCoordinator
                system={system}
                onStart={handleStartCoordinator}
                onBack={() => setStep("role")}
                loading={loading}
                error={startError}
              />
            )}
            {step === "connect" && role === "worker" && (
              <ConnectWorker
                system={system}
                onStart={handleStartWorker}
                onBack={() => setStep("role")}
                loading={loading}
                error={startError}
              />
            )}
            {step === "live" && status && (
              <LiveStatus
                status={status}
                cluster={cluster}
                onStop={handleStop}
                onRestart={handleRestart}
                stopping={stopping}
                restarting={loading}
              />
            )}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}
