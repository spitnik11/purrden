/**
 * Small DOM helpers for the PWA shell.
 * Bare ids are accepted as `"timer-display"` → `#timer-display` for ergonomics,
 * while full CSS selectors (`#id`, `.class`, `header .x`) pass through unchanged.
 */

const BARE_ID = /^[A-Za-z][\w-]*$/;

/** Normalize selector: bare token → #id (backward-compatible footgun fix). */
export function normalizeSelector(sel: string): string {
  const s = sel.trim();
  if (!s) return s;
  if (s.startsWith("#") || s.startsWith(".") || s.startsWith("[") || s.includes(" ") || s.includes(">") || s.includes(":")) {
    return s;
  }
  if (BARE_ID.test(s)) return `#${s}`;
  return s;
}

export function $(sel: string, root: ParentNode = document): HTMLElement {
  const normalized = normalizeSelector(sel);
  const el = root.querySelector(normalized);
  if (!el) {
    throw new Error(`Missing ${normalized}${sel !== normalized ? ` (from "${sel}")` : ""}`);
  }
  return el as HTMLElement;
}

export function $maybe(sel: string, root: ParentNode = document): HTMLElement | null {
  const normalized = normalizeSelector(sel);
  return root.querySelector(normalized) as HTMLElement | null;
}

export function shellReady(): boolean {
  return Boolean(document.getElementById("timer-display") && document.getElementById("garden-host"));
}
