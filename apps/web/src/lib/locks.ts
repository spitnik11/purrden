/**
 * Multi-tab coordination via Web Locks + BroadcastChannel.
 * Locks: purrden:focus:<id>, purrden:sync-leader, purrden:migration
 */

const CHANNEL = "purrden-tabs";

export type TabMessage =
  | { type: "FOCUS_UPDATED"; focusSessionId: string }
  | { type: "SAVE_UPDATED"; saveVersion: number }
  | { type: "SYNC_STARTED" }
  | { type: "SYNC_COMPLETE" }
  | { type: "LOGGED_OUT" }
  | { type: "WORLD_UPDATED" };

let channel: BroadcastChannel | null = null;

export function getChannel(): BroadcastChannel {
  if (!channel) channel = new BroadcastChannel(CHANNEL);
  return channel;
}

export function broadcast(msg: TabMessage): void {
  try {
    getChannel().postMessage(msg);
  } catch {
    /* ignore */
  }
}

export function onBroadcast(handler: (msg: TabMessage) => void): () => void {
  const ch = getChannel();
  const listener = (ev: MessageEvent) => handler(ev.data as TabMessage);
  ch.addEventListener("message", listener);
  return () => ch.removeEventListener("message", listener);
}

/** Run work holding an exclusive Web Lock. Falls back to bare run if unsupported. */
export async function withLock<T>(
  name: string,
  fn: () => Promise<T>,
  opts?: { ifAvailable?: boolean },
): Promise<T | null> {
  if (typeof navigator === "undefined" || !navigator.locks?.request) {
    return fn();
  }
  const mode = "exclusive" as const;
  if (opts?.ifAvailable) {
    return navigator.locks.request(name, { mode, ifAvailable: true }, async (lock) => {
      if (!lock) return null;
      return fn();
    });
  }
  return navigator.locks.request(name, { mode }, () => fn());
}

export const LockNames = {
  focus: (id: string) => `purrden:focus:${id}`,
  syncLeader: "purrden:sync-leader",
  migration: "purrden:migration",
  save: "purrden:save",
} as const;
