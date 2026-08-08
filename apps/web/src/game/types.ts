export type Rarity = "common" | "uncommon" | "rare" | "legendary";

export type Precipitation = "none" | "drizzle" | "rain" | "storm";
export type Daylight = "dawn" | "day" | "dusk" | "night";
export type Season = "spring" | "summer" | "autumn" | "winter";
export type Moon =
  | "new"
  | "waxing_crescent"
  | "first_quarter"
  | "waxing_gibbous"
  | "full"
  | "waning_gibbous"
  | "last_quarter"
  | "waning_crescent";

export interface WorldState {
  precipitation: Precipitation;
  daylight: Daylight;
  season: Season;
  moon: Moon;
}

export interface Visitor {
  visitId: string;
  catId: string;
  slotIndex: number;
  stage: string;
  bond: number;
  collected: boolean;
  explanation: string[];
  spawnWindowId: string;
  arrivedAt: number;
}

export interface GardenSlot {
  index: number;
  plantId: string | null;
  visitor: Visitor | null;
}

export interface CatCollectionEntry {
  catId: string;
  discoveredAt: number;
  bond: number;
  stage: string;
  fullyEvolved: boolean;
  visitCount: number;
}

export interface FocusSessionRecord {
  id: string;
  state: string;
  targetSeconds: number;
  startedAt: number | null;
  runningSince: number | null;
  accumulatedMs: number;
  completedAt: number | null;
  cancelledAt: number | null;
  source: string;
  updatedAt: number;
  rewarded: boolean;
}

export interface GameProjection {
  schemaVersion: 1;
  contentVersion: string;
  saveVersion: number;
  localSaveId: string;
  deviceId: string;
  deviceSequence: number;
  /** Guest HMAC secret (hex). Untrusted for economy after cloud claim. */
  installationSecretHex: string;
  growthEnergy: number;
  gardenLevel: number;
  slots: GardenSlot[];
  /** plant content id → owned count */
  plantInventory: Record<string, number>;
  food: number;
  collection: Record<string, CatCollectionEntry>;
  pity: Record<Rarity, number>;
  recentCats: string[];
  cooldownCats: string[];
  world: WorldState;
  /** Fake clock offset for time travel (ms). */
  clockOffsetMs: number;
  streakDays: number;
  lastFocusCompletedDay: string | null;
  activeFocusId: string | null;
  pendingSpawnWindows: number;
  lastSpawnAt: number | null;
  createdAt: number;
  updatedAt: number;
}

export type CommandType =
  | "focus.start"
  | "focus.pause"
  | "focus.resume"
  | "focus.complete"
  | "focus.cancel"
  | "garden.plant_place"
  | "garden.plant_remove"
  | "garden.collect_visitor"
  | "garden.feed_visitor"
  | "world.set"
  | "world.advance_spawn"
  | "meta.import_replace";

export interface PendingCommand {
  commandId: string;
  deviceId: string;
  deviceSequence: number;
  baseSaveVersion: number;
  type: CommandType;
  payload: Record<string, unknown>;
  createdAt: number;
  state: "pending" | "acked" | "rejected";
}

export const SCHEMA_VERSION = 1 as const;
export const CONTENT_VERSION = "2026.09.0";

export const PLANTS = [
  { id: "plant:fern:v1", label: "Fern", cost: 2, placementKey: "fern" },
  { id: "plant:pond:v1", label: "Pond", cost: 3, placementKey: "pond" },
  {
    id: "plant:sunny_rock:v1",
    label: "Sunny rock",
    cost: 2,
    placementKey: "sunny_rock",
  },
  { id: "plant:flower:v1", label: "Flower", cost: 1, placementKey: "flower" },
] as const;

export type PlantDef = (typeof PLANTS)[number];
