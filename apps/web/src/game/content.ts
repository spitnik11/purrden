import catsJson from "@content/cats.json";
import rulesetJson from "@content/ruleset.json";
import expLutJson from "@content/exp_lut.json";
import { PLANTS, type PlantDef } from "./types";

export const cats = catsJson.cats as unknown as Array<{
  id: string;
  rarity: string;
  enabled: boolean;
  fallback: boolean;
  base_score: number;
  min_garden_level: number;
  biome: string | null;
  affinities: Record<string, Record<string, number>>;
  evolutions: { stage: string; min_bond: number }[];
}>;
export const ruleset = rulesetJson as {
  version: string;
  algorithm_version: string;
  garden_slot_count: number;
  streak_bonus_per_day: number;
  streak_bonus_cap: number;
  discovery_bonus: number;
  recent_visit_penalty: number;
  fully_evolved_penalty: number;
  pity: Record<string, { per_miss: number; cap: number }>;
};
export const expLut = expLutJson;

export const contentBundle = {
  cats,
  ruleset,
  lut: expLut,
};

export function plantById(id: string): PlantDef | undefined {
  return PLANTS.find((p) => p.id === id);
}

export function placementKeys(plantIds: (string | null)[]): string[] {
  const keys: string[] = [];
  for (const id of plantIds) {
    if (!id) continue;
    const p = plantById(id);
    if (p) keys.push(p.placementKey);
  }
  return keys;
}

export function catLabel(catId: string): string {
  const short = catId.replace(/^cat:/, "").replace(/:v\d+$/, "");
  return short.charAt(0).toUpperCase() + short.slice(1);
}

export function evolutionStages(catId: string): { stage: string; min_bond: number }[] {
  const cat = cats.find((c) => c.id === catId);
  return cat?.evolutions ?? [{ stage: "kitten", min_bond: 0 }];
}

export function stageForBond(catId: string, bond: number): string {
  const stages = evolutionStages(catId);
  let current = stages[0]?.stage ?? "kitten";
  for (const s of stages) {
    if (bond >= s.min_bond) current = s.stage;
  }
  return current;
}

export function isFullyEvolved(catId: string, bond: number): boolean {
  const stages = evolutionStages(catId);
  if (stages.length === 0) return false;
  const last = stages[stages.length - 1];
  return bond >= last.min_bond && stages.length > 1;
}
