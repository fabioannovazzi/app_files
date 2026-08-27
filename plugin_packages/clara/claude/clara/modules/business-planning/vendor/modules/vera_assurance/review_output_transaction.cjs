"use strict";

const fs = require("node:fs");
const path = require("node:path");

function isPlainObject(value) {
  return value != null && typeof value === "object" && !Array.isArray(value);
}

// BEGIN EMBEDDABLE REVIEW OUTPUT TRANSACTION
const GENERATED_REVIEW_TRANSACTION_LIMITS = {
  maxEntryCount: 20_000,
  maxFileBytes: 128 * 1024 * 1024,
  maxTotalBytes: 512 * 1024 * 1024,
};

let generatedReviewWriteCounter = 0;
const GENERATED_REVIEW_TRANSACTION_ERROR_KIND = Symbol(
  "generated-review-transaction-error-kind",
);
const GENERATED_REVIEW_TRANSACTION_OPERATION_ERROR = Symbol(
  "generated-review-transaction-operation-error",
);

function generatedReviewPathEntryStat(targetPath) {
  try {
    return fs.lstatSync(targetPath);
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
}

function generatedReviewPathEntryExists(targetPath) {
  return generatedReviewPathEntryStat(targetPath) !== null;
}

function generatedReviewRemoveExactPath(targetPath) {
  const entry = generatedReviewPathEntryStat(targetPath);
  if (!entry) return;
  if (entry.isDirectory() && !entry.isSymbolicLink()) {
    fs.rmSync(targetPath, {
      recursive: true,
      force: true,
      maxRetries: 3,
      retryDelay: 25,
    });
    return;
  }
  fs.unlinkSync(targetPath);
}

function generatedReviewDirectoryIdentity(targetPath) {
  const entry = generatedReviewPathEntryStat(targetPath);
  if (!entry || !entry.isDirectory() || entry.isSymbolicLink()) {
    throw new Error("Review transaction root must be a real directory.");
  }
  return { dev: entry.dev, ino: entry.ino };
}

function generatedReviewIdentityMatches(entry, identity) {
  return (
    entry != null &&
    entry.isDirectory() &&
    !entry.isSymbolicLink() &&
    entry.dev === identity.dev &&
    entry.ino === identity.ino
  );
}

function generatedReviewTrackedRootsWithinParent(outputParent, identity) {
  generatedReviewValidateRealDirectoryAncestors(outputParent);
  const matches = [];
  for (const name of fs.readdirSync(outputParent).sort()) {
    const candidate = path.join(outputParent, name);
    const entry = generatedReviewPathEntryStat(candidate);
    if (generatedReviewIdentityMatches(entry, identity)) {
      matches.push(candidate);
    }
  }
  return matches;
}

function generatedReviewRemoveTrackedRootWithinParent(
  outputParent,
  expectedPath,
  identity,
) {
  const matches = generatedReviewTrackedRootsWithinParent(
    outputParent,
    identity,
  );
  const expected = path.resolve(expectedPath);
  const relocated = matches.some(
    (candidate) => path.resolve(candidate) !== expected,
  );
  for (const candidate of matches) {
    generatedReviewRemoveExactPath(candidate);
  }
  if (
    generatedReviewTrackedRootsWithinParent(outputParent, identity).length
  ) {
    throw new Error("Review transaction root cleanup did not close.");
  }
  return { found: matches.length > 0, relocated };
}

function generatedReviewValidateRealDirectoryAncestors(targetDir) {
  const resolved = path.resolve(targetDir);
  const parsed = path.parse(resolved);
  let current = parsed.root;
  for (const component of resolved
    .slice(parsed.root.length)
    .split(path.sep)
    .filter(Boolean)) {
    current = path.join(current, component);
    const entry = generatedReviewPathEntryStat(current);
    if (!entry || !entry.isDirectory() || entry.isSymbolicLink()) {
      throw new Error("Review output parent must be a real directory.");
    }
  }
}

function generatedReviewCanonicalRelativePath(value) {
  if (
    typeof value !== "string" ||
    value !== value.trim() ||
    !value ||
    /[\u0000-\u001f\u007f\\]/.test(value) ||
    path.posix.isAbsolute(value)
  ) {
    throw new Error("Review transaction received an invalid output path.");
  }
  const normalized = path.posix.normalize(value);
  if (
    normalized !== value ||
    normalized === "." ||
    normalized === ".." ||
    normalized.startsWith("../")
  ) {
    throw new Error("Review transaction received an invalid output path.");
  }
  return normalized;
}

function generatedReviewAbsolutePath(root, relativePath) {
  const canonical = generatedReviewCanonicalRelativePath(relativePath);
  return path.join(root, ...canonical.split("/"));
}

function generatedReviewCaptureDirectoryImage(outputDir) {
  const rootEntry = generatedReviewPathEntryStat(outputDir);
  if (!rootEntry || !rootEntry.isDirectory() || rootEntry.isSymbolicLink()) {
    throw new Error("Review output must be a real directory.");
  }
  const directories = [];
  const files = [];
  let entryCount = 0;
  let totalBytes = 0;
  const pending = [outputDir];
  while (pending.length) {
    const current = pending.pop();
    for (const name of fs.readdirSync(current).sort()) {
      entryCount += 1;
      if (entryCount > GENERATED_REVIEW_TRANSACTION_LIMITS.maxEntryCount) {
        throw new Error("Review output exceeds the transaction entry limit.");
      }
      const candidate = path.join(current, name);
      const observed = generatedReviewPathEntryStat(candidate);
      if (!observed || observed.isSymbolicLink()) {
        throw new Error("Review output contains an unsafe filesystem entry.");
      }
      const relativePath = path
        .relative(outputDir, candidate)
        .split(path.sep)
        .join("/");
      generatedReviewCanonicalRelativePath(relativePath);
      if (observed.isDirectory()) {
        directories.push({
          path: relativePath,
          mode: observed.mode & 0o7777,
        });
        pending.push(candidate);
        continue;
      }
      if (
        !observed.isFile() ||
        observed.nlink !== 1 ||
        observed.size > GENERATED_REVIEW_TRANSACTION_LIMITS.maxFileBytes
      ) {
        throw new Error("Review output contains an unsupported file.");
      }
      totalBytes += observed.size;
      if (totalBytes > GENERATED_REVIEW_TRANSACTION_LIMITS.maxTotalBytes) {
        throw new Error("Review output exceeds the transaction byte limit.");
      }
      const noFollow = fs.constants.O_NOFOLLOW || 0;
      let descriptor;
      try {
        descriptor = fs.openSync(candidate, fs.constants.O_RDONLY | noFollow);
        const before = fs.fstatSync(descriptor);
        const payload = fs.readFileSync(descriptor);
        const after = fs.fstatSync(descriptor);
        if (
          !before.isFile() ||
          before.nlink !== 1 ||
          before.dev !== observed.dev ||
          before.ino !== observed.ino ||
          before.dev !== after.dev ||
          before.ino !== after.ino ||
          before.size !== after.size ||
          before.mtimeMs !== after.mtimeMs ||
          payload.length !== after.size
        ) {
          throw new Error("Review output changed during transaction capture.");
        }
        files.push({
          path: relativePath,
          mode: after.mode & 0o7777,
          payload,
        });
      } finally {
        if (descriptor !== undefined) fs.closeSync(descriptor);
      }
    }
  }
  directories.sort((left, right) => left.path.localeCompare(right.path));
  files.sort((left, right) => left.path.localeCompare(right.path));
  return {
    rootMode: rootEntry.mode & 0o7777,
    directories,
    files,
  };
}

function generatedReviewImagesEqual(left, right) {
  if (left == null || right == null) return left === right;
  if (
    left.rootMode !== right.rootMode ||
    left.directories.length !== right.directories.length ||
    left.files.length !== right.files.length
  ) {
    return false;
  }
  for (let index = 0; index < left.directories.length; index += 1) {
    const leftEntry = left.directories[index];
    const rightEntry = right.directories[index];
    if (
      leftEntry.path !== rightEntry.path ||
      leftEntry.mode !== rightEntry.mode
    ) {
      return false;
    }
  }
  for (let index = 0; index < left.files.length; index += 1) {
    const leftEntry = left.files[index];
    const rightEntry = right.files[index];
    if (
      leftEntry.path !== rightEntry.path ||
      leftEntry.mode !== rightEntry.mode ||
      !leftEntry.payload.equals(rightEntry.payload)
    ) {
      return false;
    }
  }
  return true;
}

function generatedReviewMaterializeDirectoryImage(targetDir, image) {
  if (generatedReviewPathEntryExists(targetDir)) {
    throw new Error("Review transaction target already exists.");
  }
  fs.mkdirSync(targetDir, { mode: 0o700 });
  const effectiveImage =
    image || { rootMode: 0o755, directories: [], files: [] };
  for (const directory of [...effectiveImage.directories].sort(
    (left, right) =>
      left.path.split("/").length - right.path.split("/").length ||
      left.path.localeCompare(right.path),
  )) {
    fs.mkdirSync(generatedReviewAbsolutePath(targetDir, directory.path), {
      mode: 0o700,
    });
  }
  for (const file of effectiveImage.files) {
    const target = generatedReviewAbsolutePath(targetDir, file.path);
    generatedReviewValidateRealDirectoryAncestors(path.dirname(target));
    const noFollow = fs.constants.O_NOFOLLOW || 0;
    const descriptor = fs.openSync(
      target,
      fs.constants.O_WRONLY |
        fs.constants.O_CREAT |
        fs.constants.O_EXCL |
        noFollow,
      0o600,
    );
    try {
      fs.writeFileSync(descriptor, file.payload);
      fs.fsyncSync(descriptor);
    } finally {
      fs.closeSync(descriptor);
    }
    fs.chmodSync(target, file.mode);
  }
  for (const directory of [...effectiveImage.directories].sort(
    (left, right) =>
      right.path.split("/").length - left.path.split("/").length ||
      left.path.localeCompare(right.path),
  )) {
    fs.chmodSync(
      generatedReviewAbsolutePath(targetDir, directory.path),
      directory.mode,
    );
  }
  fs.chmodSync(targetDir, effectiveImage.rootMode);
  const replay = generatedReviewCaptureDirectoryImage(targetDir);
  if (!generatedReviewImagesEqual(effectiveImage, replay)) {
    throw new Error("Review transaction materialization did not replay.");
  }
}

function generatedReviewWritableLeafSignature(targetPath) {
  const entry = generatedReviewPathEntryStat(targetPath);
  if (!entry) return null;
  if (entry.isSymbolicLink() || !entry.isFile() || entry.nlink !== 1) {
    throw new Error("Review output contains an unsafe writable file.");
  }
  return [
    entry.dev,
    entry.ino,
    entry.size,
    entry.mtimeMs,
    entry.mode,
  ].join(":");
}

function generatedReviewAtomicWriteFileSync(
  targetPath,
  payload,
  encoding = null,
) {
  generatedReviewValidateRealDirectoryAncestors(path.dirname(targetPath));
  const initialSignature = generatedReviewWritableLeafSignature(targetPath);
  const targetEntry = generatedReviewPathEntryStat(targetPath);
  const targetMode = targetEntry ? targetEntry.mode & 0o7777 : 0o644;
  generatedReviewWriteCounter += 1;
  const tempPath = path.join(
    path.dirname(targetPath),
    `.${path.basename(targetPath)}.generated-review-write-${process.pid}-${generatedReviewWriteCounter}`,
  );
  let descriptor;
  let tempExists = false;
  try {
    const noFollow = fs.constants.O_NOFOLLOW || 0;
    descriptor = fs.openSync(
      tempPath,
      fs.constants.O_WRONLY |
        fs.constants.O_CREAT |
        fs.constants.O_EXCL |
        noFollow,
      targetMode,
    );
    tempExists = true;
    fs.writeFileSync(
      descriptor,
      payload,
      encoding ? { encoding } : undefined,
    );
    fs.fchmodSync(descriptor, targetMode);
    fs.fsyncSync(descriptor);
    fs.closeSync(descriptor);
    descriptor = undefined;
    if (
      generatedReviewWritableLeafSignature(targetPath) !== initialSignature
    ) {
      throw new Error("Review output changed during an atomic write.");
    }
    generatedReviewValidateRealDirectoryAncestors(path.dirname(targetPath));
    fs.renameSync(tempPath, targetPath);
    tempExists = false;
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
    if (tempExists) {
      try {
        fs.unlinkSync(tempPath);
      } catch (error) {
        if (error?.code !== "ENOENT") throw error;
      }
    }
  }
}

function generatedReviewImageEntryMaps(image) {
  const directoryModes = new Map();
  const files = new Map();
  if (!image) {
    return {
      rootMode: 0o755,
      directoryModes,
      files,
    };
  }
  for (const entry of image.directories) {
    directoryModes.set(entry.path, entry.mode);
  }
  for (const entry of image.files) {
    files.set(entry.path, entry);
  }
  return {
    rootMode: image.rootMode,
    directoryModes,
    files,
  };
}

function generatedReviewAuthorizedPathSet(paths) {
  if (!Array.isArray(paths)) {
    throw new Error("Review transaction requires an authorized write set.");
  }
  const authorized = new Set();
  for (const value of paths) {
    authorized.add(generatedReviewCanonicalRelativePath(value));
  }
  return authorized;
}

function generatedReviewDirectoryIsAuthorized(relativePath, authorized) {
  if (authorized.has(relativePath)) return true;
  const prefix = `${relativePath}/`;
  return Array.from(authorized).some((entry) => entry.startsWith(prefix));
}

function generatedReviewValidateAuthorizedChanges(
  beforeImage,
  afterImage,
  authorizedWritePaths,
) {
  const authorized = generatedReviewAuthorizedPathSet(authorizedWritePaths);
  const before = generatedReviewImageEntryMaps(beforeImage);
  const after = generatedReviewImageEntryMaps(afterImage);
  if (before.rootMode !== after.rootMode) {
    throw new Error("Review transaction changed the output directory mode.");
  }
  const directoryPaths = new Set([
    ...before.directoryModes.keys(),
    ...after.directoryModes.keys(),
  ]);
  for (const relativePath of directoryPaths) {
    const beforeMode = before.directoryModes.get(relativePath);
    const afterMode = after.directoryModes.get(relativePath);
    if (beforeMode === afterMode) continue;
    if (
      beforeMode != null ||
      afterMode == null ||
      !generatedReviewDirectoryIsAuthorized(relativePath, authorized)
    ) {
      throw new Error("Review transaction changed an unauthorized directory.");
    }
  }
  const filePaths = new Set([...before.files.keys(), ...after.files.keys()]);
  for (const relativePath of filePaths) {
    const beforeEntry = before.files.get(relativePath);
    const afterEntry = after.files.get(relativePath);
    const unchanged =
      beforeEntry != null &&
      afterEntry != null &&
      beforeEntry.mode === afterEntry.mode &&
      beforeEntry.payload.equals(afterEntry.payload);
    if (unchanged) continue;
    if (!authorized.has(relativePath)) {
      throw new Error("Review transaction changed an unauthorized file.");
    }
    if (
      beforeEntry != null &&
      afterEntry != null &&
      beforeEntry.mode !== afterEntry.mode
    ) {
      throw new Error("Review transaction changed an artifact mode.");
    }
  }
  return authorized;
}

function generatedReviewTransactionEnvelope(result, authorizedWritePaths) {
  return { result, authorizedWritePaths };
}

function generatedReviewArgsForWorkingOutput(inputArgs, workingOutputDir) {
  const runIntake = isPlainObject(inputArgs.run_intake)
    ? { ...inputArgs.run_intake, output_dir: workingOutputDir }
    : { output_dir: workingOutputDir };
  return { ...inputArgs, run_intake: runIntake };
}

function generatedReviewRewriteOutputPaths(
  value,
  workingOutputDir,
  canonicalOutputDir,
) {
  if (Array.isArray(value)) {
    return value.map((entry) =>
      generatedReviewRewriteOutputPaths(
        entry,
        workingOutputDir,
        canonicalOutputDir,
      ),
    );
  }
  if (value != null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, entry]) => [
        key,
        generatedReviewRewriteOutputPaths(
          entry,
          workingOutputDir,
          canonicalOutputDir,
        ),
      ]),
    );
  }
  if (typeof value !== "string") return value;
  if (value === workingOutputDir) return canonicalOutputDir;
  const prefix = `${workingOutputDir}${path.sep}`;
  if (!value.startsWith(prefix)) return value;
  return path.join(canonicalOutputDir, value.slice(prefix.length));
}

function generatedReviewCollectApplicationWritePaths(result) {
  const paths = new Set([
    "ui_decisions.json",
    "applied_decisions.json",
    "final_artifacts.json",
    "run_intake.json",
    "review_handoff.md",
  ]);
  function add(value) {
    if (Array.isArray(value)) {
      for (const entry of value) add(entry);
      return;
    }
    if (typeof value !== "string" || !value) return;
    paths.add(generatedReviewCanonicalRelativePath(value));
  }
  const applied = isPlainObject(result?.applied_decisions)
    ? result.applied_decisions
    : {};
  const finalArtifacts = isPlainObject(result?.final_artifacts)
    ? result.final_artifacts
    : {};
  const application = isPlainObject(finalArtifacts.review_application)
    ? finalArtifacts.review_application
    : {};
  for (const source of [result, applied, application]) {
    for (const fieldName of [
      "revision_paths",
      "target_update_paths",
      "structured_update_paths",
      "native_regeneration_paths",
      "native_regenerated_paths",
      "downstream_regenerated_paths",
      "original_backup_paths",
      "backup_paths",
    ]) {
      add(source?.[fieldName]);
    }
  }
  for (const effect of Array.isArray(applied.effects) ? applied.effects : []) {
    if (!isPlainObject(effect)) continue;
    for (const fieldName of [
      "revision_artifact",
      "original_artifact_backup",
      "derived_native_regeneration_paths",
      "native_regenerated_paths",
    ]) {
      add(effect[fieldName]);
    }
  }
  return Array.from(paths);
}

function generatedReviewWorkflowTransactionOptions(kind, inputArgs) {
  if (typeof workflowReviewTransactionOptions !== "function") return {};
  const options = workflowReviewTransactionOptions(kind, inputArgs);
  if (options == null) return {};
  if (!isPlainObject(options)) {
    throw new Error("Workflow review transaction options must be an object.");
  }
  return options;
}

function generatedReviewRestoreFromTrustedImage(
  outputDir,
  trustedImage,
  outputParent,
) {
  // Recovery is deliberately created only after the untrusted operation has
  // returned. It never depends on a transaction tree that the operation knew.
  const recoveryRoot = fs.mkdtempSync(
    path.join(outputParent, ".generated-review-recovery-"),
  );
  fs.chmodSync(recoveryRoot, 0o700);
  const recoveryIdentity =
    generatedReviewDirectoryIdentity(recoveryRoot);
  const recoveryOutput = path.join(recoveryRoot, "output");
  let restored = false;
  try {
    if (trustedImage) {
      generatedReviewMaterializeDirectoryImage(
        recoveryOutput,
        trustedImage,
      );
      const recoveryReplay =
        generatedReviewCaptureDirectoryImage(recoveryOutput);
      if (!generatedReviewImagesEqual(trustedImage, recoveryReplay)) {
        throw new Error("Review output recovery did not replay.");
      }
    }
    generatedReviewRemoveExactPath(outputDir);
    if (trustedImage) {
      if (generatedReviewPathEntryExists(outputDir)) {
        throw new Error("Review output changed during recovery.");
      }
      fs.renameSync(recoveryOutput, outputDir);
      const canonicalReplay =
        generatedReviewCaptureDirectoryImage(outputDir);
      if (!generatedReviewImagesEqual(trustedImage, canonicalReplay)) {
        throw new Error("Review output recovery did not close.");
      }
    } else if (generatedReviewPathEntryExists(outputDir)) {
      throw new Error("Review output recovery did not restore absence.");
    }
    restored = true;
  } finally {
    const cleanup = generatedReviewRemoveTrackedRootWithinParent(
      outputParent,
      recoveryRoot,
      recoveryIdentity,
    );
    if (!cleanup.found || cleanup.relocated) {
      throw new Error("Review output recovery root changed.");
    }
  }
  if (!restored) {
    throw new Error("Review output recovery did not close.");
  }
}

function generatedReviewCanonicalMatchesTrusted(outputDir, trustedImage) {
  if (!trustedImage) {
    return !generatedReviewPathEntryExists(outputDir);
  }
  try {
    return generatedReviewImagesEqual(
      trustedImage,
      generatedReviewCaptureDirectoryImage(outputDir),
    );
  } catch {
    return false;
  }
}

function generatedReviewRunOutputTransaction(
  outputDir,
  operation,
  options = {},
) {
  if (!outputDir) {
    const envelope = operation({
      workingOutputDir: null,
      canonicalOutputDir: null,
      trustedImage: null,
    });
    if (
      !isPlainObject(envelope) ||
      !Object.hasOwn(envelope, "result") ||
      !Array.isArray(envelope.authorizedWritePaths)
    ) {
      throw new Error("Review transaction operation returned an invalid result.");
    }
    return envelope.result;
  }
  const resolvedOutputDir = path.resolve(outputDir);
  if (resolvedOutputDir === path.parse(resolvedOutputDir).root) {
    throw new Error("Review output transaction rejected the output path.");
  }
  const outputParent = path.dirname(resolvedOutputDir);
  generatedReviewValidateRealDirectoryAncestors(outputParent);
  const outputExisted = generatedReviewPathEntryExists(resolvedOutputDir);
  const trustedImage = outputExisted
    ? generatedReviewCaptureDirectoryImage(resolvedOutputDir)
    : null;
  let transactionRoot = null;
  let transactionIdentity = null;
  let workingOutputDir = null;
  let commitRoot = null;
  let commitIdentity = null;
  let canonicalDetached = false;
  let committed = false;
  try {
    transactionRoot = fs.mkdtempSync(
      path.join(outputParent, ".generated-review-transaction-"),
    );
    fs.chmodSync(transactionRoot, 0o700);
    transactionIdentity =
      generatedReviewDirectoryIdentity(transactionRoot);
    workingOutputDir = path.join(transactionRoot, "working");
    generatedReviewMaterializeDirectoryImage(
      workingOutputDir,
      trustedImage,
    );
    if (
      !generatedReviewCanonicalMatchesTrusted(
        resolvedOutputDir,
        trustedImage,
      )
    ) {
      throw new Error("Review output changed before transaction start.");
    }
    const envelope = operation({
      workingOutputDir,
      canonicalOutputDir: resolvedOutputDir,
      trustedImage,
    });
    if (
      !isPlainObject(envelope) ||
      !Object.hasOwn(envelope, "result") ||
      !Array.isArray(envelope.authorizedWritePaths)
    ) {
      throw new Error("Review transaction operation returned an invalid result.");
    }
    const workingImage =
      generatedReviewCaptureDirectoryImage(workingOutputDir);
    const authorized = generatedReviewValidateAuthorizedChanges(
      trustedImage,
      workingImage,
      envelope.authorizedWritePaths,
    );
    if (typeof options.validateWholeTree === "function") {
      options.validateWholeTree({
        canonicalOutputDir: resolvedOutputDir,
        workingOutputDir,
        trustedImage,
        workingImage,
        authorizedWritePaths: authorized,
        result: envelope.result,
      });
    }
    if (
      !generatedReviewCanonicalMatchesTrusted(
        resolvedOutputDir,
        trustedImage,
      )
    ) {
      throw new Error("Review output changed during the transaction.");
    }

    // The validated working tree is now held in parent memory. Close the
    // child-visible tree before creating any commit or recovery material.
    const transactionCleanup =
      generatedReviewRemoveTrackedRootWithinParent(
        outputParent,
        transactionRoot,
        transactionIdentity,
      );
    transactionIdentity = null;
    if (!transactionCleanup.found || transactionCleanup.relocated) {
      throw new Error("Review transaction root changed.");
    }

    commitRoot = fs.mkdtempSync(
      path.join(outputParent, ".generated-review-commit-"),
    );
    fs.chmodSync(commitRoot, 0o700);
    commitIdentity = generatedReviewDirectoryIdentity(commitRoot);
    const commitCandidate = path.join(commitRoot, "candidate");
    const commitBackup = path.join(commitRoot, "trusted-backup");
    generatedReviewMaterializeDirectoryImage(
      commitCandidate,
      workingImage,
    );
    if (
      !generatedReviewCanonicalMatchesTrusted(
        resolvedOutputDir,
        trustedImage,
      )
    ) {
      throw new Error("Review output changed before transaction commit.");
    }
    if (outputExisted) {
      fs.renameSync(resolvedOutputDir, commitBackup);
      canonicalDetached = true;
    } else if (generatedReviewPathEntryExists(resolvedOutputDir)) {
      throw new Error("Review output changed before transaction commit.");
    }
    if (generatedReviewPathEntryExists(resolvedOutputDir)) {
      throw new Error("Review output changed during transaction commit.");
    }
    fs.renameSync(commitCandidate, resolvedOutputDir);
    committed = true;
    const committedImage =
      generatedReviewCaptureDirectoryImage(resolvedOutputDir);
    if (!generatedReviewImagesEqual(workingImage, committedImage)) {
      throw new Error("Review output changed during transaction commit.");
    }
    const commitCleanup = generatedReviewRemoveTrackedRootWithinParent(
      outputParent,
      commitRoot,
      commitIdentity,
    );
    commitIdentity = null;
    if (!commitCleanup.found || commitCleanup.relocated) {
      throw new Error("Review transaction commit root changed.");
    }
    return envelope.result;
  } catch (operationError) {
    let rollbackFailed = false;
    if (
      canonicalDetached ||
      committed ||
      !generatedReviewCanonicalMatchesTrusted(
        resolvedOutputDir,
        trustedImage,
      )
    ) {
      try {
        generatedReviewRestoreFromTrustedImage(
          resolvedOutputDir,
          trustedImage,
          outputParent,
        );
      } catch {
        rollbackFailed = true;
      }
    }
    for (const [trackedPath, trackedIdentity] of [
      [transactionRoot, transactionIdentity],
      [commitRoot, commitIdentity],
    ]) {
      if (!trackedPath || !trackedIdentity) continue;
      try {
        generatedReviewRemoveTrackedRootWithinParent(
          outputParent,
          trackedPath,
          trackedIdentity,
        );
      } catch {
        rollbackFailed = true;
      }
    }
    if (rollbackFailed) {
      const rollbackError = new Error(
        options.rollbackFailureMessage ||
          "Review output transaction could not be restored safely.",
      );
      rollbackError[GENERATED_REVIEW_TRANSACTION_ERROR_KIND] = "rollback";
      throw rollbackError;
    }
    const transactionError = new Error(
      options.failureMessage || "Review output transaction failed safely.",
    );
    transactionError[GENERATED_REVIEW_TRANSACTION_ERROR_KIND] = "operation";
    transactionError[GENERATED_REVIEW_TRANSACTION_OPERATION_ERROR] =
      operationError;
    throw transactionError;
  }
}

function generatedReviewMappedOperationFailure(error, options, fallback) {
  if (
    error?.[GENERATED_REVIEW_TRANSACTION_ERROR_KIND] !== "operation" ||
    typeof options.mapOperationError !== "function"
  ) {
    return fallback;
  }
  try {
    const candidate = options.mapOperationError(
      error[GENERATED_REVIEW_TRANSACTION_OPERATION_ERROR],
    );
    if (
      typeof candidate !== "string" ||
      !candidate ||
      candidate.length > 512 ||
      /[\\/\u0000-\u001f\u007f]/.test(candidate) ||
      /Traceback|\bFile\s+["']|file:|~[\\/]/i.test(candidate)
    ) {
      return fallback;
    }
    return candidate;
  } catch {
    return fallback;
  }
}

function withGeneratedReviewOutputTransaction(
  outputDir,
  operation,
  options = {},
) {
  const failureMessage =
    options.failureMessage || "Review output transaction failed safely.";
  const rollbackFailureMessage =
    options.rollbackFailureMessage ||
    "Review output transaction could not be restored safely.";
  try {
    return generatedReviewRunOutputTransaction(outputDir, operation, {
      ...options,
      failureMessage,
      rollbackFailureMessage,
    });
  } catch (error) {
    const rollbackFailed =
      error?.[GENERATED_REVIEW_TRANSACTION_ERROR_KIND] === "rollback";
    const publicMessage = rollbackFailed
      ? rollbackFailureMessage
      : generatedReviewMappedOperationFailure(
          error,
          options,
          failureMessage,
        );
    throw new Error(publicMessage);
  }
}

// Limitation: this is a bounded transaction contract, not an OS sandbox.
// Same-identity code can copy or move data outside the output parent and a
// hostile background descendant can mutate canonical output after return.
// The parent restores canonical bytes/modes from memory and removes a renamed
// transaction sibling by inode inside the bounded output parent; deleting
// arbitrary external copies requires an OS sandbox or a separate identity.
// END EMBEDDABLE REVIEW OUTPUT TRANSACTION

module.exports = {
  GENERATED_REVIEW_TRANSACTION_LIMITS,
  generatedReviewArgsForWorkingOutput,
  generatedReviewAtomicWriteFileSync,
  generatedReviewCaptureDirectoryImage,
  generatedReviewCollectApplicationWritePaths,
  generatedReviewPathEntryExists,
  generatedReviewPathEntryStat,
  generatedReviewRewriteOutputPaths,
  generatedReviewTransactionEnvelope,
  withGeneratedReviewOutputTransaction,
};
