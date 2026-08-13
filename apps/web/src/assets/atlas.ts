/**
 * Runtime placeholder atlas: content-ID → Pixi Texture (nearest sampling).
 * When real atlases ship under public/assets/, loaders can swap here without
 * touching saves (IDs stay stable).
 */
import { Assets, Texture } from "pixi.js";
import {
  assetManifest,
  catVisual,
  frameKey,
  plantVisual,
} from "./manifest";
import { drawCatPlaceholder, drawPlantPlaceholder } from "./placeholder-draw";

const textureCache = new Map<string, Texture>();
const realCatFrames: Record<string, string> = {
  [frameKey("cat:mizzle:v1", "kitten", "idle")]: "/assets/cats/mizzle-idle-right.png",
  [frameKey("cat:mizzle:v1", "raincoat", "idle")]: "/assets/cats/mizzle-idle-right.png",
};

function canvasToNearestTexture(canvas: HTMLCanvasElement): Texture {
  const texture = Texture.from(canvas);
  // Pixi v8: nearest for pixel art
  const src = texture.source;
  if (src) {
    src.scaleMode = "nearest";
    // prevent bleeding
    src.addressMode = "clamp-to-edge";
  }
  return texture;
}

export function getCatTexture(catId: string, stage = "kitten"): Texture | null {
  const visual = catVisual(catId);
  if (!visual) return null;
  const key = frameKey(catId, stage, "idle");
  let tex = textureCache.get(key);
  if (tex) return tex;
  const scale = visual.stages[stage]?.scale ?? visual.stages.kitten?.scale ?? 1;
  const canvas = drawCatPlaceholder(visual, scale);
  tex = canvasToNearestTexture(canvas);
  textureCache.set(key, tex);
  return tex;
}

export function getPlantTexture(plantId: string): Texture | null {
  const visual = plantVisual(plantId);
  if (!visual) return null;
  const key = frameKey(plantId, "default", "plant");
  let tex = textureCache.get(key);
  if (tex) return tex;
  const canvas = drawPlantPlaceholder(visual);
  tex = canvasToNearestTexture(canvas);
  textureCache.set(key, tex);
  return tex;
}

export function preloadAllPlaceholders(): void {
  for (const [id, visual] of Object.entries(assetManifest.cats)) {
    const stages = Object.keys(visual.stages);
    for (const st of stages.length ? stages : ["kitten"]) {
      getCatTexture(id, st);
    }
  }
  for (const id of Object.keys(assetManifest.plants)) {
    getPlantTexture(id);
  }
}

export async function preloadRealAtlas(): Promise<void> {
  for (const [key, url] of Object.entries(realCatFrames)) {
    const texture = await Assets.load<Texture>(url);
    texture.source.scaleMode = "nearest";
    textureCache.set(key, texture);
  }
}

export function clearAtlasCache(): void {
  for (const tex of textureCache.values()) {
    tex.destroy(true);
  }
  textureCache.clear();
}

export function atlasStats(): { frames: number; version: string } {
  return { frames: textureCache.size, version: assetManifest.version };
}
