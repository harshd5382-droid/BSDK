import { motion } from "motion/react";
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

export default function RoleSelect({ onSelect, onBack }: Props) {
  return (
    <div className="max-w-2xl mx-auto">
      <h2 className="font-display text-2xl font-semibold text-center mb-2">
        What does this PC do?
      </h2>
      <p className="text-fabric-600 text-center mb-4">
        Pick one role for this computer.
      </p>
      <p className="text-center text-xs text-warm mb-8 max-w-md mx-auto">
        In a two-PC cluster: one machine runs <strong>Worker</strong>, the
        other runs <strong>Coordinator</strong>. Do not run the same role on
        both.
      </p>

      <div className="grid md:grid-cols-2 gap-4 mb-8">
        <RoleCard
          index={0}
          title="Run the AI here"
          subtitle="Coordinator"
          description="This PC runs the model and talks to other PCs for extra power."
          icon="◈"
          onClick={() => onSelect("coordinator")}
        />
        <RoleCard
          index={1}
          title="Help another PC"
          subtitle="Worker"
          description="Share this PC's CPU/GPU with another computer running the AI."
          icon="◇"
          onClick={() => onSelect("worker")}
        />
      </div>

      <div className="text-center">
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
  icon: string;
  onClick: () => void;
}) {
  return (
    <motion.button
      custom={index}
      variants={cardVariants}
      initial="hidden"
      animate="visible"
      whileHover={{ y: -4, transition: { duration: 0.2 } }}
      whileTap={{ scale: 0.98 }}
      onClick={onClick}
      className="cursor-pointer text-left bg-fabric-800/80 border border-fabric-700 hover:border-accent/50 rounded-xl p-6 transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-accent"
    >
      <div className="font-display text-2xl text-accent mb-3">{icon}</div>
      <div className="font-semibold text-lg mb-1">{title}</div>
      <div className="font-display text-xs text-accent uppercase tracking-wider mb-3">
        {subtitle}
      </div>
      <p className="text-fabric-600 text-sm leading-relaxed">{description}</p>
    </motion.button>
  );
}
