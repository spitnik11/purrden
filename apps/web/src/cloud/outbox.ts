/**
 * Cloud outbox: flush Dexie pending_commands to POST /v1/sync.
 * Local projection stays authoritative until a successful flush acknowledges commands.
 */
import type { GameProjection, PendingCommand } from "../game/types";
import { broadcast, LockNames, withLock } from "../lib/locks";
import { db, simpleHash } from "../save/db";
import { getStore } from "../save/store";
import {
  bootstrap,
  createGuest,
  health,
  syncCommands,
  type SyncCommandIn,
} from "./client";

const PREF_SESSION = "cloud.sessionId";
const PREF_PLAYER = "cloud.playerId";
const PREF_CLOUD_DEVICE = "cloud.deviceId";

export type CloudStatus =
  | "offline"
  | "connected"
  | "syncing"
  | "error"
  | "unknown";

export interface CloudInfo {
  status: CloudStatus;
  sessionId: string | null;
  playerId: string | null;
  lastSuccessAt: number | null;
  lastError: string | null;
  pendingCount: number;
  lastAcceptedVersion: number;
  apiReachable: boolean | null;
}

async function getPref<T>(key: string): Promise<T | null> {
  const row = await db.preferences.get(key);
  return (row?.value as T) ?? null;
}

async function setPref(key: string, value: unknown): Promise<void> {
  await db.preferences.put({ key, value });
}

async function clearPref(key: string): Promise<void> {
  await db.preferences.delete(key);
}

export async function getCloudInfo(opts?: { ping?: boolean }): Promise<CloudInfo> {
  const sessionId = await getPref<string>(PREF_SESSION);
  const playerId = await getPref<string>(PREF_PLAYER);
  const sync = await db.sync_state.get("singleton");
  const pending = await db.pending_commands.where("state").equals("pending").count();
  let apiReachable: boolean | null = null;
  if (opts?.ping) {
    try {
      await health();
      apiReachable = true;
    } catch {
      apiReachable = false;
    }
  }
  const lastError = (await getPref<string>("cloud.lastError")) ?? null;
  return {
    status: !sessionId
      ? "offline"
      : lastError
        ? "error"
        : "connected",
    sessionId,
    playerId,
    lastSuccessAt: sync?.lastSuccessAt ?? null,
    lastError,
    pendingCount: pending,
    lastAcceptedVersion: sync?.lastAcceptedVersion ?? 0,
    apiReachable,
  };
}

export async function disconnectCloud(): Promise<void> {
  await clearPref(PREF_SESSION);
  await clearPref(PREF_PLAYER);
  await clearPref(PREF_CLOUD_DEVICE);
  await clearPref("cloud.lastError");
  await db.sync_state.put({
    id: "singleton",
    serverCursor: null,
    lastAcceptedVersion: 0,
    lastSuccessAt: null,
    backoffUntil: null,
  });
}

/**
 * Create a guest cloud account and attach this browser.
 * Then flush the local outbox so local actions become cloud state.
 */
export async function connectGuestCloud(): Promise<CloudInfo> {
  const guest = await createGuest();
  await setPref(PREF_SESSION, guest.session_id);
  await setPref(PREF_PLAYER, guest.player_id);
  await setPref(PREF_CLOUD_DEVICE, guest.device_id);
  await clearPref("cloud.lastError");
  await db.sync_state.put({
    id: "singleton",
    serverCursor: null,
    lastAcceptedVersion: guest.save_version,
    lastSuccessAt: Date.now(),
    backoffUntil: null,
  });

  // Push local pending commands (and optionally rebuild server from them).
  await flushOutbox();
  return getCloudInfo();
}

function toSyncCommand(cmd: PendingCommand): SyncCommandIn {
  return {
    commandId: cmd.commandId,
    deviceId: cmd.deviceId,
    deviceSequence: cmd.deviceSequence,
    baseSaveVersion: cmd.baseSaveVersion,
    type: cmd.type,
    payload: cmd.payload,
  };
}

/**
 * Flush up to `limit` pending commands under the save lock.
 * Marks acked/rejected locally; does not replace local projection with server
 * (local is ahead optimistically). Server save_version tracked in sync_state.
 */
export async function flushOutbox(limit = 50): Promise<{
  sent: number;
  acked: number;
  rejected: number;
  dups: number;
}> {
  const sessionId = await getPref<string>(PREF_SESSION);
  if (!sessionId) {
    throw new Error("Not connected to cloud — use Connect guest first");
  }

  const result = await withLock(LockNames.save, async () => {
    const pending = await db.pending_commands
      .where("state")
      .equals("pending")
      .sortBy("deviceSequence");
    const batch = pending.slice(0, limit);
    if (batch.length === 0) {
      return { sent: 0, acked: 0, rejected: 0, dups: 0 };
    }

    const syncRow = (await db.sync_state.get("singleton")) ?? {
      id: "singleton",
      serverCursor: null,
      lastAcceptedVersion: 0,
      lastSuccessAt: null,
      backoffUntil: null,
    };

    const out = await syncCommands(sessionId, {
      knownSaveVersion: syncRow.lastAcceptedVersion,
      commands: batch.map(toSyncCommand),
    });

    let acked = 0;
    let rejected = 0;
    let dups = 0;
    await db.transaction("rw", db.pending_commands, db.sync_state, async () => {
      for (const ack of out.acks) {
        const row = await db.pending_commands.get(ack.commandId);
        if (!row) continue;
        if (ack.status === "applied") {
          row.state = "acked";
          acked += 1;
        } else if (ack.status === "dup") {
          row.state = "acked";
          dups += 1;
        } else {
          row.state = "rejected";
          rejected += 1;
        }
        await db.pending_commands.put(row);
      }
      await db.sync_state.put({
        ...syncRow,
        lastAcceptedVersion: out.save_version,
        lastSuccessAt: Date.now(),
        backoffUntil: null,
      });
    });

    await clearPref("cloud.lastError");
    broadcast({ type: "SYNC_COMPLETE" });
    return { sent: batch.length, acked, rejected, dups };
  });

  if (!result) throw new Error("Could not acquire save lock for sync");
  return result;
}

/**
 * Replace local projection with cloud bootstrap (destructive to unsent local-only
 * state that never reached the server). Pending local commands that were not
 * flushed may still apply on next flush if they don't conflict.
 */
export async function pullBootstrap(): Promise<GameProjection> {
  const sessionId = await getPref<string>(PREF_SESSION);
  if (!sessionId) throw new Error("Not connected");

  const boot = await bootstrap(sessionId);
  const projection = boot.projection as unknown as GameProjection;

  // Preserve local device identity for new commands; keep installation secret.
  const local = getStore().projection;
  projection.deviceId = local.deviceId;
  projection.installationSecretHex = local.installationSecretHex;
  projection.localSaveId = local.localSaveId;
  // Use max device sequence so new commands don't collide with cloud ledger
  projection.deviceSequence = Math.max(
    local.deviceSequence,
    Number(projection.deviceSequence) || 0,
  );
  projection.saveVersion = Math.max(local.saveVersion, boot.save_version);

  const hash = await simpleHash(projection);
  await db.transaction("rw", db.save_snapshots, db.sync_state, async () => {
    await db.save_snapshots.put({
      localSaveId: projection.localSaveId,
      schemaVersion: projection.schemaVersion ?? 1,
      contentVersion: projection.contentVersion ?? boot.content_version,
      saveVersion: projection.saveVersion,
      projection,
      projectionHash: hash,
      updatedAt: Date.now(),
    });
    await db.sync_state.put({
      id: "singleton",
      serverCursor: null,
      lastAcceptedVersion: boot.save_version,
      lastSuccessAt: Date.now(),
      backoffUntil: null,
    });
  });

  // Reload memory via store event — caller should reloadFromDb
  broadcast({ type: "SAVE_UPDATED", saveVersion: projection.saveVersion });
  return projection;
}

export async function setCloudError(msg: string | null): Promise<void> {
  if (msg) await setPref("cloud.lastError", msg);
  else await clearPref("cloud.lastError");
}

/** After each local dispatch, best-effort background flush if connected. */
export async function maybeAutoFlush(): Promise<void> {
  const sessionId = await getPref<string>(PREF_SESSION);
  if (!sessionId) return;
  try {
    await flushOutbox();
  } catch (e) {
    await setCloudError(e instanceof Error ? e.message : String(e));
  }
}
