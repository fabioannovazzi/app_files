import hashlib
import importlib.util
import json
import secrets
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

source = (
    Path(__file__).resolve().parents[3]
    / "plugins/journal-bank-reconciliation/scripts/semantic_review.py"
)
spec = importlib.util.spec_from_file_location("qualification_capsule", source)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
import tempfile

out = Path(tempfile.mkdtemp(prefix="vera-native-image-qualification-")).resolve()
codex = Path(shutil.which("codex")).resolve()
helper = Path(
    "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex-code-mode-host"
).resolve()
production = m.SEATBELT_PROFILE
candidate = m._resolve_host_profile()
if m.inspect_execution_host(codex)["status"] != "prerequisites_match":
    raise SystemExit("This reproduction requires the already-qualified exact host.")
# Diagnostic-only exact helper. Both OS boundary and inner read-only sandbox stay active.
extra = f'(allow process-fork)\n(allow process-exec (literal "{helper}"))\n(allow file-read* file-map-executable (literal "{helper}"))\n'
extra += '(allow file-read* (literal "/Applications/ChatGPT.app/Contents/Resources/codex-cli/codex-package.json"))\n(allow file-read-metadata (path-ancestors "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex-code-mode-host"))\n'
boundary = m._codex_home_boundary_inputs()
font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 80)
controls = out / "image-controls"
controls.mkdir(exist_ok=True)
for name in sys.argv[1:] or ["positive", "outside", "symlink"]:
    work = controls / name
    work.mkdir(exist_ok=True)
    for d in ["state", "log"]:
        (work / d).mkdir(exist_ok=True)
    nonce = "".join(secrets.choice("ABCDEFGHJKMNPQRSTUVWXYZ23456789") for _ in range(6))
    image_path = (
        work / "permitted.png"
        if name == "positive"
        else controls / f"{name}-outside.png"
    )
    im = Image.new("RGB", (680, 180), "white")
    ImageDraw.Draw(im).text((40, 40), nonce, font=font, fill="black")
    im.save(image_path)
    profile = work / "seatbelt.sb"
    text = production + extra
    if name == "positive":
        text += f'(allow file-read* (literal "{image_path}"))\n'
    if name == "symlink":
        target = work / "linked.png"
        target.symlink_to(image_path)
        text += f'(allow file-read* (literal "{target}"))\n'
    else:
        target = image_path
    profile.write_text(text)
    schema = work / "schema.json"
    schema.write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {"nonce": {"type": "string"}},
                "required": ["nonce"],
                "additionalProperties": False,
            }
        )
    )
    prompt = work / "prompt.stdin"
    prompt.write_text(
        f'Use the native view_image tool to open this exact path: {target}. Read the six-character text in the image. Return only an object with nonce containing that exact text, or "DENIED" if the tool cannot open it. Do not use any other tool or guess the text.'
    )
    prefix = m._seatbelt_prefix(
        executable=codex,
        profile_path=profile,
        schema_path=schema,
        work_dir=work,
        state_dir=work / "state",
        log_dir=work / "log",
        boundary_inputs=boundary,
        host_profile=candidate,
    )
    inner = m._worker_inner_argv(
        capsule=work,
        schema_path=schema,
        state_dir=work / "state",
        log_dir=work / "log",
        host_profile=candidate,
        reasoning_effort="low",
    )
    pos = inner.index("code_mode_host")
    del inner[pos - 1 : pos + 1]
    r = m._run_captured_process(
        [*prefix, *inner],
        cwd=work,
        stdin_path=prompt,
        stdout_limit=m.MAX_EVENTS_BYTES,
        stderr_limit=m.MAX_STDERR_BYTES,
        timeout_seconds=180,
    )
    (work / "events.jsonl").write_bytes(r["stdout"])
    (work / "stderr.txt").write_bytes(r["stderr"])
    (work / "control.json").write_text(
        json.dumps(
            {
                "nonce": nonce,
                "return_code": r["return_code"],
                "inner_sandbox": "read-only",
                "helper_sha256": hashlib.sha256(helper.read_bytes()).hexdigest(),
                "production_profile_sha256": candidate.seatbelt_sha256,
                "diagnostic_profile_sha256": hashlib.sha256(text.encode()).hexdigest(),
            },
            indent=2,
        )
    )
    print(name, "exit", r["return_code"], flush=True)
