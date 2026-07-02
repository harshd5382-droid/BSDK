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
      className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-full text-xs border backdrop-blur-xl ${
        ok
          ? "border-hairline-strong text-on-dark bg-surface-card"
          : "border-hairline text-muted bg-surface-soft"
      }`}
    >
      <span
        className={`h-2 w-2 rounded-full ${ok ? "m-stripe" : "bg-hairline"}`}
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
