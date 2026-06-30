import { motion } from "motion/react";
import type { LiveTab } from "../types";

interface Tab {
  id: LiveTab;
  label: string;
}

interface Props {
  tabs: Tab[];
  active: LiveTab;
  onChange: (tab: LiveTab) => void;
}

export default function LiveTabBar({ tabs, active, onChange }: Props) {
  return (
    <div
      role="tablist"
      aria-label="Live dashboard sections"
      className="flex gap-1 p-1 bg-fabric-900/80 border border-fabric-700 rounded-lg mb-6"
    >
      {tabs.map((tab) => {
        const selected = tab.id === active;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(tab.id)}
            className={`relative flex-1 cursor-pointer px-4 py-2.5 text-sm font-medium rounded-md transition-colors min-h-[44px] ${
              selected
                ? "text-fabric-950"
                : "text-fabric-600 hover:text-white/80"
            }`}
          >
            {selected && (
              <motion.span
                layoutId="live-tab-indicator"
                className="absolute inset-0 bg-accent rounded-md"
                transition={{ type: "spring", stiffness: 400, damping: 30 }}
              />
            )}
            <span className="relative z-10 font-display tracking-wide">
              {tab.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}
