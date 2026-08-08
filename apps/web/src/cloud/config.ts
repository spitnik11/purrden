/**
 * API base URL.
 * Dev (Vite browser): proxies /api → http://127.0.0.1:8000 (see vite.config.ts).
 * Node smoke / tests: PURRDEN_API_BASE or VITE_API_BASE or localhost:8000.
 */
export function apiBase(): string {
  // Node / tsx (avoid @types/node dependency)
  const proc = (globalThis as { process?: { env?: Record<string, string | undefined> } })
    .process;
  const nodeEnv = proc?.env?.PURRDEN_API_BASE || proc?.env?.VITE_API_BASE;
  if (nodeEnv && nodeEnv.trim()) return nodeEnv.replace(/\/$/, "");

  try {
    const fromEnv = import.meta.env?.VITE_API_BASE as string | undefined;
    if (fromEnv && fromEnv.trim()) return fromEnv.replace(/\/$/, "");
    // Same-origin proxy path in Vite browser dev.
    if (import.meta.env?.DEV) return "/api";
  } catch {
    /* import.meta.env unavailable outside Vite */
  }
  return "http://127.0.0.1:8000";
}

export const SESSION_HEADER = "X-Purrden-Session";
