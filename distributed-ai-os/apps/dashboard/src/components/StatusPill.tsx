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
      className={`flex min-h-14 items-center gap-3 px-4 py-3 text-xs ${
        ok
          ? "text-on-dark bg-surface-card"
          : "text-muted bg-surface-soft"
      }`}
    >
      <span
        className={`h-2 w-2 ${ok ? "m-stripe" : "bg-hairline"}`}
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
