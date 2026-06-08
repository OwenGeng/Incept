"use client";

import { SessionProvider } from "next-auth/react";

/**
 * Thin client-side wrapper so we can use `SessionProvider` from a
 * server component layout without making the whole layout "use client".
 */
export function AuthSessionProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  return <SessionProvider>{children}</SessionProvider>;
}
