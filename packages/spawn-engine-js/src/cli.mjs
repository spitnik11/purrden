// CLI: node cli.mjs <contexts.json> <secretHex>
// Prints a JSON array of spawn results (one per context) to stdout. Used by the conformance harness.
import { readFileSync } from "node:fs";
import { createHmac } from "node:crypto";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { resolveSpawn } from "./engine.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const contentDir = join(here, "..", "..", "..", "content");
const readJson = (p) => JSON.parse(readFileSync(p, "utf8"));

const content = {
  cats: readJson(join(contentDir, "cats.json")).cats,
  ruleset: readJson(join(contentDir, "ruleset.json")),
  lut: readJson(join(contentDir, "exp_lut.json")),
};

const hmac = (secretBytes, message) => new Uint8Array(createHmac("sha256", secretBytes).update(message, "utf8").digest());

const contextsPath = process.argv[2];
const secretHex = process.argv[3] ?? "00";
const secretBytes = Buffer.from(secretHex, "hex");
const contexts = readJson(contextsPath).contexts;

const results = contexts.map((ctx) => resolveSpawn(ctx, content, hmac, secretBytes));
process.stdout.write(JSON.stringify(results));
