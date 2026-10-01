"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { removeBackground, resolveAssetUrl, waitForJobOutputs } from "@/lib/incept-api";

type SourceAsset = { id: string; url: string };

/**
 * Object images for the Kakao Object template, keyed by source asset id.
 * Either uploaded as a transparent PNG or produced by the existing
 * remove-background workflow; sources without an entry fall back to their own
 * url (useful when the source is already a transparent PNG).
 */
export function useKakaoObjectImages(workspaceId: string, threadId?: string) {
  const [objectUrls, setObjectUrls] = useState<Record<string, string>>({});
  const [removing, setRemoving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const blobUrls = useRef<string[]>([]);

  useEffect(() => () => blobUrls.current.forEach((url) => URL.revokeObjectURL(url)), []);

  const objectUrlFor = useCallback((asset: SourceAsset) => objectUrls[asset.id] ?? asset.url, [objectUrls]);

  const uploadObject = useCallback((assetId: string, file: File) => {
    const url = URL.createObjectURL(file);
    blobUrls.current.push(url);
    setObjectUrls((prev) => ({ ...prev, [assetId]: url }));
    setError(null);
  }, []);

  const removeBackgrounds = useCallback(
    async (assets: SourceAsset[]) => {
      setRemoving(true);
      setError(null);
      try {
        const results = await Promise.all(
          assets.map(async (asset) => {
            const job = await removeBackground({ workspaceId, assetId: asset.id, threadId });
            const [outputId] = await waitForJobOutputs(job.job_id);
            if (!outputId) throw new Error(`Background removal returned no image for ${asset.id}`);
            return [asset.id, resolveAssetUrl(`/assets/${outputId}/content`)] as const;
          }),
        );
        setObjectUrls((prev) => ({ ...prev, ...Object.fromEntries(results) }));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Background removal failed.");
      } finally {
        setRemoving(false);
      }
    },
    [workspaceId, threadId],
  );

  const reset = useCallback(() => {
    setObjectUrls({});
    setError(null);
  }, []);

  return { objectUrls, objectUrlFor, uploadObject, removeBackgrounds, removing, error, reset };
}
