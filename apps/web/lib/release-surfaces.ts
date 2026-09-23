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
 * Deferred products are fail-closed in every environment. A release must
 * explicitly enable the corresponding surface, including local development.
 */
export function isDeferredProductSurfaceEnabled(surface: DeferredProductSurface): boolean {
  const configured = parseBoolean(process.env[flagBySurface[surface]]);
  return configured ?? false;
}
