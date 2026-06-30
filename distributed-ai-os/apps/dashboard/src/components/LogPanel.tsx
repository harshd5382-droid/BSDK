import { motion, AnimatePresence } from "motion/react";

interface Props {
  lines: string[];
  bottomRef: React.RefObject<HTMLDivElement | null>;
}

const VISIBLE_LINES = 20;

export default function LogPanel({ lines, bottomRef }: Props) {
  const visible = lines.slice(-VISIBLE_LINES);
  return (
    <div className="bg-fabric-900 border border-fabric-700 rounded-lg overflow-hidden">
      <div className="px-4 py-2 border-b border-fabric-700 text-xs uppercase tracking-wider text-fabric-600 font-display flex items-center justify-between">
        <span>Recent Log</span>
        <span className="text-fabric-700 normal-case tracking-normal">
          last {VISIBLE_LINES} lines
        </span>
      </div>
      <div className="h-40 overflow-y-auto p-3 font-display text-xs leading-relaxed text-white/90">
        <AnimatePresence initial={false}>
          {visible.length === 0 ? (
            <div className="text-white/50">Waiting for output…</div>
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
