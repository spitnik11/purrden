/**
 * Deterministic pixel placeholder sprites (32×32 cats, 16×16 plants).
 * Binary alpha, palette-only colors — matches style bible constraints.
 * Replaced later by promoted atlas frames without changing content IDs.
 */
import { hexRgb } from "./palette";
import type { CatVisual, PlantVisual } from "./manifest";

export function createPixelCanvas(w: number, h: number): {
  canvas: HTMLCanvasElement;
  ctx: CanvasRenderingContext2D;
  put: (x: number, y: number, name: string) => void;
  imageData: ImageData;
  commit: () => void;
} {
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  const imageData = ctx.createImageData(w, h);
  const data = imageData.data;

  const put = (x: number, y: number, name: string) => {
    if (x < 0 || y < 0 || x >= w || y >= h) return;
    const [r, g, b] = hexRgb(name);
    const i = (y * w + x) * 4;
    data[i] = r;
    data[i + 1] = g;
    data[i + 2] = b;
    data[i + 3] = 255;
  };

  const commit = () => {
    ctx.putImageData(imageData, 0, 0);
  };

  return { canvas, ctx, put, imageData, commit };
}

function fillRect(
  put: (x: number, y: number, name: string) => void,
  x0: number,
  y0: number,
  w: number,
  h: number,
  color: string,
) {
  for (let y = y0; y < y0 + h; y++) {
    for (let x = x0; x < x0 + w; x++) put(x, y, color);
  }
}

/** Draw a simple cat silhouette into 32×32 buffer. */
export function drawCatPlaceholder(
  visual: CatVisual,
  stageScale = 1,
): HTMLCanvasElement {
  const W = 32;
  const H = 32;
  const { canvas, put, commit } = createPixelCanvas(W, H);

  const s = Math.max(0.7, Math.min(1.1, stageScale));
  // Center body relative to baseline y=29
  const bodyW = Math.round(14 * s);
  const bodyH = Math.round(10 * s);
  const bodyX = Math.floor((W - bodyW) / 2);
  const bodyY = 29 - bodyH;

  // outline (1px shell)
  fillRect(put, bodyX - 1, bodyY - 1, bodyW + 2, bodyH + 2, visual.outline);
  fillRect(put, bodyX, bodyY, bodyW, bodyH, visual.body);

  // head
  const headW = Math.round(10 * s);
  const headH = Math.round(8 * s);
  const headX = Math.floor((W - headW) / 2);
  const headY = bodyY - headH + 2;
  fillRect(put, headX - 1, headY - 1, headW + 2, headH + 2, visual.outline);
  fillRect(put, headX, headY, headW, headH, visual.body);

  // ears
  const earW = Math.max(2, Math.round(3 * s));
  const earH = Math.max(3, Math.round(4 * s));
  fillRect(put, headX, headY - earH + 1, earW, earH, visual.outline);
  fillRect(put, headX + 1, headY - earH + 2, earW - 1, earH - 1, visual.accent);
  fillRect(put, headX + headW - earW, headY - earH + 1, earW, earH, visual.outline);
  fillRect(
    put,
    headX + headW - earW,
    headY - earH + 2,
    earW - 1,
    earH - 1,
    visual.accent,
  );

  // eyes
  const eyeY = headY + Math.floor(headH / 2);
  put(headX + 2, eyeY, visual.eye);
  put(headX + headW - 3, eyeY, visual.eye);

  // belly accent
  fillRect(
    put,
    bodyX + 2,
    bodyY + Math.floor(bodyH / 2),
    bodyW - 4,
    Math.max(2, Math.floor(bodyH / 3)),
    visual.accent,
  );

  // feet on baseline
  put(bodyX + 1, 28, visual.outline);
  put(bodyX + bodyW - 2, 28, visual.outline);

  // tail (right-facing default)
  if (visual.silhouette === "lounging") {
    fillRect(put, bodyX + bodyW, bodyY + 2, 4, 2, visual.outline);
    fillRect(put, bodyX + bodyW, bodyY + 2, 3, 1, visual.body);
  } else {
    fillRect(put, bodyX + bodyW - 1, bodyY - 3, 2, 4, visual.outline);
    put(bodyX + bodyW, bodyY - 3, visual.accent);
  }

  commit();
  return canvas;
}

export function drawPlantPlaceholder(visual: PlantVisual): HTMLCanvasElement {
  const W = 16;
  const H = 16;
  const { canvas, put, commit } = createPixelCanvas(W, H);

  if (visual.shape === "pond") {
    fillRect(put, 2, 8, 12, 5, visual.primary);
    fillRect(put, 3, 9, 10, 3, visual.accent);
  } else if (visual.shape === "rock") {
    fillRect(put, 3, 8, 10, 6, visual.primary);
    fillRect(put, 4, 9, 4, 2, visual.accent);
  } else if (visual.shape === "flower") {
    fillRect(put, 7, 8, 2, 6, visual.accent);
    put(6, 6, visual.primary);
    put(8, 6, visual.primary);
    put(7, 5, visual.primary);
    put(7, 7, visual.primary);
  } else {
    // fern
    fillRect(put, 7, 4, 2, 10, visual.primary);
    for (let i = 0; i < 4; i++) {
      put(5, 5 + i * 2, visual.accent);
      put(9, 6 + i * 2, visual.accent);
      put(4, 6 + i * 2, visual.primary);
      put(10, 7 + i * 2, visual.primary);
    }
  }

  commit();
  return canvas;
}
