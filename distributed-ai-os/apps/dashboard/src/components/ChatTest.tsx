import { useState } from "react";
import { motion } from "motion/react";
import { sendChat } from "../api/launcher";

export default function ChatTest() {
  const [input, setInput] = useState("Say hello in one sentence.");
  const [response, setResponse] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSend() {
    if (!input.trim() || loading) return;
    setLoading(true);
    setResponse("");
    try {
      const res = await sendChat(input.trim(), false);
      const data = await res.json();
      const text =
        data.choices?.[0]?.message?.content ??
        data.choices?.[0]?.text ??
        JSON.stringify(data);
      setResponse(text);
    } catch (e) {
      setResponse(e instanceof Error ? e.message : "Chat failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bg-fabric-800/50 border border-fabric-700 rounded-lg p-4">
      <div className="text-xs uppercase tracking-wider text-fabric-600 font-display mb-3">
        Test Chat
      </div>
      <div className="flex gap-2 mb-3">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          className="flex-1 bg-fabric-900 border border-fabric-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent"
          placeholder="Type a message…"
        />
        <motion.button
          whileTap={{ scale: 0.95 }}
          onClick={handleSend}
          disabled={loading}
          className="cursor-pointer px-4 py-2 bg-accent text-fabric-950 font-medium rounded-lg text-sm hover:bg-accent-dim disabled:opacity-40 transition-colors"
        >
          {loading ? "…" : "Send"}
        </motion.button>
      </div>
      {response && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-fabric-900 rounded-lg p-3 text-sm text-fabric-600 leading-relaxed"
        >
          {response}
        </motion.div>
      )}
    </div>
  );
}
