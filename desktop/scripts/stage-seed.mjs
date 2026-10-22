#!/usr/bin/env node
// Stage the course TEXT a seeded installer carries.
//
//   node desktop/scripts/stage-seed.mjs                       # every course
//   node desktop/scripts/stage-seed.mjs --courses a,b         # a subset
//   node desktop/scripts/stage-seed.mjs --pcm D:\Projects\Pentaho-Content-Manager
//
// Writes src-tauri/vendor/seed/, which tauri.seeded.conf.json maps to
// <install>/seed. On first run the app lays it out under its own state
// directory (exam_bank/utils/seed.py), so a clean laptop opens onto real
// courses with no Content Manager checkout. See that module for how it
// ranks against a real one, and for what a seeded copy cannot do.
//
// What the bank reads (exam_bank/core/pcm_reader.py, publisher.py)
//
//   course.json, SUMMARY.md, exam.json, glossary.json   per course
//   <lab>/manifest.json, <lab>/guide.md                 per lab
//
// So the seed carries **Markdown and JSON only**, not the course folder.
// A course is mostly lab files, screenshots and sample data: the whole
// Content Manager courses/ is hundreds of megabytes the bank never opens,
// and the editor's seed (which does need them) is a different installer.
// Anything under files/, _assets/ or node_modules/ stays behind, and so
// does anything git does not track: the distribution repo is public, and
// an installer is a second way for an ignored .env to leave the building.
// Outside git a short skip list applies instead.
//
// Plain Node, no dependencies, so it runs under pytest on any OS
// (tests/test_stage_seed.py).

import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  copyFileSync, existsSync, lstatSync, mkdirSync, readdirSync, readFileSync,
  rmSync, statSync, writeFileSync,
} from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const desktopDir = resolve(here, "..");
const repoRoot = resolve(desktopDir, "..");

// Directories whose contents the bank never reads and often should not
// leave the building: lab files carry credentials' siblings and sample data.
const SKIP_DIRS = new Set(["files", "_assets", "node_modules", ".git", "__pycache__"]);
const KEEP_EXT = /\.(md|json)$/i;
const SECRETISH = /^\.env(\.|$)|\.(pem|key)$/i;

function fail(message) {
  console.error(`\n  stage-seed: ${message}\n`);
  process.exit(1);
}

function parseArgs(argv) {
  const opts = { pcm: null, courses: null, out: null };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    const value = () => argv[++i] ?? fail(`${arg} needs a value`);
    if (arg === "--pcm") opts.pcm = value();
    else if (arg === "--courses") opts.courses = value().split(",").map((c) => c.trim()).filter(Boolean);
    else if (arg === "--out") opts.out = value();
    else fail(`unknown argument ${arg}`);
  }
  return opts;
}

const opts = parseArgs(process.argv.slice(2));
// `npm run dist:seeded` chains several scripts and cannot pass a flag to
// this one, so the subset can also come from the environment.
if (!opts.courses && process.env.PEB_SEED_COURSES) {
  opts.courses = process.env.PEB_SEED_COURSES.split(",").map((c) => c.trim()).filter(Boolean);
}
const pcm = resolve(opts.pcm ?? process.env.PCM_REPO ?? join(repoRoot, "..", "Pentaho-Content-Manager"));
const out = resolve(opts.out ?? join(desktopDir, "src-tauri", "vendor", "seed"));
const coursesOut = join(out, "courses");

// ── Preconditions ───────────────────────────────────────────────────

if (!existsSync(join(pcm, "courses"))) {
  fail(`no courses/ in ${pcm}. Point --pcm (or PCM_REPO) at a Pentaho-Content-Manager checkout.`);
}
// rmSync below is recursive. Never aim it at, or around, the checkout.
const inside = (a, b) => a === b || a.startsWith(b + sep);
if (inside(pcm, out) || inside(out, pcm)) fail(`--out (${out}) and the checkout (${pcm}) must not contain each other.`);
if (existsSync(out) && readdirSync(out).length > 0 && !existsSync(join(out, "manifest.json"))) {
  fail(`${out} exists and is not a seed directory (no manifest.json) - not deleting it.`);
}

const allCourses = readdirSync(join(pcm, "courses"))
  .filter((n) => !n.startsWith("_") && existsSync(join(pcm, "courses", n, "course.json")))
  .sort();
const courses = opts.courses ?? allCourses;
for (const c of courses) {
  if (!allCourses.includes(c)) fail(`no course "${c}" in ${join(pcm, "courses")}. Have: ${allCourses.join(", ")}`);
}
if (courses.length === 0) fail("no courses to stage.");

// ── Helpers ─────────────────────────────────────────────────────────

/** Files git tracks under `rel`, or null when `pcm` is not a git checkout. */
function trackedFiles(rel) {
  try {
    const raw = execFileSync("git", ["-C", pcm, "ls-files", "-z", "--", rel], {
      maxBuffer: 1 << 28, stdio: ["ignore", "pipe", "ignore"],
    });
    return raw.toString("utf8").split("\0").filter(Boolean).map((p) => join(pcm, ...p.split("/")));
  } catch {
    return null;
  }
}

function walk(dir) {
  const found = [];
  for (const name of readdirSync(dir).sort()) {
    const full = join(dir, name);
    const st = lstatSync(full);
    if (st.isSymbolicLink()) continue;
    if (st.isDirectory()) found.push(...walk(full));
    else if (st.isFile()) found.push(full);
  }
  return found;
}

/** Is this file one the bank reads, as opposed to lab payload? */
function wanted(file, courseDir) {
  const parts = relative(courseDir, file).split(sep);
  const name = parts[parts.length - 1];
  if (parts.slice(0, -1).some((p) => SKIP_DIRS.has(p))) return false;
  if (SECRETISH.test(name)) return false;
  return KEEP_EXT.test(name);
}

// ── Stage ───────────────────────────────────────────────────────────

rmSync(out, { recursive: true, force: true });
mkdirSync(coursesOut, { recursive: true });
console.log(`\n  Staging the seed from ${pcm}`);

const hash = createHash("sha1");
let fileCount = 0;
let byteCount = 0;
const summary = [];

for (const id of courses) {
  const courseDir = join(pcm, "courses", id);
  let files = trackedFiles(`courses/${id}`);
  if (files === null) {
    console.log(`  [!]  ${pcm} is not a git checkout: ${id} staged by file type, not by what git tracks`);
    files = walk(courseDir);
  } else if (files.length === 0) {
    fail(`git tracks no files under courses/${id}. Commit the course, or pass --pcm a copy that is not a repository.`);
  }
  files = files.filter((f) => wanted(f, courseDir));
  if (!files.some((f) => relative(courseDir, f) === "course.json")) {
    fail(`courses/${id} has no tracked course.json after filtering - nothing the bank can read.`);
  }
  for (const file of files) {
    const dest = join(coursesOut, id, relative(courseDir, file));
    mkdirSync(dirname(dest), { recursive: true });
    copyFileSync(file, dest);
    fileCount++;
    byteCount += statSync(dest).size;
    hash.update(`${id}/${relative(courseDir, file)}`).update(readFileSync(dest));
  }
  summary.push({ id, files: files.length });
}

let commit = null;
try {
  commit = execFileSync("git", ["-C", pcm, "rev-parse", "HEAD"], { stdio: ["ignore", "pipe", "ignore"] }).toString().trim();
} catch { /* not a repository */ }
let pcmVersion = null;
try { pcmVersion = JSON.parse(readFileSync(join(pcm, "package.json"), "utf8")).version ?? null; } catch { /* no package.json */ }

writeFileSync(
  join(out, "manifest.json"),
  JSON.stringify({
    schema: 1,
    id: hash.digest("hex").slice(0, 16),
    builtAt: new Date().toISOString(),
    pcmVersion,
    pcmCommit: commit,
    courses: summary,
  }, null, 2) + "\n",
);

console.log(`  [ok] staged ${courses.length} course(s), ${fileCount} file(s), ${(byteCount / 1048576).toFixed(1)} MB`);
console.log(`       -> ${out}\n`);
