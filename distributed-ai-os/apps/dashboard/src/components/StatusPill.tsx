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
      className={`inline-flex items-center gap-2 px-3 py-2 text-xs border ${
        ok
          ? "border-on-dark text-on-dark"
          : "border-hairline text-muted"
      }`}
    >
      <span
        className={`h-2 w-2 ${ok ? "bg-success" : "bg-hairline"}`}
        aria-hidden="true"
      />
      <span className="label-caps text-[11px] tracking-[1px]">{label}</span>
      {detail && (
        <span className="font-display font-light text-body normal-case tracking-normal">
          {detail}
        </span>
      )}
    </motion.div>
  );
}
