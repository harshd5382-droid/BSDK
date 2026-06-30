import { motion } from "motion/react";
import type { ReactNode } from "react";
import type { NodeRole } from "../types";

interface Props {
  onSelect: (role: NodeRole) => void;
  onBack: () => void;
}

const cardVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.1, duration: 0.35 },
  }),
};

const CoordinatorIcon = (
  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
    <rect x="7" y="7" width="10" height="10" fill="currentColor" stroke="none" />
    <rect x="3.5" y="3.5" width="17" height="17" />
    <path d="M12 1v2.5M12 20.5V23M1 12h2.5M20.5 12H23" strokeLinecap="round" />
  </svg>
);

const WorkerIcon = (
  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
    <rect x="3.5" y="3.5" width="17" height="17" />
    <path d="M12 1v2.5M12 20.5V23M1 12h2.5M20.5 12H23" strokeLinecap="round" />
  </svg>
);

export default function RoleSelect({ onSelect, onBack }: Props) {
  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <span className="h-4 w-1.5 m-stripe" aria-hidden="true" />
        <span className="label-caps text-muted">Setup · Step 1</span>
      </div>

      <h2 className="display text-4xl md:text-5xl mb-4">
        What Does This PC Do?
      </h2>
      <p className="text-body text-base font-light max-w-xl leading-relaxed mb-3">
        Pick one role for this computer. In a two-PC cluster, one machine runs{" "}
        <span className="text-on-dark">Worker</span> and the other runs{" "}
        <span className="text-on-dark">Coordinator</span> — never the same role
        on both.
      </p>

      <div className="grid md:grid-cols-2 gap-6 mt-10 mb-10">
        <RoleCard
          index={0}
          title="Run The AI Here"
          subtitle="Coordinator"
          description="This PC runs the model and talks to other PCs for extra power."
          icon={CoordinatorIcon}
          onClick={() => onSelect("coordinator")}
        />
        <RoleCard
          index={1}
          title="Help Another PC"
          subtitle="Worker"
          description="Share this PC's CPU/GPU with another computer running the AI."
          icon={WorkerIcon}
          onClick={() => onSelect("worker")}
        />
      </div>

      <button
        onClick={onBack}
        className="cursor-pointer label-caps text-[12px] text-muted hover:text-on-dark transition-colors"
      >
        &larr; Back
      </button>
    </div>
  );
}

function RoleCard({
  index,
  title,
  subtitle,
  description,
  icon,
  onClick,
}: {
  index: number;
  title: string;
  subtitle: string;
  description: string;
  icon: ReactNode;
  onClick: () => void;
}) {
  return (
    <motion.button
      custom={index}
      variants={cardVariants}
      initial="hidden"
      animate="visible"
      whileTap={{ scale: 0.99 }}
      onClick={onClick}
      className="group cursor-pointer text-left bg-surface-card border border-hairline hover:border-on-dark p-6 transition-colors duration-200 focus:outline-none focus:border-on-dark"
    >
      <span className="block h-1 w-10 m-stripe mb-6 opacity-60 group-hover:w-full group-hover:opacity-100 transition-all duration-300" />
      <div className="text-on-dark mb-5">{icon}</div>
      <div className="display text-2xl mb-2">{title}</div>
      <div className="label-caps text-[12px] text-muted mb-4">{subtitle}</div>
      <p className="text-body text-sm font-light leading-relaxed">
        {description}
      </p>
    </motion.button>
  );
}
