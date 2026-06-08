"use server";

import { auth } from "@/auth";
import { createLead, updateLeadStatus } from "@/lib/api";

export async function createLeadAction(formData: FormData) {
  const session = await auth();
  const companyName = formData.get("companyName") as string;
  const listSource = formData.get("listSource") as string;
  const teamRouting = formData.get("teamRouting") as string;
  const sentToTeam = formData.get("sentToTeam") as string;
  const notes = (formData.get("notes") as string) ?? "";
  const activatedBy = session?.user?.email ?? "unknown";

  if (!companyName || !listSource || !sentToTeam) {
    return { error: "Missing required fields" };
  }

  try {
    const result = await createLead(
      { companyName, listSource, teamRouting, sentToTeam, notes, activatedBy },
      session?.user ?? undefined,
    );
    return { success: true, lead: result };
  } catch (err) {
    return { error: String(err) };
  }
}

export async function updateLeadStatusAction(
  leadId: string,
  status: "sent" | "opened" | "spending",
  notes = "",
) {
  const session = await auth();
  try {
    await updateLeadStatus(leadId, status, notes, session?.user ?? undefined);
    return { success: true };
  } catch (err) {
    return { error: String(err) };
  }
}
