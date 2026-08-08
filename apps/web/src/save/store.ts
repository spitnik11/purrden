import { applyCommand } from "../game/commands";
import { createNewProjection } from "../game/projection";
import type {
  CommandType,
  FocusSessionRecord,
  GameProjection,
  PendingCommand,
} from "../game/types";
import { broadcast, LockNames, withLock } from "../lib/locks";
import { db, simpleHash, type SaveSnapshotRow } from "./db";

export interface GameStore {
  projection: GameProjection;
  focus: FocusSessionRecord | null;
  lastEvents: string[];
  persistentStorage: boolean | null;
}

let memory: GameStore | null = null;
const listeners = new Set<() => void>();

/** Serialize nested locks: focus complete always takes save lock; optional focus id lock. */
let completingFocusIds = new Set<string>();

export function getStore(): GameStore {
  if (!memory) throw new Error("Store not loaded");
  return memory;
}

export function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function emit() {
  for (const fn of listeners) fn();
}

/** Read latest projection + active focus from IndexedDB (authoritative under multi-tab). */
export async function readLatestFromDb(): Promise<{
  projection: GameProjection;
  focus: FocusSessionRecord | null;
} | null> {
  const rows = await db.save_snapshots.orderBy("updatedAt").reverse().limit(1).toArray();
  if (!rows.length) return null;
  const snap = rows[0];
  let focus: FocusSessionRecord | null = null;
  if (snap.projection.activeFocusId) {
    focus = (await db.focus_sessions.get(snap.projection.activeFocusId)) ?? null;
  } else if (memory?.focus?.id) {
    // completed focus may still be wanted for display
    focus = (await db.focus_sessions.get(memory.focus.id)) ?? null;
    if (focus && focus.state !== "running" && focus.state !== "paused") {
      // keep completed for one-shot display
    } else if (!snap.projection.activeFocusId) {
      focus = focus?.state === "completed" || focus?.state === "cancelled" ? focus : null;
    }
  }
  return { projection: snap.projection, focus };
}

export async function loadOrCreateStore(): Promise<GameStore> {
  const rows = await db.save_snapshots.orderBy("updatedAt").reverse().limit(1).toArray();
  if (rows.length === 0) {
    const projection = createNewProjection();
    const hash = await simpleHash(projection);
    await db.transaction(
      "rw",
      db.save_snapshots,
      db.sync_state,
      db.content_catalog,
      async () => {
        await db.save_snapshots.put({
          localSaveId: projection.localSaveId,
          schemaVersion: projection.schemaVersion,
          contentVersion: projection.contentVersion,
          saveVersion: projection.saveVersion,
          projection,
          projectionHash: hash,
          updatedAt: projection.updatedAt,
        });
        await db.sync_state.put({
          id: "singleton",
          serverCursor: null,
          lastAcceptedVersion: 0,
          lastSuccessAt: null,
          backoffUntil: null,
        });
      },
    );
    memory = {
      projection,
      focus: null,
      lastEvents: ["New garden started"],
      persistentStorage: null,
    };
  } else {
    const snap = rows[0];
    let focus: FocusSessionRecord | null = null;
    if (snap.projection.activeFocusId) {
      focus =
        (await db.focus_sessions.get(snap.projection.activeFocusId)) ?? null;
    }
    memory = {
      projection: snap.projection,
      focus,
      lastEvents: ["Save restored"],
      persistentStorage: null,
    };
  }

  // Request persistent storage (advisory)
  try {
    if (navigator.storage?.persist) {
      memory.persistentStorage = await navigator.storage.persist();
    }
  } catch {
    memory.persistentStorage = false;
  }

  emit();
  return memory;
}

async function persistApplied(
  current: GameStore,
  applied: Awaited<ReturnType<typeof applyCommand>>,
): Promise<GameStore> {
  const pending: PendingCommand = {
    ...applied.command,
    state: "pending",
  };
  const hash = await simpleHash(applied.projection);
  const snap: SaveSnapshotRow = {
    localSaveId: applied.projection.localSaveId,
    schemaVersion: applied.projection.schemaVersion,
    contentVersion: applied.projection.contentVersion,
    saveVersion: applied.projection.saveVersion,
    projection: applied.projection,
    projectionHash: hash,
    updatedAt: applied.projection.updatedAt,
  };

  await db.transaction(
    "rw",
    db.save_snapshots,
    db.pending_commands,
    db.focus_sessions,
    async () => {
      await db.pending_commands.put(pending);
      await db.save_snapshots.put(snap);
      if (applied.focus) {
        await db.focus_sessions.put(applied.focus);
      }
    },
  );

  const next: GameStore = {
    projection: applied.projection,
    focus: applied.focus,
    lastEvents: applied.events,
    persistentStorage: current.persistentStorage,
  };
  memory = next;
  broadcast({ type: "SAVE_UPDATED", saveVersion: applied.projection.saveVersion });
  if (applied.command.type.startsWith("focus.")) {
    broadcast({
      type: "FOCUS_UPDATED",
      focusSessionId: applied.focus?.id ?? "",
    });
  }
  if (applied.command.type.startsWith("world.")) {
    broadcast({ type: "WORLD_UPDATED" });
  }
  return next;
}

/**
 * Apply a command in one IDB transaction under Web Locks.
 * Rehydrates projection/focus from IndexedDB before apply so multi-tab
 * cannot double-award focus completion.
 */
export async function dispatch(
  type: CommandType,
  payload: Record<string, unknown> = {},
): Promise<GameStore> {
  if (!memory) await loadOrCreateStore();

  const focusIdForLock =
    type === "focus.complete" || type === "focus.pause" || type === "focus.cancel" || type === "focus.resume"
      ? memory!.focus?.id ?? memory!.projection.activeFocusId
      : type === "focus.start"
        ? null
        : null;

  const runApply = async (): Promise<GameStore> => {
    // Always re-read under the save lock (latest wins).
    const latest = await readLatestFromDb();
    const baseProjection = latest?.projection ?? memory!.projection;
    let baseFocus = latest?.focus ?? memory!.focus;

    // For complete: prefer focus row by active id even if memory is stale
    if (type === "focus.complete" && baseProjection.activeFocusId) {
      const row = await db.focus_sessions.get(baseProjection.activeFocusId);
      if (row) baseFocus = row;
    }

    // In-memory guard against concurrent complete in same tab
    if (type === "focus.complete" && baseFocus?.id) {
      if (completingFocusIds.has(baseFocus.id)) {
        return memory!;
      }
      completingFocusIds.add(baseFocus.id);
    }

    try {
      const applied = await applyCommand(baseProjection, baseFocus, type, payload);
      return await persistApplied(memory!, applied);
    } finally {
      if (type === "focus.complete" && baseFocus?.id) {
        completingFocusIds.delete(baseFocus.id);
      }
    }
  };

  // Nest focus lock inside save lock for completion/control paths.
  const result = await withLock(LockNames.save, async () => {
    if (focusIdForLock && (type === "focus.complete" || type === "focus.cancel")) {
      const nested = await withLock(LockNames.focus(focusIdForLock), runApply);
      if (nested === null) {
        // Another tab holds the focus lock — rehydrate and surface no-op.
        await reloadFromDb();
        if (memory?.focus?.rewarded || memory?.focus?.state === "completed") {
          return memory;
        }
        throw new Error("Focus is being completed in another tab");
      }
      return nested;
    }
    return runApply();
  });

  if (!result) throw new Error("Could not acquire save lock");
  emit();
  // Best-effort cloud outbox flush (no-op if not connected).
  void import("../cloud/outbox")
    .then((m) => m.maybeAutoFlush())
    .then(() => emit())
    .catch(() => {
      /* ignore — UI can surface cloud.lastError */
    });
  return result;
}

/**
 * Auto-complete when wall clock shows target reached.
 * Uses ifAvailable focus lock so only one tab awards the reward.
 */
export async function tryAutoCompleteFocus(): Promise<boolean> {
  if (!memory?.focus) return false;
  const focus = memory.focus;
  if (focus.state !== "running" && focus.state !== "paused") return false;
  if (focus.rewarded) return false;

  const { elapsedSeconds } = await import("@domain/focus-session.mjs");
  const elapsed = elapsedSeconds(
    {
      id: focus.id,
      state: focus.state,
      targetSeconds: focus.targetSeconds,
      startedAt: focus.startedAt,
      runningSince: focus.runningSince,
      accumulatedMs: focus.accumulatedMs,
      completedAt: focus.completedAt,
      cancelledAt: focus.cancelledAt,
      source: focus.source,
      updatedAt: focus.updatedAt,
    },
    Date.now(),
  );
  if (elapsed < focus.targetSeconds) return false;

  try {
    await dispatch("focus.complete");
    return true;
  } catch {
    // Another tab won, or not ready after rehydrate
    await reloadFromDb();
    return false;
  }
}

export async function exportSaveJson(): Promise<string> {
  const store = getStore();
  const commands = await db.pending_commands
    .where("deviceSequence")
    .above(0)
    .toArray();
  const focuses = await db.focus_sessions.toArray();
  return JSON.stringify(
    {
      format: "purrden-save-v1",
      exportedAt: new Date().toISOString(),
      projection: store.projection,
      focus: store.focus,
      pendingCommands: commands.slice(-200),
      focusSessions: focuses.slice(-20),
    },
    null,
    2,
  );
}

export async function importSaveJson(text: string): Promise<GameStore> {
  const data = JSON.parse(text);
  if (data.format !== "purrden-save-v1" || !data.projection) {
    throw new Error("Invalid save file");
  }
  const projection = data.projection as GameProjection;
  const focus = (data.focus as FocusSessionRecord | null) ?? null;
  const hash = await simpleHash(projection);

  await db.transaction(
    "rw",
    db.save_snapshots,
    db.focus_sessions,
    db.pending_commands,
    async () => {
      await db.save_snapshots.put({
        localSaveId: projection.localSaveId,
        schemaVersion: projection.schemaVersion,
        contentVersion: projection.contentVersion,
        saveVersion: projection.saveVersion,
        projection,
        projectionHash: hash,
        updatedAt: Date.now(),
      });
      if (focus) await db.focus_sessions.put(focus);
    },
  );

  memory = {
    projection,
    focus,
    lastEvents: ["Save imported"],
    persistentStorage: memory?.persistentStorage ?? null,
  };
  emit();
  broadcast({ type: "SAVE_UPDATED", saveVersion: projection.saveVersion });
  return memory;
}

export async function reloadFromDb(): Promise<void> {
  const latest = await readLatestFromDb();
  if (!latest || !memory) return;
  memory = {
    ...memory,
    projection: latest.projection,
    focus: latest.focus,
    lastEvents:
      latest.projection.saveVersion !== memory.projection.saveVersion
        ? ["Synced from another tab"]
        : memory.lastEvents,
  };
  emit();
}
