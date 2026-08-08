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

/**
 * Apply a command in one IDB transaction:
 * append pending command + update projection + focus + bump sequences.
 */
export async function dispatch(
  type: CommandType,
  payload: Record<string, unknown> = {},
): Promise<GameStore> {
  if (!memory) await loadOrCreateStore();
  const result = await withLock(LockNames.save, async () => {
    const current = memory!;
    const applied = await applyCommand(
      current.projection,
      current.focus,
      type,
      payload,
    );

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
        } else if (current.focus) {
          // keep last focus record for history but clear active
          await db.focus_sessions.put({
            ...current.focus,
            state: current.focus.state,
          });
        }
      },
    );

    memory = {
      projection: applied.projection,
      focus: applied.focus,
      lastEvents: applied.events,
      persistentStorage: current.persistentStorage,
    };
    broadcast({ type: "SAVE_UPDATED", saveVersion: applied.projection.saveVersion });
    if (type.startsWith("focus.")) {
      broadcast({
        type: "FOCUS_UPDATED",
        focusSessionId: applied.focus?.id ?? "",
      });
    }
    if (type.startsWith("world.")) {
      broadcast({ type: "WORLD_UPDATED" });
    }
    return memory;
  });

  if (!result) throw new Error("Could not acquire save lock");
  emit();
  return result;
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
  const rows = await db.save_snapshots.orderBy("updatedAt").reverse().limit(1).toArray();
  if (!rows.length || !memory) return;
  const snap = rows[0];
  let focus: FocusSessionRecord | null = null;
  if (snap.projection.activeFocusId) {
    focus = (await db.focus_sessions.get(snap.projection.activeFocusId)) ?? null;
  }
  memory = {
    ...memory,
    projection: snap.projection,
    focus,
    lastEvents: ["Synced from another tab"],
  };
  emit();
}
