import { motion, AnimatePresence } from "motion/react";

interface Props {
  lines: string[];
  bottomRef: React.RefObject<HTMLDivElement | null>;
}

export default function LogPanel({ lines, bottomRef }: Props) {
  return (
    <div className="bg-fabric-900 border border-fabric-700 rounded-lg overflow-hidden">
      <div className="px-4 py-2 border-b border-fabric-700 text-xs uppercase tracking-wider text-fabric-600 font-display">
        Live Log
      </div>
      <div className="h-40 overflow-y-auto p-3 font-display text-xs leading-relaxed text-fabric-600">
        <AnimatePresence initial={false}>
          {lines.length === 0 ? (
            <div className="text-fabric-700">Waiting for output…</div>
          ) : (
            lines.map((line, i) => (
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
