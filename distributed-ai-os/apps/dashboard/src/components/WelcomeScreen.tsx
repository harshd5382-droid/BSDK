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
    <div className="max-w-5xl mx-auto">
      <motion.div
        custom={0}
        variants={fadeUp}
        initial="hidden"
        animate="visible"
        className="flex items-center gap-3 mb-6"
      >
        <span className="h-4 w-1.5 m-stripe" aria-hidden="true" />
        <span className="label-caps text-on-dark">Generation 1</span>
      </motion.div>

      <motion.h1
        custom={1}
        variants={fadeUp}
        initial="hidden"
        animate="visible"
        className="display text-5xl md:text-7xl lg:text-8xl mb-6"
      >
        More Power.
        <br />
        Together.
      </motion.h1>

      <motion.p
        custom={2}
        variants={fadeUp}
        initial="hidden"
        animate="visible"
        className="text-body-strong text-lg md:text-xl font-light max-w-xl leading-relaxed mb-12"
      >
        Connect two PCs to run AI together. One machine drives, the other
        lends its power. One click to start.
      </motion.p>

      <motion.div
        custom={3}
        variants={fadeUp}
        initial="hidden"
        animate="visible"
        className="grid grid-cols-2 md:grid-cols-4 gap-px bg-hairline border border-hairline mb-12"
      >
        <Spec label="Hostname" value={system.hostname} />
        <Spec label="LAN IP" value={system.lan_ip} />
        <Spec label="CPU" value={`${system.cpu_count} threads`} />
        <Spec
          label="RAM"
          value={`${system.ram_available_gb} / ${system.ram_total_gb} GB`}
        />
      </motion.div>

      <motion.button
        custom={4}
        variants={fadeUp}
        initial="hidden"
        animate="visible"
        whileTap={{ scale: 0.98 }}
        onClick={onNext}
        className="btn-m"
      >
        Get Started
        <span aria-hidden="true" className="ml-3">
          &rarr;
        </span>
      </motion.button>
    </div>
  );
}

function Spec({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-surface-soft px-5 py-6">
      <div className="font-display text-2xl font-bold leading-none truncate text-on-dark">
        {value}
      </div>
      <div className="label-caps text-[12px] text-muted mt-3">{label}</div>
    </div>
  );
}
