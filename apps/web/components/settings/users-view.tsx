"use client";

import { useState, useTransition } from "react";
import { Trash2, Plus, Users, Building2, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  addUserAction,
  bulkAddUsersAction,
  updateUserAction,
  deleteUserAction,
} from "@/app/actions/admin";
import type { AdminUser, AdminUserListPayload } from "@/lib/api";

// ── Constants ──────────────────────────────────────────────────────────────────

const ROLE_OPTIONS = [
  { value: "moloco_nbs",    label: "Moloco NBS" },
  { value: "moloco_ctv",    label: "Moloco CTV" },
  { value: "moloco_growth", label: "Moloco Growth" },
  { value: "moloco_gtm",    label: "Moloco GTM" },
  { value: "moloco_supply", label: "Moloco Supply" },
  { value: "agency",        label: "Agency" },
] as const;

const AGENCY_COMPANIES = ["Madhouse", "Gatherone", "Bluevision", "Globaloneclick"] as const;

const ROLE_BADGE: Record<string, string> = {
  admin:          "bg-foreground text-white",
  moloco_nbs:     "bg-[#EDF3FF] text-accent",
  moloco_ctv:     "bg-success-soft text-success",
  moloco_growth:  "bg-[#FFF7ED] text-[#C2410C]",
  moloco_gtm:     "bg-[#FDF4FF] text-[#9333EA]",
  moloco_supply:  "bg-[#FEFCE8] text-[#A16207]",
  agency:         "bg-[#FFF1F2] text-[#E11D48]",
  user:           "bg-[#EDF3FF] text-accent",
};

const ROLE_DISPLAY: Record<string, string> = {
  admin:          "Admin",
  moloco_nbs:     "Moloco NBS",
  moloco_ctv:     "Moloco CTV",
  moloco_growth:  "Moloco Growth",
  moloco_gtm:     "Moloco GTM",
  moloco_supply:  "Moloco Supply",
  agency:         "Agency",
  user:           "Moloco NBS",
};

function isAgency(role: string) { return role === "agency"; }

// ── Sub-components ─────────────────────────────────────────────────────────────

function RoleBadge({ role }: { role: string }) {
  return (
    <span className={cn(
      "inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold",
      ROLE_BADGE[role] ?? "bg-gray-100 text-gray-600"
    )}>
      {ROLE_DISPLAY[role] ?? role}
    </span>
  );
}

function RoleSelect({
  value,
  onChange,
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  className?: string;
}) {
  return (
    <div className={cn("relative", className)}>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full appearance-none rounded-xl border border-border bg-card px-3 py-2 pr-8 text-sm text-foreground focus:border-accent focus:outline-none"
      >
        {ROLE_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2.5 top-2.5 size-4 text-black/40" />
    </div>
  );
}

// ── Inline edit row ────────────────────────────────────────────────────────────

function UserRow({
  user,
  currentUserEmail,
  onDeleted,
}: {
  user: AdminUser;
  currentUserEmail: string;
  onDeleted: (email: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [role, setRole] = useState(user.role);
  const [routing, setRouting] = useState(user.routingBucket ?? "");
  const [company, setCompany] = useState(user.agencyCompany ?? "");
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState("");

  const isAdmin = user.role === "admin" || user.email === currentUserEmail;

  function handleSave() {
    startTransition(async () => {
      const res = await updateUserAction(user.email, role, isAgency(role) ? routing : null, isAgency(role) ? company : null);
      if (res.error) { setError(res.error); return; }
      setEditing(false);
      setError("");
    });
  }

  function handleDelete() {
    if (!confirm(`Remove ${user.email}?`)) return;
    startTransition(async () => {
      const res = await deleteUserAction(user.email);
      if (res.error) { setError(res.error); return; }
      onDeleted(user.email);
    });
  }

  return (
    <tr className="border-b border-border last:border-0">
      <td className="py-3 pr-4 text-sm font-medium text-foreground">{user.email}</td>
      <td className="py-3 pr-4">
        {editing ? (
          <RoleSelect value={role} onChange={setRole} className="w-44" />
        ) : (
          <RoleBadge role={user.role} />
        )}
      </td>
      <td className="py-3 pr-4 text-sm text-black/55">
        {editing && isAgency(role) ? (
          <div className="flex gap-2">
            <input
              placeholder="Routing bucket (e.g. Qipeng)"
              value={routing}
              onChange={(e) => setRouting(e.target.value)}
              className="w-36 rounded-xl border border-border bg-card px-3 py-2 text-sm focus:border-accent focus:outline-none"
            />
            <div className="relative">
              <select
                value={company}
                onChange={(e) => setCompany(e.target.value)}
                className="appearance-none rounded-xl border border-border bg-card px-3 py-2 pr-7 text-sm focus:border-accent focus:outline-none"
              >
                <option value="">— Company —</option>
                {AGENCY_COMPANIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2 top-2.5 size-3.5 text-black/40" />
            </div>
          </div>
        ) : (
          <span>
            {user.agencyCompany && <span className="font-medium text-foreground">{user.agencyCompany}</span>}
            {user.agencyCompany && user.routingBucket && <span className="mx-1 text-black/30">·</span>}
            {user.routingBucket && <span>{user.routingBucket}</span>}
          </span>
        )}
      </td>
      <td className="py-3">
        {isAdmin ? (
          <span className="text-xs text-black/30">Protected</span>
        ) : editing ? (
          <div className="flex items-center gap-2">
            <button
              onClick={handleSave}
              disabled={pending}
              className="rounded-lg bg-foreground px-3 py-1.5 text-xs font-medium text-white transition hover:bg-black disabled:opacity-50"
            >
              {pending ? "Saving…" : "Save"}
            </button>
            <button
              onClick={() => { setEditing(false); setError(""); setRole(user.role); }}
              className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-black/60 hover:bg-muted"
            >
              Cancel
            </button>
            {error && <span className="text-xs text-red-500">{error}</span>}
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setEditing(true)}
              className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-black/60 transition hover:bg-muted hover:text-black"
            >
              Edit
            </button>
            <button
              onClick={handleDelete}
              disabled={pending}
              className="rounded-lg p-1.5 text-black/30 transition hover:bg-[#FFF1F2] hover:text-red-500 disabled:opacity-50"
              title="Remove user"
            >
              <Trash2 className="size-3.5" />
            </button>
          </div>
        )}
      </td>
    </tr>
  );
}

// ── Add Users panel ────────────────────────────────────────────────────────────

function AddUsersPanel({ onAdded }: { onAdded: (users: AdminUser[]) => void }) {
  const [emails, setEmails] = useState("");
  const [role, setRole] = useState("moloco_nbs");
  const [routing, setRouting] = useState("");
  const [company, setCompany] = useState("");
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  const emailList = emails
    .split(/[\n,;]+/)
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);

  function handleAdd() {
    if (emailList.length === 0) { setError("Enter at least one email."); return; }
    setError(""); setSuccessMsg("");

    startTransition(async () => {
      const res = emailList.length === 1
        ? await addUserAction(emailList[0], role, isAgency(role) ? routing : null, isAgency(role) ? company : null)
        : await bulkAddUsersAction(emailList, role, isAgency(role) ? routing : null, isAgency(role) ? company : null);

      if (res.error) { setError(res.error); return; }

      const added: AdminUser[] = emailList.map((email) => ({
        email,
        role,
        routingBucket: isAgency(role) ? routing || null : null,
        agencyCompany: isAgency(role) ? company || null : null,
      }));
      onAdded(added);
      setEmails("");
      setSuccessMsg(`${emailList.length} user${emailList.length > 1 ? "s" : ""} added.`);
    });
  }

  return (
    <div className="rounded-2xl border border-border bg-muted p-6">
      <div className="mb-4 flex items-center gap-2">
        <Plus className="size-4 text-accent" />
        <h2 className="text-sm font-semibold text-foreground">Add Users</h2>
        <span className="text-xs text-black/40">Paste one or more emails (comma / newline separated)</span>
      </div>

      <div className="grid grid-cols-[1fr_auto] gap-4">
        {/* Emails textarea */}
        <textarea
          value={emails}
          onChange={(e) => setEmails(e.target.value)}
          placeholder={"alice@moloco.com\nbob@moloco.com\ncontact@agency.com"}
          rows={4}
          className="w-full rounded-xl border border-border bg-card px-3 py-2.5 font-mono text-xs text-foreground focus:border-accent focus:outline-none"
        />

        {/* Right-side config */}
        <div className="flex w-56 flex-col gap-3">
          <div>
            <label className="mb-1 block text-[11px] font-medium text-black/50">Role</label>
            <RoleSelect value={role} onChange={(v) => { setRole(v); setRouting(""); setCompany(""); }} />
          </div>

          {isAgency(role) && (
            <>
              <div>
                <label className="mb-1 block text-[11px] font-medium text-black/50">Agency Company</label>
                <div className="relative">
                  <select
                    value={company}
                    onChange={(e) => setCompany(e.target.value)}
                    className="w-full appearance-none rounded-xl border border-border bg-card px-3 py-2 pr-8 text-sm focus:border-accent focus:outline-none"
                  >
                    <option value="">— Select —</option>
                    {AGENCY_COMPANIES.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-2.5 top-2.5 size-4 text-black/40" />
                </div>
              </div>
              <div>
                <label className="mb-1 block text-[11px] font-medium text-black/50">Routing Bucket</label>
                <input
                  placeholder="e.g. Qipeng"
                  value={routing}
                  onChange={(e) => setRouting(e.target.value)}
                  className="w-full rounded-xl border border-border bg-card px-3 py-2 text-sm focus:border-accent focus:outline-none"
                />
              </div>
            </>
          )}

          <button
            onClick={handleAdd}
            disabled={pending || emailList.length === 0}
            className="mt-auto flex items-center justify-center gap-2 rounded-xl bg-foreground px-4 py-2.5 text-sm font-medium text-white transition hover:bg-black disabled:opacity-40"
          >
            {pending ? "Adding…" : (
              <>
                <Plus className="size-4" />
                Add {emailList.length > 1 ? `${emailList.length} Users` : "User"}
              </>
            )}
          </button>
        </div>
      </div>

      {error && <p className="mt-3 text-sm text-red-500">{error}</p>}
      {successMsg && <p className="mt-3 text-sm text-success">{successMsg}</p>}
    </div>
  );
}

// ── Main view ──────────────────────────────────────────────────────────────────

export function UsersView({
  initialData,
  currentUserEmail,
}: {
  initialData: AdminUserListPayload;
  currentUserEmail: string;
}) {
  const [users, setUsers] = useState<AdminUser[]>(initialData.users);
  const [search, setSearch] = useState("");

  const filtered = users.filter((u) =>
    u.email.toLowerCase().includes(search.toLowerCase()) ||
    (u.agencyCompany ?? "").toLowerCase().includes(search.toLowerCase())
  );

  function handleDeleted(email: string) {
    setUsers((prev) => prev.filter((u) => u.email !== email));
  }

  function handleAdded(newUsers: AdminUser[]) {
    setUsers((prev) => {
      const existingEmails = new Set(prev.map((u) => u.email));
      const toAdd = newUsers.filter((u) => !existingEmails.has(u.email));
      return [...prev, ...toAdd];
    });
  }

  // Group by role category
  const molocoUsers = filtered.filter((u) => u.role !== "agency" && u.role !== "admin");
  const agencyUsers = filtered.filter((u) => u.role === "agency");
  const adminUsers  = filtered.filter((u) => u.role === "admin");

  return (
    <div className="flex flex-col gap-6">
      {/* Add panel */}
      <AddUsersPanel onAdded={handleAdded} />

      {/* Search + stats */}
      <div className="flex items-center justify-between gap-4">
        <input
          placeholder="Search by email or agency…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-72 rounded-xl border border-border bg-card px-3.5 py-2 text-sm focus:border-accent focus:outline-none"
        />
        <div className="flex items-center gap-4 text-sm text-black/50">
          <span className="flex items-center gap-1.5">
            <Users className="size-3.5" />
            {users.length} total
          </span>
          <span className="flex items-center gap-1.5">
            <Building2 className="size-3.5" />
            {agencyUsers.length} agencies
          </span>
        </div>
      </div>

      {/* User table */}
      <div className="rounded-2xl border border-border bg-card overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border bg-muted">
              <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-black/40">Email</th>
              <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-black/40">Role</th>
              <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-black/40">Agency / Routing</th>
              <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-black/40">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {adminUsers.length > 0 && (
              <>
                <tr><td colSpan={4} className="px-4 pb-1 pt-4 text-[10px] font-semibold uppercase tracking-widest text-black/30">Admin</td></tr>
                {adminUsers.map((u) => (
                  <UserRow key={u.email} user={u} currentUserEmail={currentUserEmail} onDeleted={handleDeleted} />
                ))}
              </>
            )}
            {molocoUsers.length > 0 && (
              <>
                <tr><td colSpan={4} className="px-4 pb-1 pt-4 text-[10px] font-semibold uppercase tracking-widest text-black/30">Moloco Team</td></tr>
                {molocoUsers.map((u) => (
                  <UserRow key={u.email} user={u} currentUserEmail={currentUserEmail} onDeleted={handleDeleted} />
                ))}
              </>
            )}
            {agencyUsers.length > 0 && (
              <>
                <tr><td colSpan={4} className="px-4 pb-1 pt-4 text-[10px] font-semibold uppercase tracking-widest text-black/30">Agencies</td></tr>
                {agencyUsers.map((u) => (
                  <UserRow key={u.email} user={u} currentUserEmail={currentUserEmail} onDeleted={handleDeleted} />
                ))}
              </>
            )}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={4} className="py-12 text-center text-sm text-black/40">
                  {search ? "No users match your search." : "No users yet. Add some above."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
