import {
  CONTENT_VERSION,
  SCHEMA_VERSION,
  type FocusSessionRecord,
  type GameProjection,
  type GardenSlot,
  type Rarity,
  type WorldState,
} from "./types";
import { randomHex, uuid } from "../lib/id";
import { ruleset } from "./content";

const EMPTY_PITY: Record<Rarity, number> = {
  common: 0,
  uncommon: 0,
  rare: 0,
  legendary: 0,
};

export function defaultWorld(): WorldState {
  return {
    precipitation: "none",
    daylight: "day",
    season: "summer",
    moon: "new",
  };
}

export function emptySlots(count = ruleset.garden_slot_count): GardenSlot[] {
  return Array.from({ length: count }, (_, index) => ({
    index,
    plantId: null,
    visitor: null,
  }));
}

export function createNewProjection(now = Date.now()): GameProjection {
  return {
    schemaVersion: SCHEMA_VERSION,
    contentVersion: CONTENT_VERSION,
    saveVersion: 0,
    localSaveId: uuid(),
    deviceId: uuid(),
    deviceSequence: 0,
    installationSecretHex: randomHex(16),
    growthEnergy: 5,
    gardenLevel: 2,
    slots: emptySlots(),
    plantInventory: {
      "plant:fern:v1": 2,
      "plant:pond:v1": 1,
      "plant:sunny_rock:v1": 1,
      "plant:flower:v1": 3,
    },
    food: 5,
    collection: {},
    pity: { ...EMPTY_PITY },
    recentCats: [],
    cooldownCats: [],
    world: defaultWorld(),
    clockOffsetMs: 0,
    streakDays: 0,
    lastFocusCompletedDay: null,
    activeFocusId: null,
    pendingSpawnWindows: 0,
    lastSpawnAt: null,
    createdAt: now,
    updatedAt: now,
  };
}

export function gameNow(proj: GameProjection, wall = Date.now()): number {
  return wall + proj.clockOffsetMs;
}

export function dayKey(ms: number): string {
  const d = new Date(ms);
  return d.toISOString().slice(0, 10);
}

export function cloneProjection(p: GameProjection): GameProjection {
  return structuredClone(p);
}

export function createFocusRecord(
  id: string,
  targetSeconds: number,
  now: number,
): FocusSessionRecord {
  return {
    id,
    state: "idle",
    targetSeconds,
    startedAt: null,
    runningSince: null,
    accumulatedMs: 0,
    completedAt: null,
    cancelledAt: null,
    source: "focus_timer",
    updatedAt: now,
    rewarded: false,
  };
}
