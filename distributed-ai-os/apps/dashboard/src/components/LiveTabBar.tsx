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
      className="flex gap-8 border-b border-hairline mb-8"
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
            className={`relative cursor-pointer pb-3 min-h-[44px] label-caps text-[13px] transition-colors ${
              selected ? "text-on-dark" : "text-muted hover:text-on-dark"
            }`}
          >
            {tab.label}
            {selected && (
              <motion.span
                layoutId="live-tab-indicator"
                className="absolute left-0 right-0 -bottom-px h-0.5 bg-on-dark"
                transition={{ type: "spring", stiffness: 400, damping: 30 }}
              />
            )}
          </button>
        );
      })}
    </div>
  );
}
