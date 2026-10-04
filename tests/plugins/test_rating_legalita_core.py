"""Casi di confine sintetici; nessuna pratica reale, nessun portale."""

from __future__ import annotations

import importlib.util
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "rating_core_test",
    Path(__file__).resolve().parents[2]
    / "plugins/rating-legalita/scripts/core_rating.py",
)
assert SPEC and SPEC.loader
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


def p(n):
    return {x: "supported" if i < n else "absent" for i, x in enumerate("abcdefgh")}


class CoreTests(unittest.TestCase):
    def test_debt_half_percent(self):
        self.assertEqual(c.debt_threshold("2000000"), Decimal("10000"))

    def test_debt_maximum(self):
        self.assertEqual(c.debt_threshold("20000000"), Decimal("50000"))

    def test_debt_equal(self):
        self.assertTrue(c.debt_test("2000000", "10000"))

    def test_debt_one_cent_above(self):
        self.assertFalse(c.debt_test("2000000", "10000.01"))

    def test_debt_missing(self):
        with self.assertRaises(ValueError):
            c.debt_test("2000000", None)

    def test_negative_amount(self):
        with self.assertRaises(ValueError):
            c.money("-1")

    def test_nonfinite_amount(self):
        with self.assertRaises(ValueError):
            c.money("NaN")

    def test_safety_single_equal(self):
        self.assertTrue(c.safety_test([1200]))

    def test_safety_single_above(self):
        self.assertFalse(c.safety_test(["1200.01"]))

    def test_safety_multiple_equal(self):
        self.assertTrue(c.safety_test([1200, 1200, 1200]))

    def test_safety_multiple_excess(self):
        self.assertFalse(c.safety_test([1000, 1000, 1000, 1000]))

    def test_safety_individual_excess(self):
        self.assertFalse(c.safety_test([2000, 1000]))

    def test_half_is_not_more_than_half(self):
        self.assertFalse(
            c.traceability_test(100, 50, complete=True, perimeter_reviewed=True)
        )

    def test_majority(self):
        self.assertTrue(
            c.traceability_test(100, 51, complete=True, perimeter_reviewed=True)
        )

    def test_no_payments(self):
        self.assertIsNone(
            c.traceability_test(0, 0, complete=True, perimeter_reviewed=True)
        )

    def test_partial_payments(self):
        self.assertIsNone(
            c.traceability_test(100, 99, complete=False, perimeter_reviewed=True)
        )

    def test_unreviewed_payments(self):
        self.assertIsNone(
            c.traceability_test(100, 99, complete=True, perimeter_reviewed=False)
        )

    def test_impossible_counts(self):
        with self.assertRaises(ValueError):
            c.traceability_test(100, 101, complete=True, perimeter_reviewed=True)

    def test_text_confirmation_not_boolean(self):
        with self.assertRaises(ValueError):
            c.traceability_test(100, 99, complete="false", perimeter_reviewed=True)

    def test_old_rating_two_years(self):
        self.assertEqual(c.expected_expiry(date(2026, 3, 15)), date(2028, 3, 15))

    def test_new_rating_three_years(self):
        self.assertEqual(c.expected_expiry(date(2026, 3, 16)), date(2029, 3, 16))

    def test_calendar_months_not_180_days(self):
        self.assertEqual(c.renewal_window(date(2027, 3, 31))[0], date(2026, 9, 30))

    def test_sixtieth_day_renewal(self):
        self.assertEqual(
            c.application_route(date(2026, 8, 3), date(2026, 10, 2)), "rinnovo"
        )

    def test_fiftyninth_day_new(self):
        self.assertEqual(
            c.application_route(date(2026, 8, 4), date(2026, 10, 2)),
            "nuova_attribuzione",
        )

    def test_renewal_too_early(self):
        self.assertEqual(
            c.application_route(date(2026, 4, 1), date(2026, 10, 2)),
            "rinnovo_non_ancora_presentabile",
        )

    def test_renewal_first_day(self):
        self.assertEqual(
            c.application_route(date(2026, 4, 2), date(2026, 10, 2)), "rinnovo"
        )

    def test_event_deadline_month_crossing(self):
        self.assertEqual(c.event_deadline(date(2026, 10, 2)), date(2026, 11, 1))

    def test_transition_shorter_expiry(self):
        self.assertEqual(
            c.transitional_expiry(
                date(2026, 10, 20),
                timely_notice=True,
                authority_continuation_confirmed=True,
            ),
            date(2026, 10, 20),
        )

    def test_transition_november_cap(self):
        self.assertEqual(
            c.transitional_expiry(
                date(2027, 5, 10),
                timely_notice=True,
                authority_continuation_confirmed=True,
            ),
            date(2026, 11, 16),
        )

    def test_transition_notice_missing(self):
        self.assertIsNone(
            c.transitional_expiry(
                date(2027, 5, 10),
                timely_notice=False,
                authority_continuation_confirmed=True,
            )
        )

    def test_transition_authority_missing(self):
        self.assertIsNone(
            c.transitional_expiry(
                date(2027, 5, 10),
                timely_notice=True,
                authority_continuation_confirmed=False,
            )
        )

    def test_star_conversion(self):
        expected = ["★", "★+", "★++", "★★", "★★+", "★★++", "★★★"]
        self.assertEqual([c.label(i) for i in range(7)], expected)

    def test_obstacle_blocks_despite_eight_premiums(self):
        self.assertIsNone(
            c.score(base="obstructed", premiums=p(8), deduction=False)[
                "estimated_rating"
            ]
        )

    def test_unknown_base_is_not_one_star(self):
        self.assertIsNone(
            c.score(base="undetermined", premiums=p(0), deduction=False)[
                "estimated_rating"
            ]
        )

    def test_six_awards(self):
        self.assertEqual(
            c.score(base="verified", premiums=p(6), deduction=False)[
                "estimated_rating"
            ],
            "★★★",
        )

    def test_three_awards_with_deduction(self):
        self.assertEqual(
            c.score(base="verified", premiums=p(3), deduction=True)["estimated_rating"],
            "★++",
        )

    def test_deduction_cannot_remove_base(self):
        self.assertEqual(
            c.score(base="verified", premiums=p(0), deduction=True)["estimated_rating"],
            "★",
        )

    def test_loyalty_requires_three_previous_renewals(self):
        self.assertEqual(
            c.score(
                base="verified",
                premiums=p(2),
                deduction=False,
                prior_continuous_renewals=2,
                timely_renewal=True,
            )["estimated_rating"],
            "★++",
        )

    def test_loyalty_after_three_renewals(self):
        self.assertEqual(
            c.score(
                base="verified",
                premiums=p(2),
                deduction=False,
                prior_continuous_renewals=3,
                timely_renewal=True,
            )["estimated_rating"],
            "★★",
        )

    def test_loyalty_denied_on_new_attribution(self):
        self.assertEqual(
            c.score(
                base="verified",
                premiums=p(2),
                deduction=False,
                prior_continuous_renewals=3,
                timely_renewal=False,
            )["estimated_rating"],
            "★++",
        )

    def test_unknown_premiums_excluded(self):
        values = p(2)
        values["c"] = "unknown"
        result = c.score(base="verified", premiums=values, deduction=False)
        self.assertEqual(result["estimated_rating"], "★++")
        self.assertEqual(result["unknown_premiums"], ["c"])

    def test_unknown_anac_no_unique_claim(self):
        self.assertIsNone(
            c.score(base="verified", premiums=p(3), deduction=None)["estimated_rating"]
        )

    def test_cap_deduction_requires_review(self):
        result = c.score(base="verified", premiums=p(7), deduction=True)
        self.assertIsNone(result["estimated_rating"])
        self.assertEqual(result["possible_estimates"], ["★★++", "★★★"])

    def test_approved_policy_is_explicit(self):
        self.assertEqual(
            c.score(
                base="verified",
                premiums=p(7),
                deduction=True,
                approved_cap_policy="net_then_cap",
            )["estimated_rating"],
            "★★★",
        )

    def test_unknown_policy_rejected(self):
        with self.assertRaises(ValueError):
            c.score(
                base="verified",
                premiums=p(7),
                deduction=True,
                approved_cap_policy="guess",
            )

    def test_duplicate_letter_shape_rejected(self):
        values = p(2)
        values["a_second"] = "supported"
        with self.assertRaises(ValueError):
            c.score(base="verified", premiums=values, deduction=False)

    def gate(self, **override):
        args = dict(
            required_states={"A01": "verified", "B02": "verified"},
            source_current=True,
            perimeter_complete=True,
            declarations_complete=True,
            reviewed_bundle_hash="abc",
            actual_bundle_hash="abc",
            field_map_verified=True,
            attachments_complete=True,
        )
        args.update(override)
        return c.final_readiness(**args)

    def test_readiness_all_met(self):
        self.assertTrue(self.gate()["ready"])
        self.assertFalse(self.gate()["submission_authorized"])

    def test_missing_evidence_blocks(self):
        self.assertFalse(
            self.gate(required_states={"A01": "verified", "B02": "unknown"})["ready"]
        )

    def test_new_version_invalidates_approval(self):
        self.assertFalse(self.gate(actual_bundle_hash="different")["ready"])

    def test_stale_source_blocks(self):
        self.assertFalse(self.gate(source_current=False)["ready"])

    def test_unmapped_portal_blocks(self):
        self.assertFalse(self.gate(field_map_verified=False)["ready"])

    def test_missing_attachment_blocks(self):
        self.assertFalse(self.gate(attachments_complete=False)["ready"])

    def test_empty_matrix_is_not_complete(self):
        self.assertFalse(self.gate(required_states={})["ready"])
        self.assertFalse(self.gate(required_states={})["submission_authorized"])

    def test_text_confirmation_does_not_unlock(self):
        with self.assertRaises(ValueError):
            self.gate(source_current="false")

    def test_missing_subject_keeps_open(self):
        self.assertFalse(self.gate(perimeter_complete=False)["ready"])

    def test_unsigned_declarations_keep_open(self):
        self.assertFalse(self.gate(declarations_complete=False)["ready"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
