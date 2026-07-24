"use client";

import { useState } from "react";
import { RefreshCw, CheckCircle2, XCircle } from "lucide-react";

type State = "idle" | "loading" | "success" | "failed";

export function RefreshDataButton() {
  const [state, setState] = useState<State>("idle");
  const [message, setMessage] = useState("");

  const handleRefresh = async () => {
    if (state === "loading") return;
    setState("loading");
    setMessage("");
    try {
      const res = await fetch("/api/incept/api/v1/supply-smb/refresh-snapshot", {
        method: "POST",
      });
      if (!res.ok) throw new Error(`${res.status}`);
      setState("success");
      setMessage("Cache cleared — reload the page to see fresh data.");
      // Auto-reset after 4 seconds
      setTimeout(() => setState("idle"), 4000);
    } catch (e) {
      setState("failed");
      setMessage(String(e));
      setTimeout(() => setState("idle"), 4000);
    }
  };

  const icon =
    state === "loading" ? (
      <RefreshCw className="size-3.5 animate-spin" />
    ) : state === "success" ? (
      <CheckCircle2 className="size-3.5 text-[#16A34A]" />
    ) : state === "failed" ? (
      <XCircle className="size-3.5 text-destructive" />
    ) : (
      <RefreshCw className="size-3.5" />
    );

  const label =
    state === "loading"
      ? "Refreshing…"
      : state === "success"
        ? "Refreshed"
        : state === "failed"
          ? "Failed"
          : "Refresh Data";

  return (
    <button
      onClick={handleRefresh}
      disabled={state === "loading"}
      title={message || "Clear cache and reload latest BQ data"}
      className="flex items-center gap-1.5 rounded-full border border-border bg-background px-3.5 py-1.5 text-sm font-medium text-foreground shadow-sm transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-60"
    >
      {icon}
      {label}
    </button>
  );
}
