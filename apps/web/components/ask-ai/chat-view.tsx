"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Bot, Sparkles, TrendingUp, Square } from "lucide-react";
import { cn } from "@/lib/utils";

interface Message {
  role: "user" | "assistant";
  content: string;
}

const STARTER_QUESTIONS: Record<string, string[]> = {
  "no-sdk-no-ua": [
    "Which P1 companies haven't been contacted yet?",
    "Show me the team routing distribution",
    "Which P1 companies have Moloco supply visibility?",
    "How many apps haven't been updated in over a year?",
  ],
  "sdk-no-ua": [
    "How many apps are marked Eligible vs Ineligible?",
    "Which companies have the highest SDK revenue this month?",
    "Show companies with no SDK Growth Manager assigned",
    "Which apps have the most untapped UA potential?",
  ],
  "ua-no-sdk": [
    "Which companies have the highest existing UA spend?",
    "Show companies with multiple apps but no SDK integration",
    "Which companies already have some SDK apps? Show their untapped count.",
    "Give me a summary of the ua-no-sdk dataset",
  ],
  ctv: [
    "What CTV inventory trends should I watch?",
    "How does CTV-to-web conversion compare to industry benchmarks?",
  ],
  studio: [
    "What creative formats are performing best?",
    "Suggest optimization for my current campaigns.",
  ],
};

function EmptyState({ module, dataset, onSelect }: { module: string; dataset: string; onSelect: (q: string) => void }) {
  const starters = STARTER_QUESTIONS[dataset] ?? STARTER_QUESTIONS[module] ?? [];
  return (
    <div className="flex flex-col items-center justify-center gap-6 py-12 text-center">
      <div className="flex size-14 items-center justify-center rounded-2xl bg-soft-accent">
        <Sparkles className="size-7 text-accent" />
      </div>
      <div>
        <p className="text-base font-semibold text-foreground">Linglong Analysis Assistant</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Ask anything about your data — I can filter, compare,<br />
          and surface patterns to help you prioritize actions.
        </p>
      </div>
      {starters.length > 0 && (
        <div className="flex w-full max-w-lg flex-col gap-2">
          {starters.map((q) => (
            <button
              key={q}
              onClick={() => onSelect(q)}
              className="flex items-center gap-2.5 rounded-xl border border-border bg-card px-4 py-2.5 text-left text-sm text-muted-foreground transition hover:border-accent hover:text-foreground"
            >
              <TrendingUp className="size-3.5 shrink-0 text-accent" />
              {q}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  return (
    <div className={cn("flex gap-3", isUser && "flex-row-reverse")}>
      {!isUser && (
        <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-soft-accent">
          <Bot className="size-3.5 text-accent" />
        </div>
      )}
      <div
        className={cn(
          "max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap",
          isUser
            ? "bg-accent text-white rounded-tr-sm"
            : "bg-card border border-border text-foreground rounded-tl-sm",
        )}
      >
        {msg.content}
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex gap-3">
      <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-soft-accent">
        <Bot className="size-3.5 text-accent" />
      </div>
      <div className="flex items-center gap-1 rounded-2xl rounded-tl-sm border border-border bg-card px-4 py-3">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="size-1.5 rounded-full bg-muted-foreground animate-bounce"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </div>
    </div>
  );
}

export function ChatView({ module, dataset = "no-sdk-no-ua" }: { module: "supply" | "ctv" | "studio"; dataset?: string }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  // Track IME composition so we don't fire Enter mid-composition
  const composingRef = useRef(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  function handleSelect(q: string) {
    setInput(q);
    inputRef.current?.focus();
  }

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    setInput("");
    const newMessages: Message[] = [...messages, { role: "user", content: text }];
    setMessages(newMessages);
    setLoading(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch("/api/agent/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, module, dataset, history: messages }),
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json() as { reply: string };
      setMessages([...newMessages, { role: "assistant", content: data.reply }]);
    } catch (err) {
      if ((err as Error).name === "AbortError") {
        // User stopped — don't show error, just remove loading
      } else {
        setMessages([...newMessages, {
          role: "assistant",
          content: "Sorry, I encountered an error. Please try again.",
        }]);
      }
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  }, [input, loading, messages, module]);

  function handleStop() {
    abortRef.current?.abort();
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      // Block Enter if IME is composing (Chinese/Japanese/Korean input)
      if (composingRef.current) return;
      e.preventDefault();
      sendMessage();
    }
  }

  return (
    <div className="flex h-full flex-col">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {messages.length === 0 ? (
          <EmptyState module={module} dataset={dataset} onSelect={handleSelect} />
        ) : (
          <div className="space-y-4 pb-2">
            {messages.map((msg, i) => (
              <MessageBubble key={i} msg={msg} />
            ))}
            {loading && <TypingIndicator />}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Input bar */}
      <div className="shrink-0 border-t border-border bg-background px-6 py-4">
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onCompositionStart={() => { composingRef.current = true; }}
            onCompositionEnd={() => { composingRef.current = false; }}
            placeholder="Ask about your data… (Enter to send, Shift+Enter for newline)"
            rows={1}
            disabled={loading}
            className="flex-1 resize-none rounded-xl border border-border bg-card px-4 py-2.5 text-sm outline-none transition focus:border-accent placeholder:text-muted-foreground disabled:opacity-50"
            style={{ maxHeight: "120px", overflowY: "auto" }}
          />

          {loading ? (
            <button
              onClick={handleStop}
              title="Stop generating"
              className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-border bg-card text-muted-foreground transition hover:border-red-300 hover:bg-red-50 hover:text-red-500"
            >
              <Square className="size-4 fill-current" />
            </button>
          ) : (
            <button
              onClick={sendMessage}
              disabled={!input.trim()}
              title="Send message"
              className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-accent text-white transition hover:opacity-90 disabled:opacity-40"
            >
              <Send className="size-4" />
            </button>
          )}
        </div>
        <p className="mt-2 text-[11px] text-muted-foreground">
          Powered by Gemini · Answers are based on live data
        </p>
      </div>
    </div>
  );
}
