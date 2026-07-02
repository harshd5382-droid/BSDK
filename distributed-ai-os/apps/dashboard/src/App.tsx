import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  getSystem,
  startNode,
  stopNode,
} from "./api/launcher";
import { useStatus } from "./hooks/useStatus";
import WelcomeScreen from "./components/WelcomeScreen";
import RoleSelect from "./components/RoleSelect";
import ConnectCoordinator from "./components/ConnectCoordinator";
import ConnectWorker from "./components/ConnectWorker";
import LiveStatus from "./components/LiveStatus";
import type { NodeRole, StartRequest, SystemInfo, WizardStep } from "./types";

const stepVariants = {
  enter: { opacity: 0, x: 40 },
  center: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -40 },
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

  const { status, cluster, refresh } = useStatus(
    step === "live" ? 2000 : 5000,
  );

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
    window.scrollTo({ top: 0, behavior: "auto" });
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
        <span className="relative flex h-3 w-3">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full m-stripe opacity-60" />
          <span className="relative inline-flex h-3 w-3 rounded-full m-stripe" />
        </span>
        <div className="label-caps text-muted animate-pulse">Loading</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <header className="sticky top-0 z-50 h-[72px] px-5 md:px-8 flex items-stretch justify-between bg-canvas border-b border-hairline">
        <div className="flex items-center gap-4">
          <span className="inline-flex h-3 w-3 m-stripe" aria-hidden="true" />
          <div className="flex items-baseline gap-3">
            <span
              className="display text-xl leading-none tracking-[-0.04em]"
              title="Beyond Single Device Kernel"
            >
              BSDK
            </span>
            <span className="hidden sm:inline label-caps text-[10px] text-muted">
              Control plane
            </span>
          </div>
        </div>
        <div className="flex items-center border-l border-hairline pl-5 md:pl-8">
          <div className="text-right">
            <div className="label-caps text-[9px] text-muted mb-1">Local endpoint</div>
            <div className="text-xs text-body-strong font-mono tabular-nums">
              {system.lan_ip}
            </div>
          </div>
        </div>
      </header>

      <main id="main-content" className="px-5 py-12 md:px-8 md:py-16">
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
                system={system}
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
