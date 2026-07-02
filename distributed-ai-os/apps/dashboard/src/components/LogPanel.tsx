import { motion, AnimatePresence } from "motion/react";

interface Props {
  lines: string[];
  bottomRef: React.RefObject<HTMLDivElement | null>;
}

const VISIBLE_LINES = 20;

export default function LogPanel({ lines, bottomRef }: Props) {
  const visible = lines.slice(-VISIBLE_LINES);
  return (
    <div className="bg-surface-soft border border-hairline rounded-2xl backdrop-blur-xl overflow-hidden">
      <div className="h-1 w-full m-stripe opacity-70" aria-hidden="true" />
      <div className="px-4 py-2.5 border-b border-hairline flex items-center justify-between">
        <span className="label-caps text-[12px] text-body-strong">Recent Log</span>
        <span className="font-display text-xs font-light text-muted">
          last {VISIBLE_LINES} lines
        </span>
      </div>
      <div className="h-40 overflow-y-auto p-3 font-display font-light text-xs leading-relaxed text-body-strong">
        <AnimatePresence initial={false}>
          {visible.length === 0 ? (
            <div className="text-muted">Waiting for output…</div>
          ) : (
            visible.map((line, i) => (
              <motion.div
                key={`${i}-${line.slice(0, 40)}`}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                className="truncate"
              >
                {line}
              </motion.div>
            ))
          )}
        </AnimatePresence>
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
