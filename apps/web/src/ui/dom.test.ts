/**
 * Tiny node-side check for selector normalization (run via tsx).
 * Not part of browser bundle tsconfig include if excluded — used as smoke.
 */
import { normalizeSelector } from "./dom";

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg);
}

assert(normalizeSelector("timer-display") === "#timer-display", "bare id");
assert(normalizeSelector("#timer-display") === "#timer-display", "hash id");
assert(normalizeSelector("header .save-meta") === "header .save-meta", "compound");
assert(normalizeSelector(".chip") === ".chip", "class");
console.log("DOM selector smoke OK");
