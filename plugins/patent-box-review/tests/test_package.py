import json
import re
import unittest
from pathlib import Path

from patent_box.contracts import ROOT, read_json, validate


class PackageTests(unittest.TestCase):
    def test_all_json_parses_without_duplicate_keys(self):
        for path in ROOT.rglob("*.json"):
            if "out" not in path.parts:
                read_json(path)

    def test_bundled_input_fixtures_match_schemas(self):
        for path in (ROOT / "examples").glob("case.*.json"):
            validate(read_json(path), "case.schema.json")
        validate(read_json(ROOT / "examples/rules.demo.json"), "ruleset.schema.json")
        validate(
            read_json(ROOT / "config/ruleset.proposed.json"), "ruleset.schema.json"
        )
        for path in (ROOT / "examples").glob("sources.*.json"):
            validate(read_json(path), "source-snapshot.schema.json")
        validate(read_json(ROOT / "examples/case-index.json"), "case-index.schema.json")

    def test_workflow_dependencies_exist_and_are_acyclic(self):
        rows = read_json(ROOT / "config/workflow.json")["stages"]
        pending = {r["id"]: set(r["depends_on"]) for r in rows}
        self.assertEqual(len(pending), len(rows))
        self.assertTrue(all(deps <= set(pending) for deps in pending.values()))
        done = set()
        while pending:
            ready = {i for i, deps in pending.items() if deps <= done}
            self.assertTrue(ready, "Cyclic dependencies")
            done |= ready
            pending = {i: d for i, d in pending.items() if i not in ready}

    def test_control_and_acceptance_ids_unique(self):
        controls = read_json(ROOT / "config/control_catalog.json")["controls"]
        scenarios = read_json(ROOT / "tests/acceptance_scenarios.json")["scenarios"]
        self.assertEqual(len(controls), len({c["control_id"] for c in controls}))
        self.assertEqual(len(scenarios), len({s["scenario_id"] for s in scenarios}))
        self.assertEqual(len(controls), 32)
        self.assertEqual(len(scenarios), 32)

    def test_acceptance_test_references_exist(self):
        test_source = (ROOT / "tests/test_engine.py").read_text()
        for row in read_json(ROOT / "tests/acceptance_scenarios.json")["scenarios"]:
            if row["unit_test"]:
                self.assertIn("def " + row["unit_test"] + "(", test_source)
            self.assertEqual(row["professional_uat"], "NOT_RUN")

    def test_live_monitor_is_not_accidentally_enabled(self):
        config = read_json(ROOT / "config/source_monitor.json")
        self.assertFalse(config["enabled"])
        self.assertIsNone(config["schedule"])
        self.assertIsNone(config["owner"])

    def test_real_sources_are_not_falsely_approved(self):
        reg = read_json(ROOT / "config/source_register.json")
        for source in reg["sources"]:
            self.assertFalse(source["approved_as_executable_rule"])
            self.assertIsNone(source["snapshot_sha256"])


if __name__ == "__main__":
    unittest.main()
