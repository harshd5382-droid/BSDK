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
    <div className="flex flex-col items-center text-center max-w-lg mx-auto">
      <motion.div
        custom={0}
        variants={fadeUp}
        initial="hidden"
        animate="visible"
        className="font-display text-xs tracking-[0.3em] uppercase text-accent mb-4"
      >
        Generation 1
      </motion.div>

      <motion.h1
        custom={1}
        variants={fadeUp}
        initial="hidden"
        animate="visible"
        className="font-display text-3xl md:text-4xl font-semibold mb-3"
      >
        Distributed AI OS
      </motion.h1>

      <motion.p
        custom={2}
        variants={fadeUp}
        initial="hidden"
        animate="visible"
        className="text-fabric-600 text-lg mb-10 leading-relaxed"
      >
        Connect two PCs to run AI together. One click to start.
      </motion.p>

      <motion.div
        custom={3}
        variants={fadeUp}
        initial="hidden"
        animate="visible"
        className="w-full grid grid-cols-2 gap-3 mb-10 text-left"
      >
        <Spec label="Hostname" value={system.hostname} />
        <Spec label="LAN IP" value={system.lan_ip} highlight />
        <Spec label="CPU" value={`${system.cpu_count} threads`} />
        <Spec
          label="RAM"
          value={`${system.ram_available_gb} / ${system.ram_total_gb} GB free`}
        />
      </motion.div>

      <motion.button
        custom={4}
        variants={fadeUp}
        initial="hidden"
        animate="visible"
        whileTap={{ scale: 0.97 }}
        onClick={onNext}
        className="cursor-pointer px-10 py-4 bg-accent text-fabric-950 font-semibold rounded-lg text-lg hover:bg-accent-dim transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-fabric-950"
      >
        Get Started
      </motion.button>
    </div>
  );
}

function Spec({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="bg-fabric-800/60 border border-fabric-700 rounded-lg px-4 py-3">
      <div className="text-xs text-fabric-600 uppercase tracking-wider mb-1">
        {label}
      </div>
      <div
        className={`font-display text-sm ${highlight ? "text-accent" : "text-white"}`}
      >
        {value}
      </div>
    </div>
  );
}
