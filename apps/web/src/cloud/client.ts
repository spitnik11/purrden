import { apiBase, SESSION_HEADER } from "./config";

export class CloudError extends Error {
  status?: number;
  body?: unknown;
  constructor(message: string, status?: number, body?: unknown) {
    super(message);
    this.name = "CloudError";
    this.status = status;
    this.body = body;
  }
}

export interface GuestCreateOut {
  player_id: string;
  session_id: string;
  device_id: string;
  save_version: number;
  projection: Record<string, unknown>;
  joined?: boolean;
}

export interface BootstrapOut {
  player_id: string;
  save_version: number;
  content_version: string;
  projection: Record<string, unknown>;
}

export interface SyncCommandIn {
  commandId: string;
  deviceId: string;
  deviceSequence: number;
  baseSaveVersion: number;
  type: string;
  payload: Record<string, unknown>;
}

export interface CommandAck {
  commandId: string;
  status: string;
  reject_reason: string | null;
}

export interface SyncOut {
  save_version: number;
  projection: Record<string, unknown>;
  acks: CommandAck[];
  server_time: string;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  sessionId?: string | null,
): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (sessionId) headers.set(SESSION_HEADER, sessionId);
  if (init.method && !["GET", "HEAD", "OPTIONS"].includes(init.method.toUpperCase())) {
    const csrf = typeof document === "undefined" ? null : document.cookie.match(/(?:^|; )purrden_csrf=([^;]*)/)?.[1];
    if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  }

  let res: Response;
  try {
    res = await fetch(`${apiBase()}${path}`, { ...init, headers });
  } catch (e) {
    throw new CloudError(
      `Cannot reach API at ${apiBase()} — is Purrden-API-Dev running?`,
      0,
      e,
    );
  }

  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!res.ok) {
    const detail =
      typeof data === "object" && data && "detail" in data
        ? String((data as { detail: unknown }).detail)
        : text.slice(0, 200);
    throw new CloudError(detail || `HTTP ${res.status}`, res.status, data);
  }
  return data as T;
}

export function createGuest(body?: {
  deviceId?: string;
  label?: string;
}): Promise<GuestCreateOut> {
  return request<GuestCreateOut>("/v1/guest", {
    method: "POST",
    body: JSON.stringify(body ?? {}),
  });
}

export function claimGuestGenesis(body: {
  deviceId?: string;
  label?: string;
  projection: Record<string, unknown>;
}): Promise<GuestCreateOut> {
  return request<GuestCreateOut>("/v1/guest/claim", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function joinSession(body: {
  sessionId: string;
  deviceId?: string;
  label?: string;
}): Promise<GuestCreateOut> {
  return request<GuestCreateOut>("/v1/session/join", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function listDevices(
  sessionId: string,
): Promise<{ player_id: string; devices: { device_id: string; label?: string }[] }> {
  return request("/v1/devices", { method: "GET" }, sessionId);
}

export function bootstrap(sessionId: string): Promise<BootstrapOut> {
  return request<BootstrapOut>("/v1/bootstrap", { method: "GET" }, sessionId);
}

export function syncCommands(
  sessionId: string,
  body: { knownSaveVersion: number; cursor?: string | null; commands: SyncCommandIn[] },
): Promise<SyncOut> {
  return request<SyncOut>(
    "/v1/sync",
    { method: "POST", body: JSON.stringify(body) },
    sessionId,
  );
}

export function health(): Promise<{ status: string; version: string; env: string }> {
  return request("/health");
}

export async function logout(): Promise<void> {
  await request("/v1/auth/logout", { method: "POST" });
}
