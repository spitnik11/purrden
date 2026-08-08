import Dexie, { type Table } from "dexie";
import type {
  FocusSessionRecord,
  GameProjection,
  PendingCommand,
} from "../game/types";

export interface SaveSnapshotRow {
  localSaveId: string;
  schemaVersion: number;
  contentVersion: string;
  saveVersion: number;
  projection: GameProjection;
  projectionHash: string;
  updatedAt: number;
}

export interface SyncStateRow {
  id: string; // "singleton"
  serverCursor: string | null;
  lastAcceptedVersion: number;
  lastSuccessAt: number | null;
  backoffUntil: number | null;
}

export interface PreferencesRow {
  key: string;
  value: unknown;
}

export class PurrdenDB extends Dexie {
  save_snapshots!: Table<SaveSnapshotRow, string>;
  pending_commands!: Table<PendingCommand, string>;
  focus_sessions!: Table<FocusSessionRecord, string>;
  sync_state!: Table<SyncStateRow, string>;
  preferences!: Table<PreferencesRow, string>;
  content_catalog!: Table<{ version: string; payload: unknown }, string>;

  constructor() {
    super("purrden");
    this.version(1).stores({
      save_snapshots: "localSaveId, updatedAt",
      pending_commands: "commandId, deviceSequence, state, createdAt",
      focus_sessions: "id, state, updatedAt",
      sync_state: "id",
      preferences: "key",
      content_catalog: "version",
    });
  }
}

export const db = new PurrdenDB();

export async function simpleHash(obj: unknown): Promise<string> {
  const text = JSON.stringify(obj);
  const data = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(digest)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
