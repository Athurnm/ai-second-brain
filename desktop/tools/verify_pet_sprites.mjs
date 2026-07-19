#!/usr/bin/env node
// Stats every expected pet-battler v2 sprite asset and prints its dimensions —
// no PNG-decoding dependency needed, since PNG's IHDR chunk (width/height) sits
// at a fixed byte offset right after the 8-byte file signature.
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SPRITE_DIR = path.join(__dirname, "..", "src", "assets", "sprites");

const SPECIES = ["bit", "byte", "link", "pixel", "scribe"];
const STATES = ["idle", "walk", "attack"];
const ENEMIES = ["goblin", "slime", "golem", "reaper"];

function expectedNames() {
  const names = [];
  for (const sp of SPECIES) for (const st of STATES) names.push(`${sp}_${st}`);
  names.push("egg_idle");
  for (const en of ENEMIES) names.push(`enemy_${en}`);
  names.push("bg_journey", "bg_battle");
  return names;
}

function pngDimensions(buf) {
  // 8-byte PNG signature, then IHDR chunk: 4-byte length, 4-byte "IHDR", then
  // 4-byte width + 4-byte height (big-endian).
  if (buf.length < 24 || buf.toString("ascii", 12, 16) !== "IHDR") return null;
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

let missing = 0;
let ok = 0;
console.log(`Verifying pet sprite assets in ${SPRITE_DIR}\n`);
for (const name of expectedNames()) {
  const p = path.join(SPRITE_DIR, `${name}.png`);
  if (!existsSync(p)) {
    console.log(`  MISSING  ${name}.png`);
    missing++;
    continue;
  }
  const buf = readFileSync(p);
  const dim = pngDimensions(buf);
  if (!dim) {
    console.log(`  BAD PNG  ${name}.png (${buf.length} bytes, no IHDR found)`);
    missing++;
    continue;
  }
  console.log(`  ok       ${name}.png  ${dim.width}x${dim.height}  (${buf.length} bytes)`);
  ok++;
}
console.log(`\n${ok} present, ${missing} missing/invalid (engine falls back to the matrix renderer for those).`);
process.exit(missing > 0 && ok === 0 ? 1 : 0); // only hard-fail if NOTHING produced — partial fallback is a valid state
