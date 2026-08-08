/**
 * Persistent cloud session preferences (Dexie).
 * Isolated so outbox/API client stay free of storage details — scalable module boundary.
 */
import { db } from "../save/db";

const KEYS = {
  sessionId: "cloud.sessionId",
  playerId: "cloud.playerId",
  deviceId: "cloud.deviceId",
  shareSessionId: "cloud.shareSessionId",
  lastError: "cloud.lastError",
} as const;

export type CloudSessionKeys = typeof KEYS;

export async function getPref<T>(key: string): Promise<T | null> {
  const row = await db.preferences.get(key);
  return (row?.value as T) ?? null;
}

export async function setPref(key: string, value: unknown): Promise<void> {
  await db.preferences.put({ key, value });
}

export async function clearPref(key: string): Promise<void> {
  await db.preferences.delete(key);
}

export async function readSession(): Promise<{
  sessionId: string | null;
  playerId: string | null;
  deviceId: string | null;
  shareSessionId: string | null;
  lastError: string | null;
}> {
  return {
    sessionId: await getPref<string>(KEYS.sessionId),
    playerId: await getPref<string>(KEYS.playerId),
    deviceId: await getPref<string>(KEYS.deviceId),
    shareSessionId: await getPref<string>(KEYS.shareSessionId),
    lastError: await getPref<string>(KEYS.lastError),
  };
}

export async function writeSession(guest: {
  session_id: string;
  player_id: string;
  device_id: string;
  share_session_id?: string;
}): Promise<void> {
  await setPref(KEYS.sessionId, guest.session_id);
  await setPref(KEYS.playerId, guest.player_id);
  await setPref(KEYS.deviceId, guest.device_id);
  await setPref(KEYS.shareSessionId, guest.share_session_id ?? guest.session_id);
  await clearPref(KEYS.lastError);
}

export async function clearSession(): Promise<void> {
  await clearPref(KEYS.sessionId);
  await clearPref(KEYS.playerId);
  await clearPref(KEYS.deviceId);
  await clearPref(KEYS.shareSessionId);
  await clearPref(KEYS.lastError);
}

export async function setLastError(msg: string | null): Promise<void> {
  if (msg) await setPref(KEYS.lastError, msg);
  else await clearPref(KEYS.lastError);
}

export { KEYS as CLOUD_PREF_KEYS };
