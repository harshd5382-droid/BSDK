import { useEffect, useRef, useState } from "react";
import { subscribeLogs } from "../api/launcher";

const MAX_LINES = 200;

export function useLogs(enabled: boolean) {
  const [lines, setLines] = useState<string[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!enabled) return;
    const unsub = subscribeLogs((line) => {
      setLines((prev) => [...prev.slice(-(MAX_LINES - 1)), line]);
    });
    return unsub;
  }, [enabled]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines]);

  return { lines, bottomRef, clear: () => setLines([]) };
}
