/**
 * Pure offline-loop smoke (no DOM / IndexedDB).
 * Run: npx tsx src/game/loop-smoke.ts
 * Or:  npm run smoke
 */
import { applyCommand } from "./commands";
import { createNewProjection } from "./projection";
import type { FocusSessionRecord, GameProjection } from "./types";

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg);
}

async function main(): Promise<void> {
  let proj: GameProjection = createNewProjection();
  let focus: FocusSessionRecord | null = null;
  const energy0 = proj.growthEnergy;
  const spawns0 = proj.pendingSpawnWindows;

  // Start 3s focus
  {
    const r = await applyCommand(proj, focus, "focus.start", { seconds: 3 }, 1_000_000);
    proj = r.projection;
    focus = r.focus;
    assert(focus?.state === "running", "focus should be running");
  }

  // Too early to complete
  {
    let threw = false;
    try {
      await applyCommand(proj, focus, "focus.complete", {}, 1_000_000 + 500);
    } catch {
      threw = true;
    }
    assert(threw, "complete before target should throw");
  }

  // Complete after target
  {
    const r = await applyCommand(proj, focus, "focus.complete", {}, 1_000_000 + 3_000);
    proj = r.projection;
    focus = r.focus;
    assert(focus?.state === "completed", "completed");
    assert(focus?.rewarded === true, "rewarded");
    assert(proj.growthEnergy > energy0, "energy granted");
    assert(proj.pendingSpawnWindows === spawns0 + 1, "spawn window queued");
  }

  const energy1 = proj.growthEnergy;
  const spawns1 = proj.pendingSpawnWindows;

  // Double complete is idempotent (no duplicate reward)
  {
    const r = await applyCommand(proj, focus, "focus.complete", {}, 1_000_000 + 4_000);
    proj = r.projection;
    focus = r.focus;
    assert(proj.growthEnergy === energy1, "no double energy");
    assert(proj.pendingSpawnWindows === spawns1, "no double spawn");
    assert(r.events.some((e) => e.includes("already completed")), "idempotent event");
  }

  // Plant fern in slot 0
  {
    const r = await applyCommand(
      proj,
      focus,
      "garden.plant_place",
      { slotIndex: 0, plantId: "plant:fern:v1" },
    );
    proj = r.projection;
    focus = r.focus;
    assert(proj.slots[0].plantId === "plant:fern:v1", "planted");
  }

  // World rain + dusk
  {
    const r = await applyCommand(proj, focus, "world.set", {
      world: { precipitation: "rain", daylight: "dusk" },
    });
    proj = r.projection;
  }

  // Spawn visitor
  {
    const r = await applyCommand(proj, focus, "world.advance_spawn", {});
    proj = r.projection;
    assert(proj.slots[0].visitor != null, "visitor arrived");
    assert(proj.pendingSpawnWindows === spawns1 - 1, "spawn window consumed");
  }

  // Feed + collect
  {
    const r = await applyCommand(proj, focus, "garden.feed_visitor", { slotIndex: 0 });
    proj = r.projection;
    assert((proj.slots[0].visitor?.bond ?? 0) >= 50, "bond increased");
  }
  {
    const catId = proj.slots[0].visitor!.catId;
    const r = await applyCommand(proj, focus, "garden.collect_visitor", { slotIndex: 0 });
    proj = r.projection;
    assert(proj.slots[0].visitor == null, "visitor cleared");
    assert(proj.collection[catId] != null, "dex entry");
  }

  console.log("SMOKE OK: focus → plant → spawn → feed → collect (idempotent complete)");
  console.log(
    `  energy=${proj.growthEnergy} spawns=${proj.pendingSpawnWindows} dex=${Object.keys(proj.collection).length}`,
  );
}

main().catch((e) => {
  console.error("SMOKE FAILED:", e);
  // Avoid @types/node dependency in the browser package tsconfig.
  (globalThis as { process?: { exit: (c: number) => void } }).process?.exit?.(1);
  throw e;
});
