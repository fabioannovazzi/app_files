# Native invoice worker: current-host qualification

The v2 record pins macOS 26A428, Codex CLI 0.155.0-alpha.16, and the exact
Codex, sandbox-exec and canary-reader hashes. The original v1 record remains
immutable. The production Seatbelt text, feature exclusions, model selection,
read-only worker arguments, allowed data paths and per-launch canaries are
unchanged. A version/hash update alone was not used as qualification.

The normal public worker entry point produced a schema-valid answer and an
actual launch receipt. Exact schema reading succeeded; an outside-file read was
denied. The native image tool also denied both an outside image and a symlink
from a permitted directory to an outside image. A permitted image control
returned its fresh random nonce exactly. Native tool-router logs independently
record the negative outcomes; no kernel-log confirmation is claimed.

The image diagnostics needed a separately permitted, exact code-mode helper
and child-process creation. Codex's nested filesystem sandbox otherwise failed
before any file operation, including the positive control. Only those diagnostic
processes used the outer OS sandbox without the inner CLI sandbox. The outer
sandbox kept its original deny-default data boundary. Production never gains
these extra helper/process permissions or the diagnostic inner configuration.
Thus the working image controls exercise a more permissive diagnostic envelope;
the deployed worker remains more restricted.

`worker-qualification.json` binds the original local evidence by digest and
records limitations, including the earlier OCR error and the negative probe's
extra model message. That probe is not a normal accepted worker response.
Unknown hosts or changed executables still fail closed. New operating-system or
Codex builds require fresh qualification. This evidence does not establish
Windows, Cowork, professional correctness or learner completion.
