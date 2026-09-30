import copy
import json
import tempfile
import unittest
from pathlib import Path

from patent_box.cli import main
from patent_box.contracts import (
    ROOT,
    ContractError,
    canonical_hash,
    read_json,
    validate,
)
from patent_box.engine import approval_record, calculate
from patent_box.monitor import compare_snapshots, impact_queue


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.case = read_json(ROOT / "examples/case.ordinary.json")
        self.rules = read_json(ROOT / "examples/rules.demo.json")

    def run_case(self, case=None, rules=None, as_of="2026-09-23"):
        return calculate(
            case or self.case,
            rules or self.rules,
            evidence_root=ROOT / "examples/evidence",
            as_of=as_of,
        )

    def test_additional_110_not_210_percent(self):
        r = self.run_case()
        self.assertEqual(
            r["additional_deduction"], {"income": "110000.00", "irap": "88000.00"}
        )
        self.assertIsNone(r["tax_saving"])

    def test_reproducible_and_input_immutable(self):
        before = copy.deepcopy(self.case)
        self.assertEqual(self.run_case(), self.run_case())
        self.assertEqual(before, self.case)

    def test_ordinary_software_no_registration(self):
        self.assertIsNone(self.case["ips"][0]["premial_event"])
        self.assertEqual(self.run_case()["lines"][0]["status"], "INCLUDED")

    def test_missing_rights_suspend(self):
        self.case["ips"][0]["controls"] = [
            x for x in self.case["ips"][0]["controls"] if x["gate"] != "RIGHTS"
        ]
        self.assertEqual(self.run_case()["bases"]["SUSPENDED"]["income"], "100000.00")

    def test_warning_is_not_silent_pass(self):
        self.case["allocations"][0]["controls"][1]["status"] = "WARNING"
        self.assertEqual(self.run_case()["additional_deduction"]["income"], "0.00")

    def test_explicit_substantive_failure_excluded(self):
        self.case["ips"][0]["controls"][0]["status"] = "FAIL"
        self.assertEqual(self.run_case()["bases"]["EXCLUDED"]["income"], "100000.00")

    def test_penalty_not_requested_does_not_block(self):
        self.assertEqual(
            self.run_case()["penalty_protection"]["status"], "NOT_REQUESTED"
        )
        self.assertEqual(self.run_case()["lines"][0]["status"], "INCLUDED")

    def test_penalty_incomplete_independent(self):
        c = read_json(ROOT / "examples/case.penalty-incomplete.json")
        r = self.run_case(c)
        self.assertEqual(r["additional_deduction"]["income"], "110000.00")
        self.assertEqual(r["penalty_protection"]["status"], "NOT_READY")

    def test_documentation_does_not_cure_missing_ip(self):
        base = self.case["controls"][0]
        self.case["penalty_protection"] = {
            "requested": True,
            "controls": [
                dict(copy.deepcopy(base), gate=g)
                for g in [
                    "DOC_A",
                    "DOC_B",
                    "SIGNATURE",
                    "TIMESTAMP",
                    "COMMUNICATION",
                    "RETENTION",
                ]
            ],
        }
        self.case["ips"][0]["controls"][0]["status"] = "FAIL"
        r = self.run_case()
        self.assertEqual(
            r["penalty_protection"]["status"], "REVIEWED_REQUIREMENTS_ONLY"
        )
        self.assertEqual(r["additional_deduction"]["income"], "0.00")

    def test_component_block_does_not_block_whole_case(self):
        r = self.run_case(read_json(ROOT / "examples/case.mixed.json"))
        self.assertEqual(r["bases"]["INCLUDED"]["income"], "100000.00")
        self.assertEqual(r["bases"]["SUSPENDED"]["income"], "100000.00")

    def test_outsourcing_requires_specific_review(self):
        self.case["ips"][0]["outsourced"] = True
        self.assertIn("OUTSOURCING:NOT_TESTED", self.run_case()["lines"][0]["reasons"])

    def test_unknown_ip_type_excluded(self):
        self.case["ips"][0]["type"] = "OTHER"
        self.assertEqual(self.run_case()["lines"][0]["status"], "EXCLUDED")

    def test_missing_cost_incentive_review_suspends(self):
        self.case["allocations"][0]["controls"].pop()
        self.assertIn("INCENTIVES:NOT_TESTED", self.run_case()["lines"][0]["reasons"])

    def test_premial_exact_eighth_period_included(self):
        r = self.run_case(read_json(ROOT / "examples/case.premial.json"))
        self.assertEqual(r["lines"][0]["status"], "INCLUDED")

    def test_ninth_period_excluded(self):
        c = read_json(ROOT / "examples/case.premial.json")
        c["costs"][0]["period_id"] = "P2016"
        self.assertIn("OUTSIDE_PREMIAL_WINDOW", self.run_case(c)["lines"][0]["reasons"])

    def test_premial_current_year_not_historical(self):
        c = read_json(ROOT / "examples/case.premial.json")
        c["costs"][0]["period_id"] = "P2025"
        self.assertEqual(self.run_case(c)["lines"][0]["status"], "EXCLUDED")

    def test_premial_without_registration_suspended(self):
        self.case["allocations"][0]["mode"] = "PREMIAL"
        self.assertIn("PREMIAL_EVENT_MISSING", self.run_case()["lines"][0]["reasons"])

    def test_wrong_premial_event_kind_suspended(self):
        c = read_json(ROOT / "examples/case.premial.json")
        c["ips"][0]["premial_event"]["kind"] = "PATENT_GRANT"
        self.assertIn(
            "PREMIAL_EVENT_KIND_NOT_REVIEWED", self.run_case(c)["lines"][0]["reasons"]
        )

    def test_premial_event_date_must_match_period(self):
        c = read_json(ROOT / "examples/case.premial.json")
        c["ips"][0]["premial_event"]["date"] = "2024-01-01"
        with self.assertRaises(ContractError):
            self.run_case(c)

    def test_deferred_use_does_not_shift_historical_window(self):
        c = read_json(ROOT / "examples/case.premial.json")
        c["claim_period_id"] = "P2026"
        self.assertEqual(self.run_case(c)["lines"][0]["status"], "INCLUDED")
        c["costs"][0]["period_id"] = "P2016"
        self.assertIn("OUTSIDE_PREMIAL_WINDOW", self.run_case(c)["lines"][0]["reasons"])

    def test_non_calendar_periods(self):
        for p in self.case["periods"]:
            y = int(p["period_id"][1:])
            p["start"] = f"{y}-07-01"
            p["end"] = f"{y+1}-06-30"
        self.assertEqual(self.run_case()["additional_deduction"]["income"], "110000.00")

    def test_premial_entry_uses_fiscal_period_not_january(self):
        c = read_json(ROOT / "examples/case.premial.json")
        for p in c["periods"]:
            y = int(p["period_id"][1:])
            p["start"] = f"{y}-07-01"
            p["end"] = f"{y+1}-06-30"
        c["ips"][0]["premial_event"].update(period_id="P2020", date="2021-03-01")
        # March 2021 falls in a period ending before the 31 December anchor.
        self.assertIn(
            "EVENT_REQUIRES_TRANSITION_REVIEW", self.run_case(c)["lines"][0]["reasons"]
        )

    def test_missing_period_breaks_window(self):
        del self.case["periods"][1]
        with self.assertRaises(ContractError):
            self.run_case()

    def test_period_overlap_rejected(self):
        self.case["periods"][1]["start"] = "2015-12-31"
        with self.assertRaises(ContractError):
            self.run_case()

    def test_historical_cost_not_ordinary(self):
        self.case["costs"][0]["period_id"] = "P2024"
        self.assertEqual(self.run_case()["lines"][0]["status"], "EXCLUDED")

    def test_prior_claim_duplicate_suspends(self):
        self.case = read_json(ROOT / "examples/case.premial.json")
        self.case["prior_claims"] = [
            {
                "claim_id": "OLD.1",
                "cost_id": "C1",
                "claim_period_id": "P2024",
                "income_amount": "1.00",
                "irap_amount": "0.00",
                "regime": "NEW",
                "evidence_id": "DEMO.EVIDENCE",
            }
        ]
        self.assertIn("POSSIBLE_DOUBLE_CLAIM", self.run_case()["lines"][0]["reasons"])

    def test_prior_claim_cannot_predate_cost(self):
        self.case["prior_claims"] = [
            {
                "claim_id": "OLD.1",
                "cost_id": "C1",
                "claim_period_id": "P2024",
                "income_amount": "1.00",
                "irap_amount": "0.00",
                "regime": "NEW",
                "evidence_id": "DEMO.EVIDENCE",
            }
        ]
        with self.assertRaises(ContractError):
            self.run_case()

    def test_duplicate_source_row_rejected(self):
        c = copy.deepcopy(self.case["costs"][0])
        c["cost_id"] = "C2"
        self.case["costs"].append(c)
        self.case["ledger_control_total"] = "200000.00"
        with self.assertRaises(ContractError):
            self.run_case()

    def test_duplicate_allocation_id_rejected(self):
        self.case["allocations"].append(copy.deepcopy(self.case["allocations"][0]))
        with self.assertRaises(ContractError):
            self.run_case()

    def test_overallocation_across_multiple_ips_rejected(self):
        a = copy.deepcopy(self.case["allocations"][0])
        a["allocation_id"] = "A2"
        self.case["allocations"].append(a)
        with self.assertRaises(ContractError):
            self.run_case()

    def test_accounting_tieout_required(self):
        self.case["ledger_control_total"] = "100001.00"
        with self.assertRaises(ContractError):
            self.run_case()

    def test_unallocated_costs_visible(self):
        self.case["allocations"][0]["income_amount"] = "80000.00"
        self.assertEqual(self.run_case()["unallocated_bases"]["income"], "20000.00")

    def test_rounding_after_aggregation(self):
        self.case["ledger_control_total"] = "0.10"
        self.case["costs"][0].update(
            book_amount="0.10", income_max="0.10", irap_max="0.10"
        )
        self.case["allocations"][0].update(income_amount="0.05", irap_amount="0.05")
        b = copy.deepcopy(self.case["allocations"][0])
        b["allocation_id"] = "A2"
        self.case["allocations"].append(b)
        self.assertEqual(self.run_case()["additional_deduction"]["income"], "0.11")

    def test_missing_review_is_not_pass(self):
        self.case["controls"][0]["reviewer"] = None
        self.assertEqual(self.run_case()["lines"][0]["status"], "SUSPENDED")

    def test_future_review_is_not_pass(self):
        self.case["controls"][0]["reviewed_on"] = "2027-01-01"
        self.assertEqual(self.run_case()["lines"][0]["status"], "SUSPENDED")

    def test_missing_evidence_not_inferred(self):
        self.case["controls"][0]["evidence_ids"] = []
        self.assertEqual(self.run_case()["lines"][0]["status"], "SUSPENDED")

    def test_hash_tampering_rejected(self):
        self.case["evidence"][0]["sha256"] = "0" * 64
        with self.assertRaises(ContractError):
            self.run_case()

    def test_path_traversal_rejected(self):
        self.case["evidence"][0]["path"] = "../../README.md"
        with self.assertRaises(ContractError):
            self.run_case()

    def test_unknown_source_suspends(self):
        self.case["controls"][0]["source_ids"] = ["INVENTED"]
        self.assertEqual(self.run_case()["lines"][0]["status"], "SUSPENDED")

    def test_unknown_fields_rejected(self):
        self.case["automatic_approval"] = True
        with self.assertRaises(ContractError):
            self.run_case()

    def test_negative_money_rejected(self):
        self.case["costs"][0]["book_amount"] = "-1.00"
        with self.assertRaises(ContractError):
            self.run_case()

    def test_float_money_rejected(self):
        self.case["allocations"][0]["income_amount"] = 100000.0
        with self.assertRaises(ContractError):
            self.run_case()

    def test_comma_decimal_rejected(self):
        self.case["allocations"][0]["income_amount"] = "100,00"
        with self.assertRaises(ContractError):
            self.run_case()

    def test_currency_not_silently_converted(self):
        self.case["costs"][0]["currency"] = "USD"
        with self.assertRaises(ContractError):
            self.run_case()

    def test_draft_rules_cannot_calculate(self):
        rules = read_json(ROOT / "config/ruleset.proposed.json")
        self.case["demo"] = False
        with self.assertRaises(ContractError):
            self.run_case(rules=rules)

    def test_demo_real_cannot_mix(self):
        self.case["demo"] = False
        with self.assertRaises(ContractError):
            self.run_case()

    def test_synthetic_source_on_real_case_rejected(self):
        self.case["demo"] = False
        self.rules["demo"] = False
        with self.assertRaises(ContractError):
            self.run_case()

    def test_stale_source_preflight(self):
        self.rules["sources_checked_on"] = "2026-09-01"
        with self.assertRaises(ContractError):
            self.run_case()

    def test_missing_rule_review_date(self):
        self.rules["reviewed_on"] = None
        with self.assertRaises(ContractError):
            self.run_case()

    def test_rule_period_coverage(self):
        self.rules["tax_period_start_max"] = "2024-12-31"
        with self.assertRaises(ContractError):
            self.run_case()

    def test_approval_stale_input_rejected(self):
        result = self.run_case()
        self.case["case_id"] = "CHANGED"
        with self.assertRaises(ContractError):
            approval_record(
                self.case, self.rules, result, "Reviewer", "APPROVE_DRAFT", "2026-09-23"
            )

    def test_approval_tampered_result_rejected(self):
        result = self.run_case()
        result["additional_deduction"]["income"] = "1.00"
        with self.assertRaises(ContractError):
            approval_record(
                self.case, self.rules, result, "Reviewer", "APPROVE_DRAFT", "2026-09-23"
            )

    def test_approval_is_not_electronic_signature(self):
        a = approval_record(
            self.case,
            self.rules,
            self.run_case(),
            "Reviewer",
            "APPROVE_DRAFT",
            "2026-09-23",
        )
        self.assertIsNone(a["signature"])
        self.assertEqual(a["authentication"], "REQUIRES_HOST_IDENTITY")

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "a.json"
            p.write_text('{"x":1,"x":2}')
            with self.assertRaises(ContractError):
                read_json(p)


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.before = read_json(ROOT / "examples/sources.before.json")
        self.after = read_json(ROOT / "examples/sources.after.json")
        self.index = read_json(ROOT / "examples/case-index.json")

    def test_unchanged_no_events(self):
        self.assertEqual(compare_snapshots(self.before, self.before)["events"], [])

    def test_changed_source_reopens_only_by_proposal(self):
        old = copy.deepcopy(self.index)
        q = impact_queue(compare_snapshots(self.before, self.after), self.index)
        self.assertEqual(q["items"][0]["action"], "PROPOSE_REOPEN")
        self.assertFalse(q["items"][0]["automatic_mutation"])
        self.assertEqual(old, self.index)

    def test_network_failure_is_not_no_change(self):
        self.after["sources"][0].update(fetch_status="HTTP_ERROR", content_sha256=None)
        self.after["coverage"] = "PARTIAL"
        d = compare_snapshots(self.before, self.after)
        self.assertEqual(d["events"][0]["kind"], "SOURCE_UNAVAILABLE")
        self.assertEqual(d["status"], "PARTIAL_SCAN")

    def test_error_overrides_claimed_complete_coverage(self):
        self.after["sources"][0].update(fetch_status="TIMEOUT", content_sha256=None)
        self.assertEqual(
            compare_snapshots(self.before, self.after)["status"], "PARTIAL_SCAN"
        )

    def test_ok_without_source_hash_rejected(self):
        self.after["sources"][0]["content_sha256"] = None
        with self.assertRaises(ContractError):
            compare_snapshots(self.before, self.after)

    def test_old_regime_not_automatically_reused(self):
        self.after["sources"][0]["regime"] = "OLD"
        q = impact_queue(compare_snapshots(self.before, self.after), self.index)
        self.assertEqual(q["items"], [])

    def test_unknown_mapping_broadens_review(self):
        self.after["sources"][0]["impact_reviewed"] = False
        self.index["cases"][0]["rule_ids"] = ["PB.OTHER"]
        self.assertEqual(
            len(
                impact_queue(compare_snapshots(self.before, self.after), self.index)[
                    "items"
                ]
            ),
            1,
        )

    def test_no_temporal_overlap(self):
        self.after["sources"][0]["affected_from"] = "2026-01-01"
        self.assertEqual(
            impact_queue(compare_snapshots(self.before, self.after), self.index)[
                "items"
            ],
            [],
        )

    def test_publication_not_effective_date(self):
        self.after["sources"][0]["retrieved_at"] = "2026-09-23T20:00:00+00:00"
        self.assertEqual(
            len(
                impact_queue(compare_snapshots(self.before, self.after), self.index)[
                    "items"
                ]
            ),
            1,
        )

    def test_unreviewed_old_label_cannot_filter_cases(self):
        self.after["sources"][0].update(regime="OLD", impact_reviewed=False)
        self.assertEqual(
            len(
                impact_queue(compare_snapshots(self.before, self.after), self.index)[
                    "items"
                ]
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
