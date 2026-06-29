import { motion } from "motion/react";

interface Props {
  label: string;
  ok: boolean;
  detail?: string;
}

export default function StatusPill({ label, ok, detail }: Props) {
  return (
    <motion.div
      layout
      className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium border ${
        ok
          ? "bg-success/10 border-success/30 text-success"
          : "bg-fabric-800 border-fabric-700 text-fabric-600"
      }`}
    >
      <span
        className={`w-2 h-2 rounded-full ${ok ? "bg-success" : "bg-fabric-600"}`}
      />
      {label}
      {detail && <span className="text-fabric-600">· {detail}</span>}
    </motion.div>
  );
}
