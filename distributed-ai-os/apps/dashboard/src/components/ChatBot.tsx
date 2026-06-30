import { useCallback, useEffect, useRef, useState } from "react";
import {
  AnimatePresence,
  motion,
  useReducedMotion,
} from "motion/react";
import { sendChat } from "../api/launcher";
import type { ChatMessage } from "../types";

function parseSseChunk(
  chunk: string,
): { content?: string; done?: boolean; error?: string } {
  const lines = chunk.split("\n");
  let content = "";
  for (const line of lines) {
    if (!line.startsWith("data: ")) continue;
    const payload = line.slice(6).trim();
    if (payload === "[DONE]") return { done: true };
    try {
      const data = JSON.parse(payload) as {
        choices?: Array<{ delta?: { content?: string }; message?: { content?: string } }>;
        error?: { message?: string };
      };
      if (data.error?.message) return { error: data.error.message };
      const delta =
        data.choices?.[0]?.delta?.content ??
        data.choices?.[0]?.message?.content;
      if (delta) content += delta;
    } catch {
      /* ignore malformed SSE lines */
    }
  }
  return content ? { content } : {};
}

export default function ChatBot() {
  const reduced = useReducedMotion();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: reduced ? "auto" : "smooth",
    });
  }, [messages, loading, reduced]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: ChatMessage = { role: "user", content: text };
    const history = [...messages, userMsg];
    setMessages(history);
    setInput("");
    setError(null);
    setLoading(true);

    try {
      const res = await sendChat(history, true);
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const err =
          data.detail ??
          data.error?.message ??
          (typeof data.error === "string" ? data.error : null) ??
          `Chat failed (HTTP ${res.status})`;
        setError(typeof err === "string" ? err : JSON.stringify(err));
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) {
        setError("Streaming not supported by the server");
        return;
      }

      const decoder = new TextDecoder();
      let assistantText = "";
      setMessages([...history, { role: "assistant", content: "" }]);

      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";

        for (const part of parts) {
          const parsed = parseSseChunk(part);
          if (parsed.error) {
            setError(parsed.error);
            return;
          }
          if (parsed.content) {
            assistantText += parsed.content;
            setMessages([
              ...history,
              { role: "assistant", content: assistantText },
            ]);
          }
        }
      }

      if (!assistantText) {
        const fallback = await sendChat(history, false);
        const data = await fallback.json();
        if (!fallback.ok) {
          const err =
            data.detail ??
            data.error?.message ??
            `Chat failed (HTTP ${fallback.status})`;
          setError(typeof err === "string" ? err : JSON.stringify(err));
          return;
        }
        const content =
          data.choices?.[0]?.message?.content ??
          data.choices?.[0]?.text ??
          "";
        setMessages([...history, { role: "assistant", content }]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Chat failed");
    } finally {
      setLoading(false);
      textareaRef.current?.focus();
    }
  }, [input, loading, messages]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function handleClear() {
    setMessages([]);
    setError(null);
    textareaRef.current?.focus();
  }

  return (
    <div className="flex flex-col h-[min(72dvh,640px)] bg-fabric-800/50 border border-fabric-700 rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-fabric-700">
        <div>
          <h3 className="font-display text-sm tracking-wider text-accent">
            AI Chat
          </h3>
          <p className="text-xs text-fabric-600 mt-0.5">
            Full model context — prompt and reply share the model window
          </p>
        </div>
        {messages.length > 0 && (
          <motion.button
            whileTap={{ scale: 0.95 }}
            type="button"
            onClick={handleClear}
            disabled={loading}
            className="cursor-pointer px-3 py-1.5 text-xs border border-fabric-700 rounded-md text-fabric-600 hover:text-white/80 hover:border-fabric-600 disabled:opacity-40 transition-colors min-h-[44px]"
          >
            Clear
          </motion.button>
        )}
      </div>

      <div
        ref={scrollRef}
        role="log"
        aria-live="polite"
        aria-label="Chat messages"
        className="flex-1 overflow-y-auto p-4 space-y-3"
      >
        {messages.length === 0 && !error && (
          <div className="h-full flex flex-col items-center justify-center text-center px-6">
            <p className="text-sm text-fabric-600 max-w-sm leading-relaxed">
              Ask anything. Responses stream from your distributed cluster with
              no artificial length limit.
            </p>
            <p className="text-xs text-fabric-700 mt-3">
              Enter to send · Shift+Enter for newline
            </p>
          </div>
        )}

        <AnimatePresence initial={false}>
          {messages.map((msg, i) => (
            <motion.div
              key={`${i}-${msg.role}`}
              initial={reduced ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-lg px-3 py-2 text-sm leading-relaxed ${
                  msg.role === "user"
                    ? "bg-accent/15 border border-accent/25 text-white/95"
                    : "bg-fabric-900 border border-fabric-700 text-white/90"
                }`}
              >
                {msg.content || (
                  <span className="text-fabric-600 animate-pulse">…</span>
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {error && (
          <motion.div
            role="alert"
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            className="px-3 py-2 bg-danger/10 border border-danger/30 rounded-lg text-danger text-sm"
          >
            {error}
          </motion.div>
        )}
      </div>

      <div className="border-t border-fabric-700 p-4">
        <label htmlFor="chat-input" className="sr-only">
          Message
        </label>
        <div className="flex gap-2 items-end">
          <textarea
            id="chat-input"
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
            rows={2}
            placeholder="Type a message…"
            className="flex-1 resize-none bg-fabric-900 border border-fabric-700 rounded-lg px-3 py-2.5 text-sm leading-relaxed focus:outline-none focus:border-accent disabled:opacity-50 min-h-[44px]"
          />
          <motion.button
            whileTap={{ scale: 0.95 }}
            type="button"
            onClick={handleSend}
            disabled={loading || !input.trim()}
            aria-label={loading ? "Sending message" : "Send message"}
            className="cursor-pointer shrink-0 px-5 py-2.5 bg-accent text-fabric-950 font-medium rounded-lg text-sm hover:bg-accent-dim disabled:opacity-40 transition-colors min-h-[44px] min-w-[44px]"
          >
            {loading ? "…" : "Send"}
          </motion.button>
        </div>
      </div>
    </div>
  );
}
