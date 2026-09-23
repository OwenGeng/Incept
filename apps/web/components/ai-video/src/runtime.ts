/** Browser configuration for the integrated Next.js AI Video application. */
export const aiVideoApiBase = process.env.NEXT_PUBLIC_AI_VIDEO_API_BASE_URL ?? "/api/ai-video";

/** Local-only fixture mode. It is never enabled by a production deployment. */
export const isAiVideoMockEnabled = process.env.NEXT_PUBLIC_AI_VIDEO_USE_MOCK === "true";
