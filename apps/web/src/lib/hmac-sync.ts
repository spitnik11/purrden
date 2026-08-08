/**
 * Pure JS HMAC-SHA256 for deterministic spawn draws in the browser.
 * SubtleCrypto is async-only; the spawn engine needs a synchronous hmac inject.
 * Matches Node: crypto.createHmac('sha256', secret).update(msg, 'utf8').digest()
 */

function rotr(n: number, x: number) {
  return (x >>> n) | (x << (32 - n));
}
function ch(x: number, y: number, z: number) {
  return (x & y) ^ (~x & z);
}
function maj(x: number, y: number, z: number) {
  return (x & y) ^ (x & z) ^ (y & z);
}
function sigma0(x: number) {
  return rotr(2, x) ^ rotr(13, x) ^ rotr(22, x);
}
function sigma1(x: number) {
  return rotr(6, x) ^ rotr(11, x) ^ rotr(25, x);
}
function gamma0(x: number) {
  return rotr(7, x) ^ rotr(18, x) ^ (x >>> 3);
}
function gamma1(x: number) {
  return rotr(17, x) ^ rotr(19, x) ^ (x >>> 10);
}

const K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4,
  0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe,
  0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f,
  0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
  0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
  0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
  0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116,
  0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
  0xc67178f2,
]);

function sha256(message: Uint8Array): Uint8Array {
  const bitLen = message.length * 8;
  const withOne = message.length + 1;
  let padLen = withOne % 64;
  padLen = padLen <= 56 ? 56 - padLen : 120 - padLen;
  const total = withOne + padLen + 8;
  const buf = new Uint8Array(total);
  buf.set(message);
  buf[message.length] = 0x80;
  const view = new DataView(buf.buffer);
  const hi = Math.floor(bitLen / 0x100000000);
  const lo = bitLen >>> 0;
  view.setUint32(total - 8, hi, false);
  view.setUint32(total - 4, lo, false);

  let h0 = 0x6a09e667,
    h1 = 0xbb67ae85,
    h2 = 0x3c6ef372,
    h3 = 0xa54ff53a,
    h4 = 0x510e527f,
    h5 = 0x9b05688c,
    h6 = 0x1f83d9ab,
    h7 = 0x5be0cd19;

  const w = new Uint32Array(64);
  for (let i = 0; i < total; i += 64) {
    for (let t = 0; t < 16; t++) w[t] = view.getUint32(i + t * 4, false);
    for (let t = 16; t < 64; t++) {
      w[t] = (gamma1(w[t - 2]) + w[t - 7] + gamma0(w[t - 15]) + w[t - 16]) >>> 0;
    }
    let a = h0,
      b = h1,
      c = h2,
      d = h3,
      e = h4,
      f = h5,
      g = h6,
      h = h7;
    for (let t = 0; t < 64; t++) {
      const t1 = (h + sigma1(e) + ch(e, f, g) + K[t] + w[t]) >>> 0;
      const t2 = (sigma0(a) + maj(a, b, c)) >>> 0;
      h = g;
      g = f;
      f = e;
      e = (d + t1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (t1 + t2) >>> 0;
    }
    h0 = (h0 + a) >>> 0;
    h1 = (h1 + b) >>> 0;
    h2 = (h2 + c) >>> 0;
    h3 = (h3 + d) >>> 0;
    h4 = (h4 + e) >>> 0;
    h5 = (h5 + f) >>> 0;
    h6 = (h6 + g) >>> 0;
    h7 = (h7 + h) >>> 0;
  }

  const out = new Uint8Array(32);
  const ov = new DataView(out.buffer);
  ov.setUint32(0, h0, false);
  ov.setUint32(4, h1, false);
  ov.setUint32(8, h2, false);
  ov.setUint32(12, h3, false);
  ov.setUint32(16, h4, false);
  ov.setUint32(20, h5, false);
  ov.setUint32(24, h6, false);
  ov.setUint32(28, h7, false);
  return out;
}

export function hmacSha256Sync(secret: Uint8Array, message: string): Uint8Array {
  const block = 64;
  let key = secret;
  if (key.length > block) key = sha256(key);
  if (key.length < block) {
    const k = new Uint8Array(block);
    k.set(key);
    key = k;
  }
  const oKey = new Uint8Array(block);
  const iKey = new Uint8Array(block);
  for (let i = 0; i < block; i++) {
    oKey[i] = key[i] ^ 0x5c;
    iKey[i] = key[i] ^ 0x36;
  }
  const msgBytes = new TextEncoder().encode(message);
  const inner = new Uint8Array(block + msgBytes.length);
  inner.set(iKey);
  inner.set(msgBytes, block);
  const innerHash = sha256(inner);
  const outer = new Uint8Array(block + 32);
  outer.set(oKey);
  outer.set(innerHash, block);
  return sha256(outer);
}
