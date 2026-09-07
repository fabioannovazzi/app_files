import assert from "node:assert/strict";
import { mkdtemp, realpath, rename, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { observeDownloadDirectory } from "../plugins/browser-automation/scripts/download_directory.mjs";

async function setup(t) {
  const directory = await mkdtemp(join(tmpdir(), "vera-download-test-"));
  t.after(() => rm(directory, { recursive: true, force: true }));
  return realpath(directory);
}
const quick = { timeoutMs: 150, stableMs: 10, pollMs: 5 };

test("new file verified without reading or returning preexisting documents", async (t) => {
  const directory = await setup(t);
  await writeFile(join(directory, "private-old.xml"), "old");
  const observation = await observeDownloadDirectory(directory);
  t.after(observation.close);
  await writeFile(join(directory, "new.xml"), "abc");
  assert.deepEqual(await observation.wait(quick), {
    path: join(directory, "new.xml"), byte_length: 3,
    sha256: "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
  });
});

test("partial file must be renamed before acceptance", async (t) => {
  const directory = await setup(t);
  const observation = await observeDownloadDirectory(directory);
  t.after(observation.close);
  await writeFile(join(directory, "new.zip.crdownload"), "abc");
  await assert.rejects(observation.wait(quick), /download-file-not-completed/);
  await rename(join(directory, "new.zip.crdownload"), join(directory, "new.zip"));
  assert.equal((await observation.wait(quick)).byte_length, 3);
});

test("multiple arrivals are ambiguous and never accepted", async (t) => {
  const directory = await setup(t);
  const observation = await observeDownloadDirectory(directory);
  t.after(observation.close);
  await writeFile(join(directory, "one.xml"), "one");
  await writeFile(join(directory, "two.xml"), "two");
  await assert.rejects(observation.wait(quick), /download-directory-ambiguous/);
});

test("overwriting an old file is not evidence of a new download", async (t) => {
  const directory = await setup(t);
  await writeFile(join(directory, "old.xml"), "old");
  const observation = await observeDownloadDirectory(directory);
  t.after(observation.close);
  await writeFile(join(directory, "old.xml"), "changed");
  await assert.rejects(observation.wait(quick), /download-file-not-completed/);
});

for (const extension of ["crdownload", "part", "partial", "tmp"]) {
  test(`preexisting .${extension} does not block a new completed download`, async (t) => {
    const directory = await setup(t);
    await writeFile(join(directory, `old.${extension}`), "old");
    const observation = await observeDownloadDirectory(directory);
    t.after(observation.close);
    await writeFile(join(directory, "new.zip"), "abc");
    assert.equal((await observation.wait(quick)).path, join(directory, "new.zip"));
  });
}

test("old partial cannot be mistaken for the requested download when it completes", async (t) => {
  const directory = await setup(t);
  await writeFile(join(directory, "old.zip.crdownload"), "old");
  const observation = await observeDownloadDirectory(directory);
  t.after(observation.close);
  await rename(join(directory, "old.zip.crdownload"), join(directory, "old.zip"));
  await assert.rejects(observation.wait(quick), /download-directory-ambiguous/);
});

test("ignoring an old partial does not accept a new unfinished download", async (t) => {
  const directory = await setup(t);
  await writeFile(join(directory, "old.part"), "old");
  const observation = await observeDownloadDirectory(directory);
  t.after(observation.close);
  await writeFile(join(directory, "new.zip.crdownload"), "abc");
  await assert.rejects(observation.wait(quick), /download-file-not-completed/);
});

test("cooperating runners cannot share an observation window", async (t) => {
  const directory = await setup(t);
  const observation = await observeDownloadDirectory(directory);
  t.after(observation.close);
  await assert.rejects(observeDownloadDirectory(directory), /download-directory-busy/);
});

test("new symlink is rejected without reading its target", async (t) => {
  const directory = await setup(t);
  await writeFile(join(directory, "private.xml"), "private");
  const observation = await observeDownloadDirectory(directory);
  t.after(observation.close);
  await symlink(join(directory, "private.xml"), join(directory, "new.xml"));
  await assert.rejects(observation.wait(quick), /download-path-not-regular-file/);
});
