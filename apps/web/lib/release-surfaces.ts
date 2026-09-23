export type DeferredProductSurface = "videoProduction" | "gamingPlayable";

const flagBySurface: Record<DeferredProductSurface, string> = {
  videoProduction: "INCEPT_ENABLE_VIDEO_PRODUCTION",
  gamingPlayable: "INCEPT_ENABLE_GAMING_PLAYABLE",
};

function parseBoolean(value: string | undefined): boolean | undefined {
  const normalized = value?.trim().toLowerCase();
  if (normalized === "true") return true;
  if (normalized === "false") return false;
  return undefined;
}

/**
 * Deferred products remain usable in local development. Production is
 * fail-closed unless a release explicitly enables the corresponding surface.
 */
export function isDeferredProductSurfaceEnabled(surface: DeferredProductSurface): boolean {
  const configured = parseBoolean(process.env[flagBySurface[surface]]);
  return configured ?? process.env.NODE_ENV !== "production";
}
