"use strict";

// Simulate filesystem observations at the verifier's actual read boundaries.
// Package bytes stay untouched except in the explicit content-mismatch case.
const fs = require("node:fs");
const path = require("node:path");
const target = path.resolve(process.env.VERIFIER_TEST_TARGET);
const scenario = process.env.VERIFIER_TEST_SCENARIO;
const descriptors = new Set();
let opened = false;
let read = false;
const original = {
  open: fs.openSync, lstat: fs.lstatSync, fstat: fs.fstatSync,
  read: fs.readFileSync, close: fs.closeSync,
};

function observation(info, selected) {
  const active = scenario === "ctime-during-read" ? read : opened;
  if (!selected || !active) return info;
  const changed = Object.create(info);
  const field = {
    "ctime-before-read": "ctimeNs", "ctime-during-read": "ctimeNs",
    "replaced-file": "ino", "modified-file": "mtimeNs",
  }[scenario];
  if (field) changed[field] = info[field] + 1n;
  return changed;
}

fs.openSync = function(file, ...args) {
  const fd = original.open(file, ...args);
  if (path.resolve(String(file)) === target) {
    opened = true;
    read = false;
    descriptors.add(fd);
  }
  return fd;
};
fs.lstatSync = function(file, options) {
  return observation(original.lstat(file, options),
    options?.bigint && path.resolve(String(file)) === target);
};
fs.fstatSync = function(fd, options) {
  return observation(original.fstat(fd, options), descriptors.has(fd) && options?.bigint);
};
fs.readFileSync = function(file, ...args) {
  const bytes = original.read(file, ...args);
  if (!descriptors.has(file)) return bytes;
  read = true;
  if (scenario === "changed-content") {
    const altered = Buffer.from(bytes);
    altered[0] ^= 1; // Same length and metadata, different package bytes.
    return altered;
  }
  return bytes;
};
fs.closeSync = function(fd) {
  descriptors.delete(fd);
  return original.close(fd);
};
