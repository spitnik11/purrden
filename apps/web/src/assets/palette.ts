/**
 * Purrden core palette — mirrors art/style-bible.yaml (stable names → RGB).
 * Used by placeholder sprites and future atlas loaders.
 */

export type PaletteName =
  | "ink"
  | "shadow"
  | "brick"
  | "clay"
  | "sand"
  | "leaf"
  | "moss"
  | "pine"
  | "deep"
  | "sky"
  | "cool_blue"
  | "ice"
  | "cloud"
  | "mist"
  | "slate"
  | "coal"
  | "rose"
  | "gold"
  | "cream"
  | "bark"
  | "soil"
  | "lilac"
  | "dusk";

/** RGB 0–255, no alpha. */
export const PALETTE: Record<PaletteName, [number, number, number]> = {
  ink: [0x1a, 0x1c, 0x2c],
  shadow: [0x5d, 0x27, 0x5d],
  brick: [0xb1, 0x3e, 0x53],
  clay: [0xef, 0x7d, 0x57],
  sand: [0xff, 0xcd, 0x75],
  leaf: [0xa7, 0xf0, 0x70],
  moss: [0x38, 0xb7, 0x64],
  pine: [0x25, 0x71, 0x79],
  deep: [0x29, 0x36, 0x6f],
  sky: [0x3b, 0x5d, 0xc9],
  cool_blue: [0x41, 0xa6, 0xf6],
  ice: [0x73, 0xef, 0xf7],
  cloud: [0xf4, 0xf4, 0xf4],
  mist: [0x94, 0xb0, 0xc2],
  slate: [0x56, 0x6c, 0x86],
  coal: [0x33, 0x3c, 0x57],
  rose: [0xea, 0x90, 0xb4],
  gold: [0xf4, 0xd3, 0x5e],
  cream: [0xf9, 0xe6, 0xc5],
  bark: [0x8b, 0x5e, 0x34],
  soil: [0x5a, 0x3a, 0x1a],
  lilac: [0x9b, 0x6b, 0x9e],
  dusk: [0x4a, 0x3f, 0x6b],
};

export function hexRgb(name: PaletteName | string): [number, number, number] {
  if (name in PALETTE) return PALETTE[name as PaletteName];
  return PALETTE.mist;
}

export function hexNumber(name: PaletteName | string): number {
  const [r, g, b] = hexRgb(name);
  return (r << 16) | (g << 8) | b;
}
