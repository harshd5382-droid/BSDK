import { motion } from "motion/react";
import type { SystemInfo } from "../types";

interface Props {
  system: SystemInfo;
  onNext: () => void;
}

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.08, duration: 0.4, ease: "easeOut" as const },
  }),
};

export default function WelcomeScreen({ system, onNext }: Props) {
  return (
    <div className="max-w-6xl mx-auto">
      <motion.div
        custom={0}
        variants={fadeUp}
        initial="hidden"
        animate="visible"
        className="flex items-center gap-3 mb-10"
      >
        <span className="inline-flex h-px w-8 m-stripe" aria-hidden="true" />
        <span className="label-caps text-[11px] text-body-strong">
          Distributed inference / Node ready
        </span>
      </motion.div>

      <div className="grid lg:grid-cols-[minmax(0,1.55fr)_minmax(280px,0.45fr)] gap-12 lg:gap-20 items-end mb-14">
        <motion.h1
          custom={1}
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          className="display text-5xl sm:text-6xl md:text-7xl lg:text-[88px]"
        >
          One model.
          <br />
          Every machine.
        </motion.h1>

        <motion.div
          custom={2}
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          className="border-l border-hairline pl-6"
        >
          <p className="text-body-strong text-base leading-7 mb-6">
            Pool memory and compute across your LAN, then serve the cluster
            through one OpenAI-compatible endpoint.
          </p>
          <button onClick={onNext} className="btn-m w-full sm:w-auto">
            Configure node
            <span aria-hidden="true" className="ml-3">→</span>
          </button>
        </motion.div>
      </div>

      <motion.div
        custom={3}
        variants={fadeUp}
        initial="hidden"
        animate="visible"
        className="grid grid-cols-2 lg:grid-cols-4 border-t border-l border-hairline"
      >
        <Spec label="Hostname" value={system.hostname} />
        <Spec label="LAN IP" value={system.lan_ip} />
        <Spec label="CPU" value={`${system.cpu_count} threads`} />
        <Spec
          label="RAM"
          value={`${system.ram_available_gb} / ${system.ram_total_gb} GB`}
        />
      </motion.div>

    </div>
  );
}

function Spec({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-surface-soft border-r border-b border-hairline px-5 py-7 min-h-28">
      <div className="metric-value text-lg md:text-2xl font-medium leading-none truncate text-on-dark">
        {value}
      </div>
      <div className="label-caps text-[10px] text-muted mt-5">{label}</div>
    </div>
  );
}
