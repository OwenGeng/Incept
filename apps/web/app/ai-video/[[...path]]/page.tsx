"use client";

import dynamic from "next/dynamic";

// The preserved workflow uses BrowserRouter, which intentionally reads browser
// history. Keep that client-only boundary explicit instead of evaluating it
// during Next's server render.
const AiVideoApp = dynamic(
  () => import("@/components/ai-video/src/AiVideoApp").then((module) => module.AiVideoApp),
  { ssr: false },
);

/**
 * AI Video intentionally owns its nested client-side workflow routes. Next
 * resolves every `/ai-video/*` URL first, then React Router preserves the
 * legacy Jellyfish route tree during the React 19 migration.
 */
export default function AiVideoPage() {
  return <AiVideoApp />;
}
