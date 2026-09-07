/** Local file identity and hashes are mechanically verifiable; no invoice interpretation. */
import { createHash } from "node:crypto";
import { constants } from "node:fs";
import { lstat, mkdir, open, readdir, realpath, rmdir } from "node:fs/promises";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

export const DEFAULT_DOWNLOAD_DIRECTORY = join(homedir(), "Downloads");
const PARTIAL = /\.(crdownload|part|partial|tmp)$/i;
const identity = (s) => `${s.dev}:${s.ino}:${s.size}:${s.mtimeMs}:${s.ctimeMs}`;

export class DownloadDirectoryError extends Error {
  constructor(code) {
    super(code);
    this.evidenceCode = code;
  }
}

/** Snapshot names only; never read pre-existing documents. Lock cooperating runners. */
export async function observeDownloadDirectory(directory) {
  let root;
  try {
    root = await realpath(directory);
  } catch {
    throw new DownloadDirectoryError("download-directory-unavailable");
  }
  const key = createHash("sha256").update(root).digest("hex");
  const lock = join(tmpdir(), `vera-download-${key}.lock`);
  try {
    await mkdir(lock, { mode: 0o700 });
  } catch {
    throw new DownloadDirectoryError("download-directory-busy");
  }
  const close = () => rmdir(lock);
  try {
    const baseline = new Set(await readdir(root));
    if ([...baseline].some((name) => PARTIAL.test(name))) {
      throw new DownloadDirectoryError("download-already-in-progress");
    }
    return {
      close,
      async wait({ timeoutMs = 10000, stableMs = 1000, pollMs = 100 } = {}) {
        const deadline = performance.now() + timeoutMs;
        let previous = null;
        let stableSince = 0;
        const observedFinalNames = new Set();
        while (performance.now() < deadline) {
          const arrivals = (await readdir(root)).filter((name) => !baseline.has(name));
          const finished = arrivals.filter((name) => !PARTIAL.test(name));
          for (const name of finished) observedFinalNames.add(name);
          if (observedFinalNames.size > 1) {
            throw new DownloadDirectoryError("download-directory-ambiguous");
          }
          if (finished.length === 1 && !arrivals.some((name) => PARTIAL.test(name))) {
            const path = join(root, finished[0]);
            let before;
            try {
              before = await lstat(path);
            } catch (error) {
              if (error.code !== "ENOENT") throw error;
            }
            if (before) {
              if (!before.isFile() || before.isSymbolicLink()) {
                throw new DownloadDirectoryError("download-path-not-regular-file");
              }
              const signature = `${finished[0]}:${identity(before)}`;
              if (signature !== previous) {
                previous = signature;
                stableSince = performance.now();
              } else if (performance.now() - stableSince >= stableMs) {
                const handle = await open(path, constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0));
                try {
                  if (identity(await handle.stat()) !== identity(before)) {
                    throw new DownloadDirectoryError("download-file-changed");
                  }
                  const hash = createHash("sha256");
                  let bytes = 0;
                  for await (const chunk of handle.createReadStream({ autoClose: false })) {
                    bytes += chunk.length;
                    hash.update(chunk);
                  }
                  if (bytes !== before.size || identity(await handle.stat()) !== identity(before)
                      || identity(await lstat(path)) !== identity(before)) {
                    throw new DownloadDirectoryError("download-file-changed");
                  }
                  const finalArrivals = (await readdir(root)).filter((name) => !baseline.has(name));
                  if (finalArrivals.length !== 1 || finalArrivals[0] !== finished[0]) {
                    throw new DownloadDirectoryError("download-directory-ambiguous");
                  }
                  return { path, byte_length: bytes, sha256: hash.digest("hex") };
                } finally {
                  await handle.close();
                }
              }
            }
          } else {
            previous = null;
          }
          await delay(pollMs);
        }
        throw new DownloadDirectoryError("download-file-not-completed");
      },
    };
  } catch (error) {
    await close();
    throw error;
  }
}
