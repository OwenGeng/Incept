"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";

export function FeedbackButton() {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handle(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [open]);

  async function handleSubmit() {
    if (!text.trim() || submitting) return;
    setSubmitting(true);
    try {
      await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: text.trim() }),
      });
    } catch {
      // silent
    }
    setDone(true);
    setText("");
    setSubmitting(false);
    setTimeout(() => {
      setDone(false);
      setOpen(false);
    }, 2000);
  }

  return (
    <div className="relative" ref={wrapperRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="rounded-full border border-border px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted"
      >
        Feedback
      </button>

      {open && (
        <div className="absolute right-0 top-[calc(100%+8px)] z-50 w-80 overflow-hidden rounded-2xl border border-border bg-card shadow-xl">
          {done ? (
            <div className="flex h-32 items-center justify-center text-sm font-medium text-success">
              Thanks for your feedback 🙏
            </div>
          ) : (
            <>
              <div className="p-4 pb-3">
                <textarea
                  autoFocus
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && e.metaKey) void handleSubmit();
                  }}
                  placeholder="Type your feedback here…"
                  rows={4}
                  className="w-full resize-none rounded-xl border border-border bg-background p-3 text-sm leading-6 outline-none placeholder:text-muted-foreground focus:border-accent"
                />
              </div>
              <div className="flex items-end justify-between border-t border-border px-4 pb-4 pt-3">
                <p className="max-w-[170px] text-xs leading-4 text-muted-foreground">
                  We don&apos;t respond to submissions, but we read all of them carefully
                </p>
                <Button size="sm" onClick={() => void handleSubmit()} disabled={!text.trim() || submitting}>
                  {submitting ? "Sending…" : "Submit"}
                </Button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

export function DocsButton({ href = "/docs" }: { href?: string }) {
  return (
    <a
      href={href}
      className="rounded-full border border-border px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted"
    >
      Docs
    </a>
  );
}
