/**
 * Content-ID → visual recipe. Saves never store paths; only IDs like cat:mizzle:v1.
 */
import manifestJson from "@content/assets/manifest.json";

export interface CatVisual {
  label: string;
  body: string;
  accent: string;
  outline: string;
  eye: string;
  silhouette: string;
  stages: Record<string, { scale: number }>;
}

export interface PlantVisual {
  label: string;
  primary: string;
  accent: string;
  shape: string;
}

export interface AssetManifest {
  version: string;
  styleBible: string;
  pixel: {
    cat: { width: number; height: number; baselineY: number };
    plant: { width: number; height: number };
    sampling: string;
  };
  cats: Record<string, CatVisual>;
  plants: Record<string, PlantVisual>;
}

export const assetManifest = manifestJson as AssetManifest;

export function catVisual(catId: string): CatVisual | undefined {
  return assetManifest.cats[catId];
}

export function plantVisual(plantId: string): PlantVisual | undefined {
  return assetManifest.plants[plantId];
}

/** Stable frame key for cache: content id + stage + kind */
export function frameKey(
  contentId: string,
  stage = "default",
  kind: "idle" | "plant" = "idle",
): string {
  return `${contentId}:${stage}:${kind}`;
}
