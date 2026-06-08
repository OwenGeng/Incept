"use server";

import { auth } from "@/auth";
import { addAdminUser, bulkAddAdminUsers, updateAdminUser, deleteAdminUser } from "@/lib/api";

type ActionResult = { error?: string; ok?: boolean };

async function getAdminSession() {
  const session = await auth();
  if (session?.user?.role !== "admin") return null;
  return session.user;
}

export async function addUserAction(
  email: string,
  role: string,
  routingBucket?: string | null,
  agencyCompany?: string | null,
): Promise<ActionResult> {
  const user = await getAdminSession();
  if (!user) return { error: "Unauthorized" };
  try {
    await addAdminUser({ email, role, routingBucket: routingBucket ?? undefined, agencyCompany: agencyCompany ?? undefined }, user);
    return { ok: true };
  } catch (e) {
    return { error: (e as Error).message ?? "Failed to add user" };
  }
}

export async function bulkAddUsersAction(
  emails: string[],
  role: string,
  routingBucket?: string | null,
  agencyCompany?: string | null,
): Promise<ActionResult> {
  const user = await getAdminSession();
  if (!user) return { error: "Unauthorized" };
  try {
    await bulkAddAdminUsers({ emails, role, routingBucket: routingBucket ?? undefined, agencyCompany: agencyCompany ?? undefined }, user);
    return { ok: true };
  } catch (e) {
    return { error: (e as Error).message ?? "Failed to add users" };
  }
}

export async function updateUserAction(
  email: string,
  role: string,
  routingBucket?: string | null,
  agencyCompany?: string | null,
): Promise<ActionResult> {
  const user = await getAdminSession();
  if (!user) return { error: "Unauthorized" };
  try {
    await updateAdminUser(email, { role, routingBucket, agencyCompany }, user);
    return { ok: true };
  } catch (e) {
    return { error: (e as Error).message ?? "Failed to update user" };
  }
}

export async function deleteUserAction(email: string): Promise<ActionResult> {
  const user = await getAdminSession();
  if (!user) return { error: "Unauthorized" };
  try {
    await deleteAdminUser(email, user);
    return { ok: true };
  } catch (e) {
    return { error: (e as Error).message ?? "Failed to delete user" };
  }
}
