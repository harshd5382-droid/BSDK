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
import type { NodeRole, SystemInfo, WizardStep } from "./types";

const stepVariants = {
  enter: { opacity: 0, x: 40 },
  center: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -40 },
};

export default function App() {
  const [step, setStep] = useState<WizardStep>("welcome");
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [role, setRole] = useState<NodeRole | null>(null);
  const [loading, setLoading] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [stopping, setStopping] = useState(false);

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

  const handleStartCoordinator = useCallback(
    async (peerHost: string, modelPath: string) => {
      setLoading(true);
      setStartError(null);
      try {
        const useMock = !modelPath;
        await startNode({
          role: "coordinator",
          peer_host: peerHost,
          peer_rpc_port: 50052,
          peer_api_port: 8001,
          model_path: modelPath || undefined,
          backend: useMock ? "mock" : "llama.cpp",
          api_port: 8000,
        });
        setStep("live");
        refresh();
      } catch (e) {
        setStartError(e instanceof Error ? e.message : "Start failed");
      } finally {
        setLoading(false);
      }
    },
    [refresh],
  );

  const handleStartWorker = useCallback(async () => {
    setLoading(true);
    setStartError(null);
    try {
      await startNode({
        role: "worker",
        backend: "llama.cpp",
        api_port: 8001,
        rpc_port: 50052,
      });
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
      refresh();
    } finally {
      setStopping(false);
    }
  }, [refresh]);

  const handleRestart = useCallback(() => {
    handleStop().then(() => setStep("role"));
  }, [handleStop]);

  if (!system) {
    return (
      <div className="min-h-screen grid-bg noise-overlay flex items-center justify-center">
        <div className="font-display text-accent animate-pulse">Loading…</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen grid-bg noise-overlay">
      <header className="border-b border-fabric-700/50 px-6 py-4 flex items-center justify-between">
        <div className="font-display text-sm tracking-wider text-accent">
          DAIOS
        </div>
        <div className="text-xs text-fabric-600 font-display">
          {system.lan_ip}
        </div>
      </header>

      <main className="px-6 py-10">
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
                logLines={lines}
                logBottomRef={bottomRef}
                onStop={handleStop}
                onRestart={handleRestart}
                stopping={stopping}
              />
            )}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}
