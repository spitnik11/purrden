/**
 * Pure command application: projection + optional focus → next state.
 * Side-effect free (except crypto for spawn which is async — spawn handled separately).
 */
import {
  createFocusSession,
  startFocus,
  pauseFocus,
  cancelFocus,
  completeFocus,
  growthEnergyFor,
  FocusState,
} from "@domain/focus-session.mjs";
import { contentBundle, placementKeys, stageForBond, isFullyEvolved } from "./content";
import { cloneProjection, dayKey, gameNow } from "./projection";
import type {
  CommandType,
  FocusSessionRecord,
  GameProjection,
  PendingCommand,
  Visitor,
  WorldState,
} from "./types";
import { PLANTS } from "./types";
import { uuid } from "../lib/id";
import { hexToBytes } from "../lib/crypto-hmac";
import { resolveSpawn } from "@spawn/engine.mjs";

export interface ApplyResult {
  projection: GameProjection;
  focus: FocusSessionRecord | null;
  command: Omit<PendingCommand, "state">;
  events: string[];
}

function toDomainFocus(rec: FocusSessionRecord) {
  return {
    id: rec.id,
    state: rec.state,
    targetSeconds: rec.targetSeconds,
    startedAt: rec.startedAt,
    runningSince: rec.runningSince,
    accumulatedMs: rec.accumulatedMs,
    completedAt: rec.completedAt,
    cancelledAt: rec.cancelledAt,
    source: rec.source,
    updatedAt: rec.updatedAt,
  };
}

function fromDomainFocus(
  d: ReturnType<typeof createFocusSession>,
  rewarded: boolean,
): FocusSessionRecord {
  return {
    id: d.id,
    state: d.state,
    targetSeconds: d.targetSeconds,
    startedAt: d.startedAt,
    runningSince: d.runningSince,
    accumulatedMs: d.accumulatedMs,
    completedAt: d.completedAt,
    cancelledAt: d.cancelledAt,
    source: d.source,
    updatedAt: d.updatedAt,
    rewarded,
  };
}

export async function applyCommand(
  projection: GameProjection,
  activeFocus: FocusSessionRecord | null,
  type: CommandType,
  payload: Record<string, unknown> = {},
  nowWall = Date.now(),
): Promise<ApplyResult> {
  const proj = cloneProjection(projection);
  let focus = activeFocus ? { ...activeFocus } : null;
  const events: string[] = [];
  const now = gameNow(proj, nowWall);

  switch (type) {
    case "focus.start": {
      const minutes = Number(payload.minutes ?? 25);
      const targetSeconds = Math.max(1, Math.floor(minutes * 60));
      // Dev shortcut: allow seconds for testing
      const secondsOverride = payload.seconds != null ? Number(payload.seconds) : null;
      const target = secondsOverride ?? targetSeconds;
      if (focus && (focus.state === FocusState.RUNNING || focus.state === FocusState.PAUSED)) {
        throw new Error("A focus session is already active");
      }
      const id = uuid();
      let d = createFocusSession({ id, targetSeconds: target, now });
      d = startFocus(d, now);
      focus = fromDomainFocus(d, false);
      proj.activeFocusId = id;
      events.push(`Focus started (${target}s)`);
      break;
    }
    case "focus.pause": {
      if (!focus) throw new Error("No focus session");
      focus = fromDomainFocus(pauseFocus(toDomainFocus(focus), now), focus.rewarded);
      events.push("Focus paused");
      break;
    }
    case "focus.resume": {
      if (!focus) throw new Error("No focus session");
      focus = fromDomainFocus(startFocus(toDomainFocus(focus), now), focus.rewarded);
      events.push("Focus resumed");
      break;
    }
    case "focus.cancel": {
      if (!focus) throw new Error("No focus session");
      focus = fromDomainFocus(cancelFocus(toDomainFocus(focus), now), focus.rewarded);
      proj.activeFocusId = null;
      events.push("Focus cancelled");
      break;
    }
    case "focus.complete": {
      if (!focus) throw new Error("No focus session");
      // Idempotent: already rewarded → no second energy/spawn (multi-tab safe).
      if (focus.rewarded || focus.state === FocusState.COMPLETED) {
        focus = {
          ...focus,
          state: FocusState.COMPLETED,
          rewarded: true,
          runningSince: null,
          updatedAt: now,
          completedAt: focus.completedAt ?? now,
        };
        proj.activeFocusId = null;
        events.push("Focus already completed (no duplicate reward)");
        break;
      }
      const before = toDomainFocus(focus);
      const after = completeFocus(before, now);
      if (after.state !== FocusState.COMPLETED) {
        throw new Error("Focus target not reached yet");
      }
      focus = fromDomainFocus(after, false);
      const energy = growthEnergyFor(after);
      proj.growthEnergy += energy;
      focus.rewarded = true;
      // Streak
      const day = dayKey(now);
      if (proj.lastFocusCompletedDay) {
        const prev = new Date(proj.lastFocusCompletedDay + "T00:00:00Z").getTime();
        const cur = new Date(day + "T00:00:00Z").getTime();
        const diffDays = Math.round((cur - prev) / 86_400_000);
        if (diffDays === 1) proj.streakDays += 1;
        else if (diffDays > 1) proj.streakDays = 1;
        // same day: keep streak
      } else {
        proj.streakDays = 1;
      }
      proj.lastFocusCompletedDay = day;
      // Each completed focus queues a spawn window
      proj.pendingSpawnWindows += 1;
      events.push(`Focus complete · +${energy} growth energy · spawn window ready`);
      proj.activeFocusId = null;
      break;
    }
    case "garden.plant_place": {
      const slotIndex = Number(payload.slotIndex);
      const plantId = String(payload.plantId ?? "");
      const plant = PLANTS.find((p) => p.id === plantId);
      if (!plant) throw new Error("Unknown plant");
      const slot = proj.slots[slotIndex];
      if (!slot) throw new Error("Invalid slot");
      if (slot.plantId) throw new Error("Slot already has a plant");
      if (slot.visitor) throw new Error("Cannot plant under a visitor");
      const owned = proj.plantInventory[plantId] ?? 0;
      if (owned < 1 && proj.growthEnergy < plant.cost) {
        throw new Error("Not enough plants or growth energy");
      }
      if (owned >= 1) {
        proj.plantInventory[plantId] = owned - 1;
      } else {
        proj.growthEnergy -= plant.cost;
      }
      slot.plantId = plantId;
      events.push(`Planted ${plant.label} in slot ${slotIndex + 1}`);
      break;
    }
    case "garden.plant_remove": {
      const slotIndex = Number(payload.slotIndex);
      const slot = proj.slots[slotIndex];
      if (!slot?.plantId) throw new Error("No plant in slot");
      if (slot.visitor) throw new Error("Cannot remove plant under a visitor");
      const pid = slot.plantId;
      slot.plantId = null;
      proj.plantInventory[pid] = (proj.plantInventory[pid] ?? 0) + 1;
      events.push(`Removed plant from slot ${slotIndex + 1}`);
      break;
    }
    case "garden.collect_visitor": {
      const slotIndex = Number(payload.slotIndex);
      const slot = proj.slots[slotIndex];
      if (!slot?.visitor || slot.visitor.collected) throw new Error("No visitor to collect");
      const v = slot.visitor;
      v.collected = true;
      const existing = proj.collection[v.catId];
      if (!existing) {
        proj.collection[v.catId] = {
          catId: v.catId,
          discoveredAt: now,
          bond: 0,
          stage: v.stage,
          fullyEvolved: false,
          visitCount: 1,
        };
      } else {
        existing.visitCount += 1;
      }
      proj.food += 1;
      // free the slot visitor after collect stays visible until leave — mark collected, clear visitor
      slot.visitor = null;
      events.push(`Collected ${v.catId}`);
      break;
    }
    case "garden.feed_visitor": {
      const slotIndex = Number(payload.slotIndex);
      const slot = proj.slots[slotIndex];
      if (!slot?.visitor) throw new Error("No visitor");
      if (proj.food < 1) throw new Error("No food");
      proj.food -= 1;
      const v = slot.visitor;
      v.bond += 50;
      v.stage = stageForBond(v.catId, v.bond);
      const entry = proj.collection[v.catId] ?? {
        catId: v.catId,
        discoveredAt: now,
        bond: 0,
        stage: v.stage,
        fullyEvolved: false,
        visitCount: 0,
      };
      entry.bond = Math.max(entry.bond, v.bond);
      entry.stage = stageForBond(v.catId, entry.bond);
      entry.fullyEvolved = isFullyEvolved(v.catId, entry.bond);
      proj.collection[v.catId] = entry;
      events.push(`Fed ${v.catId} · bond ${v.bond} · stage ${v.stage}`);
      break;
    }
    case "world.set": {
      const w = payload.world as Partial<WorldState>;
      proj.world = { ...proj.world, ...w };
      events.push("World updated");
      break;
    }
    case "world.advance_spawn": {
      if (proj.pendingSpawnWindows < 1) {
        // allow forced spawn for demo/dev
        if (!payload.force) throw new Error("No pending spawn windows — complete a focus first");
      } else {
        proj.pendingSpawnWindows -= 1;
      }
      const free = proj.slots.find((s) => !s.visitor);
      if (!free) throw new Error("No free garden slot for a visitor");
      const visitor = await rollVisitor(proj, free.index, now);
      free.visitor = visitor;
      // pity update already applied inside rollVisitor on proj
      proj.recentCats = [visitor.catId, ...proj.recentCats.filter((c) => c !== visitor.catId)].slice(0, 8);
      proj.lastSpawnAt = now;
      events.push(
        `Visitor ${visitor.catId} arrived` +
          (visitor.explanation.length ? ` (${visitor.explanation.join(", ")})` : ""),
      );
      break;
    }
    default:
      throw new Error(`Unknown command: ${type}`);
  }

  proj.deviceSequence += 1;
  proj.saveVersion += 1;
  proj.updatedAt = nowWall;

  const command = {
    commandId: uuid(),
    deviceId: proj.deviceId,
    deviceSequence: proj.deviceSequence,
    baseSaveVersion: projection.saveVersion,
    type,
    payload,
    createdAt: nowWall,
  };

  return { projection: proj, focus, command, events };
}

async function rollVisitor(
  proj: GameProjection,
  slotIndex: number,
  now: number,
): Promise<Visitor> {
  const placements = placementKeys(proj.slots.map((s) => s.plantId));
  const discovered = Object.keys(proj.collection);
  const fully_evolved = Object.values(proj.collection)
    .filter((c) => c.fullyEvolved)
    .map((c) => c.catId);

  const ctx = {
    user_id: proj.localSaveId,
    spawn_window_id: `spw_${proj.saveVersion}_${slotIndex}_${now}`,
    slot_index: slotIndex,
    spawn_generation: 1,
    ruleset_version: proj.contentVersion,
    garden_level: proj.gardenLevel,
    biome: "meadow",
    placements,
    world: { ...proj.world },
    activity: { streak_days: proj.streakDays },
    pity: { ...proj.pity },
    occupied_slots: proj.slots
      .filter((s) => s.visitor)
      .map((s) => s.index),
    discovered,
    fully_evolved,
    recent_cats: proj.recentCats,
    cooldown_cats: proj.cooldownCats,
  };

  const secret = hexToBytes(proj.installationSecretHex);
  const result = await resolveSpawnAsync(ctx, secret);

  if (!result.selected) {
    throw new Error(result.no_spawn_reason ?? "spawn failed");
  }

  // Apply pity_after
  proj.pity = result.pity_after as GameProjection["pity"];

  return {
    visitId: uuid(),
    catId: result.selected,
    slotIndex,
    stage: stageForBond(result.selected, 0),
    bond: 0,
    collected: false,
    explanation: result.explanation?.top_factors ?? [],
    spawnWindowId: ctx.spawn_window_id,
    arrivedAt: now,
  };
}

/** Async-friendly spawn: engine uses injected hmac; we provide async-backed sync by using a prebuilt cache.
 *  The engine calls hmac multiple times synchronously. Web Crypto is async only.
 *  Solution: use a pure JS SHA-256 HMAC implementation for the browser spawn path.
 */
async function resolveSpawnAsync(
  ctx: Record<string, unknown>,
  secret: Uint8Array,
): Promise<{
  selected: string | null;
  no_spawn_reason: string | null;
  pity_after: Record<string, number>;
  explanation: { top_factors: string[] };
}> {
  const { hmacSha256Sync } = await import("../lib/hmac-sync");
  const hmac = (secretBytes: Uint8Array, message: string) =>
    hmacSha256Sync(secretBytes, message);
  const result = resolveSpawn(ctx, contentBundle, hmac, secret) as unknown as {
    selected: string | null;
    no_spawn_reason: string | null;
    pity_after: Record<string, number>;
    explanation: { top_factors: string[] };
  };
  return result;
}
