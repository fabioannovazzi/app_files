"use strict";

// Exact inventory and SHA-256 comparisons prevent altered package code from
// starting. Verification is synchronous and leaves no process or code snapshot.
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { createHash } = require("node:crypto");
let verifiedFiles;

function verify(root) {
  const manifest = "execution-files.json";
  const indexPath = path.join(root, manifest);
  const development = fs.existsSync(path.resolve(root, "../../.git")) &&
    fs.existsSync(path.resolve(root, "../_shared"));
  if (!fs.existsSync(indexPath) && development) return;

  function realDirectories(directory) {
    for (;;) {
      const info = fs.lstatSync(directory);
      if (!info.isDirectory() || info.isSymbolicLink())
        throw new Error(`Non-directory installation ancestor: ${directory}`);
      const parent = path.dirname(directory);
      if (parent === directory) break;
      directory = parent;
    }
  }
  function identity(info) {
    return [info.dev, info.ino, info.mode, info.size, info.mtimeNs, info.ctimeNs, info.nlink].join(":");
  }
  function read(file) {
    realDirectories(path.dirname(file));
    const before = fs.lstatSync(file, { bigint: true });
    if (!before.isFile() || before.isSymbolicLink())
      throw new Error(`Non-regular installation file: ${file}`);
    const fd = fs.openSync(file, fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW || 0));
    try {
      if (identity(before) !== identity(fs.fstatSync(fd, { bigint: true })))
        throw new Error(`Installation file changed before read: ${file}`);
      const bytes = fs.readFileSync(fd);
      if (identity(before) !== identity(fs.fstatSync(fd, { bigint: true })) ||
          identity(before) !== identity(fs.lstatSync(file, { bigint: true })))
        throw new Error(`Installation file changed during read: ${file}`);
      realDirectories(path.dirname(file));
      return bytes;
    } finally { fs.closeSync(fd); }
  }

  const indexBytes = read(indexPath);
  const index = JSON.parse(indexBytes);
  if (index.schema_version !== 1 || !index.files ||
      typeof index.files !== "object" || Array.isArray(index.files))
    throw new Error("Invalid execution digest index");
  const expected = new Map(Object.entries(index.files));
  const directories = new Set();
  for (const [name, digest] of expected) {
    if (!name || name === manifest || path.posix.isAbsolute(name) ||
        path.win32.parse(name).root || name.includes("\\") ||
        name.split("/").some(part => !part || part === "." || part === "..") ||
        typeof digest !== "string" || !/^[0-9a-f]{64}$/.test(digest))
      throw new Error("Invalid execution digest index entry");
    for (let parent = path.posix.dirname(name); parent !== "."; parent = path.posix.dirname(parent))
      directories.add(parent);
  }
  const observed = new Set();
  const observedDirectories = new Set();
  function inventory(directory) {
    for (const name of fs.readdirSync(directory)) {
      const file = path.join(directory, name);
      const relative = path.relative(root, file).split(path.sep).join("/");
      const info = fs.lstatSync(file);
      if (info.isSymbolicLink()) throw new Error(`Symlink in installation: ${relative}`);
      if (info.isDirectory()) {
        if (relative === ".in_use") {
          for (const marker of fs.readdirSync(file)) {
            const lease = fs.lstatSync(path.join(file, marker));
            if (!/^[0-9]+$/.test(marker) || !lease.isFile() || lease.isSymbolicLink() || lease.nlink !== 1)
              throw new Error("Invalid host use marker");
          }
        } else if (name !== "__pycache__") {
          observedDirectories.add(relative);
          inventory(file);
        }
      } else if (info.isFile()) {
        if (/\.py[co]$/.test(name)) {
          if (info.nlink !== 1) throw new Error("Hardlinked bytecode is not repairable");
        } else if (relative !== manifest) {
          observed.add(relative);
          if (!expected.has(relative)) throw new Error(`Installation inventory mismatch: ${relative}`);
          if (createHash("sha256").update(read(file)).digest("hex") !== expected.get(relative))
            throw new Error(`Installation content mismatch: ${relative}`);
        }
      } else throw new Error(`Non-regular installation entry: ${relative}`);
    }
  }
  inventory(root);
  if (observed.size !== expected.size || observedDirectories.size !== directories.size ||
      [...directories].some(name => !observedDirectories.has(name)))
    throw new Error("Installation inventory mismatch");
  if (!indexBytes.equals(read(indexPath))) throw new Error("Execution digest index changed during verification");
  process.env.VERA_EXECUTION_PACKAGE_ID = createHash("sha256").update(indexBytes).digest("hex");
  verifiedFiles = { root, expected, read };
}

function componentRoot(root, component, original) {
  // Some component integrity validators require single-link implementation
  // files. Copy only that component when a host uses hardlinks; no gateway,
  // old-release routing or full-product update snapshot is involved.
  if (verifiedFiles?.root !== root) return { root: original, cleanup() {} };
  const prefix = `modules/${component}/`;
  const entries = [...verifiedFiles.expected].filter(([name]) => name.startsWith(prefix));
  if (!entries.some(([name]) => fs.lstatSync(path.join(root, name)).nlink > 1))
    return { root: original, cleanup() {} };
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "vera-component-"));
  const cleanup = () => fs.rmSync(temporary, { recursive: true, force: true });
  try {
    for (const [name, digest] of entries) {
      const bytes = verifiedFiles.read(path.join(root, name));
      if (createHash("sha256").update(bytes).digest("hex") !== digest)
        throw new Error(`Installation content mismatch: ${name}`);
      const target = path.join(temporary, name.slice(prefix.length));
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.writeFileSync(target, bytes, { flag: "wx", mode: 0o600 });
    }
    return { root: temporary, cleanup };
  } catch (error) { cleanup(); throw error; }
}

module.exports = { verify, componentRoot };
