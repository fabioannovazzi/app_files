"""CI preserves test evidence without posting it into customer incident alerts."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_every_ci_workflow_defaults_to_local_only_incident_delivery():
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        workflow = yaml.safe_load(path.read_text())
        assert workflow["env"]["MPARANZA_INCIDENT_DELIVERY"] == "local-only", path
        for job in workflow["jobs"].values():
            assert (
                job.get("env", {}).get("MPARANZA_INCIDENT_DELIVERY", "local-only")
                == "local-only"
            ), path
            for step in job.get("steps", []):
                assert (
                    step.get("env", {}).get("MPARANZA_INCIDENT_DELIVERY", "local-only")
                    == "local-only"
                ), path
