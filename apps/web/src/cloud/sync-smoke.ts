/**
 * Integration smoke against a running API (optional).
 * Run with API up:  npm run smoke:cloud
 * Skips cleanly if API is unreachable.
 */
import { createGuest, health, syncCommands } from "./client";

async function main(): Promise<void> {
  try {
    const h = await health();
    console.log("API health:", h);
  } catch (e) {
    console.log("SMOKE CLOUD SKIP: API not reachable —", e instanceof Error ? e.message : e);
    return;
  }

  const guest = await createGuest();
  console.log("guest", guest.player_id, "session", guest.session_id.slice(0, 8));

  const device = guest.device_id;
  const r1 = await syncCommands(guest.session_id, {
    knownSaveVersion: 0,
    commands: [
      {
        commandId: "smoke-plant-1",
        deviceId: device,
        deviceSequence: 1,
        baseSaveVersion: 0,
        type: "garden.plant_place",
        payload: { slotIndex: 0, plantId: "plant:fern:v1" },
      },
    ],
  });
  if (r1.acks[0]?.status !== "applied") {
    throw new Error(`expected applied, got ${JSON.stringify(r1.acks)}`);
  }
  if (r1.projection.slots?.[0]?.plantId !== "plant:fern:v1") {
    throw new Error("plant not on server projection");
  }

  // idempotent retry
  const r2 = await syncCommands(guest.session_id, {
    knownSaveVersion: r1.save_version,
    commands: [
      {
        commandId: "smoke-plant-1",
        deviceId: device,
        deviceSequence: 1,
        baseSaveVersion: 0,
        type: "garden.plant_place",
        payload: { slotIndex: 0, plantId: "plant:fern:v1" },
      },
    ],
  });
  if (r2.acks[0]?.status !== "dup") {
    throw new Error(`expected dup, got ${JSON.stringify(r2.acks)}`);
  }
  if (r2.save_version !== r1.save_version) {
    throw new Error("dup retry must not bump save_version");
  }

  console.log("SMOKE CLOUD OK: guest → plant → idempotent retry");
}

main().catch((e) => {
  console.error("SMOKE CLOUD FAILED:", e);
  throw e;
});
