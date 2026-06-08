"use client";

import { useRef, useState, useTransition } from "react";
import { Send, X } from "lucide-react";
import { createLeadAction } from "@/app/actions/leads";

type Props = {
  companyName: string;
  teamRouting: string;
  listSource: string;
};

const SEND_TO_OPTIONS = [
  "Qipeng Team",
  "Jiuye Agency",
  "Internal NBS",
  "Agency Partner A",
  "Agency Partner B",
  "Other",
];

export function LeadModal({ companyName, teamRouting, listSource }: Props) {
  const [open, setOpen] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const dialogRef = useRef<HTMLDialogElement>(null);

  function openModal() {
    setDone(false);
    setError(null);
    setOpen(true);
    dialogRef.current?.showModal();
  }

  function closeModal() {
    setOpen(false);
    dialogRef.current?.close();
  }

  function handleSubmit(formData: FormData) {
    formData.set("companyName", companyName);
    formData.set("teamRouting", teamRouting);
    formData.set("listSource", listSource);
    startTransition(async () => {
      const result = await createLeadAction(formData);
      if ("error" in result && result.error) {
        setError(result.error);
      } else {
        setDone(true);
        setTimeout(closeModal, 1200);
      }
    });
  }

  return (
    <>
      <button
        onClick={openModal}
        title="Mark as Contacted"
        className="inline-flex items-center gap-1.5 rounded-lg border border-[#DBEAFE] bg-[#EFF6FF] px-2.5 py-1 text-[11px] font-semibold text-accent transition hover:bg-[#DBEAFE]"
      >
        <Send className="size-3" />
        Send
      </button>

      {/* Native <dialog> — no extra dependency */}
      <dialog
        ref={dialogRef}
        className="m-auto w-full max-w-md rounded-[24px] border border-border p-0 shadow-2xl backdrop:bg-black/40"
        onClose={() => setOpen(false)}
      >
        <div className="p-6">
          <div className="mb-5 flex items-start justify-between gap-3">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                Mark as Contacted
              </div>
              <div className="mt-1 text-base font-semibold text-foreground">{companyName}</div>
              <div className="mt-0.5 text-sm text-muted-foreground">{teamRouting} · {listSource}</div>
            </div>
            <button
              onClick={closeModal}
              className="rounded-xl p-1.5 text-muted-foreground hover:bg-muted"
            >
              <X className="size-4" />
            </button>
          </div>

          {done ? (
            <div className="rounded-2xl bg-[#EDFDF3] py-4 text-center text-sm font-medium text-[#16A34A]">
              ✓ Lead recorded successfully
            </div>
          ) : (
            <form action={handleSubmit} className="space-y-4">
              <label className="flex flex-col gap-1.5">
                <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  Send to Team / Agency *
                </span>
                <select
                  name="sentToTeam"
                  required
                  className="h-10 rounded-xl border border-border bg-card px-3 text-sm text-foreground outline-none focus:border-[#DBEAFE] focus:ring-2 focus:ring-[#EFF6FF]"
                >
                  <option value="">Select…</option>
                  {SEND_TO_OPTIONS.map((opt) => (
                    <option key={opt} value={opt}>{opt}</option>
                  ))}
                </select>
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  Notes (optional)
                </span>
                <textarea
                  name="notes"
                  rows={3}
                  placeholder="Context, next steps, contact person…"
                  className="resize-none rounded-xl border border-border bg-card px-3 py-2 text-sm text-foreground outline-none focus:border-[#DBEAFE] focus:ring-2 focus:ring-[#EFF6FF]"
                />
              </label>

              {error && (
                <div className="rounded-xl bg-danger-soft px-3 py-2 text-sm text-destructive">
                  {error}
                </div>
              )}

              <div className="flex gap-3 pt-1">
                <button
                  type="submit"
                  disabled={isPending}
                  className="flex-1 rounded-xl bg-accent py-2.5 text-sm font-semibold text-white transition hover:bg-accent/90 disabled:opacity-60"
                >
                  {isPending ? "Saving…" : "Confirm Send"}
                </button>
                <button
                  type="button"
                  onClick={closeModal}
                  className="rounded-xl border border-border bg-muted px-4 py-2.5 text-sm font-semibold text-foreground transition hover:bg-muted"
                >
                  Cancel
                </button>
              </div>
            </form>
          )}
        </div>
      </dialog>
    </>
  );
}
