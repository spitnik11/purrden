/**
 * Cloud outbox + multi-device claim/join/reconcile.
 * Session prefs live in session-store.ts; HTTP in client.ts — modular boundaries.
 */
import type { GameProjection, PendingCommand } from "../game/types";
import { broadcast, LockNames, withLock } from "../lib/locks";
import { db, simpleHash } from "../save/db";
import { getStore } from "../save/store";
import {
  bootstrap,
  claimGuestGenesis,
  createGuest,
  health,
  joinSession,
  listDevices,
  syncCommands,
  type SyncCommandIn,
} from "./client";
import {
  clearSession,
  readSession,
  setLastError,
  writeSession,
} from "./session-store";

export type CloudStatus =
  | "offline"
  | "connected"
  | "syncing"
  | "error"
  | "unknown";

export interface CloudInfo {
  status: CloudStatus;
  sessionId: string | null;
  /** Session id safe to share with a second browser (join). */
  shareSessionId: string | null;
  playerId: string | null;
  lastSuccessAt: number | null;
  lastError: string | null;
  pendingCount: number;
  lastAcceptedVersion: number;
  apiReachable: boolean | null;
  deviceCount: number;
}

async function rememberSession(guest: {
  session_id: string;
  player_id: string;
  device_id: string;
  save_version: number;
  share_session_id?: string;
}): Promise<void> {
  await writeSession(guest);
  await db.sync_state.put({
    id: "singleton",
    serverCursor: null,
    lastAcceptedVersion: guest.save_version,
    lastSuccessAt: Date.now(),
    backoffUntil: null,
  });
}

export async function getCloudInfo(opts?: { ping?: boolean }): Promise<CloudInfo> {
  const sess = await readSession();
  const sync = await db.sync_state.get("singleton");
  const pending = await db.pending_commands.where("state").equals("pending").count();
  let apiReachable: boolean | null = null;
  let deviceCount = 0;
  if (opts?.ping) {
    try {
      await health();
      apiReachable = true;
    } catch {
      apiReachable = false;
    }
  }
  if (sess.sessionId && opts?.ping) {
    try {
      const devs = await listDevices(sess.sessionId);
      deviceCount = devs.devices.length;
    } catch {
      /* ignore */
    }
  }
  return {
    status: !sess.sessionId ? "offline" : sess.lastError ? "error" : "connected",
    sessionId: sess.sessionId,
    shareSessionId: sess.shareSessionId ?? sess.sessionId,
    playerId: sess.playerId,
    lastSuccessAt: sync?.lastSuccessAt ?? null,
    lastError: sess.lastError,
    pendingCount: pending,
    lastAcceptedVersion: sync?.lastAcceptedVersion ?? 0,
    apiReachable,
    deviceCount,
  };
}

export async function disconnectCloud(): Promise<void> {
  await clearSession();
  await db.sync_state.put({
    id: "singleton",
    serverCursor: null,
    lastAcceptedVersion: 0,
    lastSuccessAt: null,
    backoffUntil: null,
  });
}

/** Empty cloud garden (fresh guest). */
export async function connectGuestCloud(): Promise<CloudInfo> {
  const local = getStore().projection;
  const guest = await createGuest({
    deviceId: local.deviceId,
    label: "browser",
  });
  await rememberSession(guest);
  await flushOutbox();
  return getCloudInfo({ ping: true });
}

/**
 * Claim: upload sanitized local garden as cloud genesis, then flush pending commands.
 */
export async function claimLocalAsCloud(): Promise<CloudInfo> {
  const local = getStore().projection;
  const guest = await claimGuestGenesis({
    deviceId: local.deviceId,
    label: "claim",
    projection: local as unknown as Record<string, unknown>,
  });
  await rememberSession(guest);

  const proj = { ...local, saveVersion: Math.max(local.saveVersion, guest.save_version) };
  const hash = await simpleHash(proj);
  await db.save_snapshots.put({
    localSaveId: proj.localSaveId,
    schemaVersion: proj.schemaVersion,
    contentVersion: proj.contentVersion,
    saveVersion: proj.saveVersion,
    projection: proj,
    projectionHash: hash,
    updatedAt: Date.now(),
  });
  broadcast({ type: "SAVE_UPDATED", saveVersion: proj.saveVersion });

  try {
    await flushOutbox(100);
  } catch {
    /* claim succeeded even if flush partial */
  }
  return getCloudInfo({ ping: true });
}

/** Second device: join with shared session id, pull bootstrap. */
export async function joinCloudSession(shareSessionId: string): Promise<CloudInfo> {
  const local = getStore().projection;
  const guest = await joinSession({
    sessionId: shareSessionId.trim(),
    deviceId: local.deviceId,
    label: "join",
  });
  await rememberSession({
    ...guest,
    share_session_id: shareSessionId.trim(),
  });
  await applyBootstrapProjection(
    guest.projection as unknown as GameProjection,
    guest.save_version,
  );
  return getCloudInfo({ ping: true });
}

/**
 * Reconcile: flush local outbox, then pull if server is ahead.
 */
export async function reconcileCloud(): Promise<string> {
  const { sessionId } = await readSession();
  if (!sessionId) throw new Error("Not connected");

  const flush = await flushOutbox(100);
  const boot = await bootstrap(sessionId);
  const sync = await db.sync_state.get("singleton");
  const localKnown = sync?.lastAcceptedVersion ?? 0;

  if (boot.save_version > localKnown || boot.save_version > getStore().projection.saveVersion) {
    await applyBootstrapProjection(
      boot.projection as unknown as GameProjection,
      boot.save_version,
    );
    return `Reconciled · flushed ${flush.sent} · pulled server v${boot.save_version}`;
  }
  return `Reconciled · flushed ${flush.sent} acked ${flush.acked} · server v${boot.save_version} (already current)`;
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

export async function flushOutbox(limit = 50): Promise<{
  sent: number;
  acked: number;
  rejected: number;
  dups: number;
}> {
  const { sessionId } = await readSession();
  if (!sessionId) {
    throw new Error("Not connected to cloud");
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

    await setLastError(null);
    broadcast({ type: "SYNC_COMPLETE" });
    return { sent: batch.length, acked, rejected, dups };
  });

  if (!result) throw new Error("Could not acquire save lock for sync");
  return result;
}

async function applyBootstrapProjection(
  projection: GameProjection,
  serverVersion: number,
): Promise<void> {
  const local = getStore().projection;
  projection.deviceId = local.deviceId;
  projection.installationSecretHex = local.installationSecretHex;
  projection.localSaveId = local.localSaveId;
  projection.deviceSequence = Math.max(
    local.deviceSequence,
    Number(projection.deviceSequence) || 0,
  );
  projection.saveVersion = Math.max(local.saveVersion, serverVersion);

  const hash = await simpleHash(projection);
  await db.transaction("rw", db.save_snapshots, db.sync_state, async () => {
    await db.save_snapshots.put({
      localSaveId: projection.localSaveId,
      schemaVersion: projection.schemaVersion ?? 1,
      contentVersion: projection.contentVersion ?? "2026.09.0",
      saveVersion: projection.saveVersion,
      projection,
      projectionHash: hash,
      updatedAt: Date.now(),
    });
    await db.sync_state.put({
      id: "singleton",
      serverCursor: null,
      lastAcceptedVersion: serverVersion,
      lastSuccessAt: Date.now(),
      backoffUntil: null,
    });
  });
  broadcast({ type: "SAVE_UPDATED", saveVersion: projection.saveVersion });
}

export async function pullBootstrap(): Promise<GameProjection> {
  const { sessionId } = await readSession();
  if (!sessionId) throw new Error("Not connected");
  const boot = await bootstrap(sessionId);
  const projection = boot.projection as unknown as GameProjection;
  await applyBootstrapProjection(projection, boot.save_version);
  return projection;
}

export async function setCloudError(msg: string | null): Promise<void> {
  await setLastError(msg);
}

export async function maybeAutoFlush(): Promise<void> {
  const { sessionId } = await readSession();
  if (!sessionId) return;
  try {
    await flushOutbox();
  } catch (e) {
    await setLastError(e instanceof Error ? e.message : String(e));
  }
}
