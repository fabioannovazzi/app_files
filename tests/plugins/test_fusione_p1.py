from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


class Inputs:
    """Small exact-reference inputs for the public pure calculation API."""

    def __init__(self, engine):
        self.engine = engine
        self.records = {}
        self.a = self.row(
            "Entity", {"residence": "IT", "accounting_framework": "OIC"}, "alpha"
        )
        self.b = self.row(
            "Entity", {"residence": "IT", "accounting_framework": "OIC"}, "beta"
        )
        self.rule = self.row("RuleVersion", {})

    def row(self, kind, data, name=None):
        key = name or f"r_{len(self.records)}"
        ref = {"operation_id": "operation_test", "id": key, "version": 1, "sha256": key}
        self.records[key] = {**ref, "kind": kind, "data": data}
        return ref

    def fact(self, value, kind="decimal"):
        return self.row(
            "Fact", {"fact_status": "known", "value_kind": kind, "value": value}
        )

    def derive(self, kind, request):
        return self.engine.derive(kind, request, self.records)

    def paper(self, kind, request):
        result, issues = self.derive(kind, request)
        return self.row(
            kind,
            {
                "engine_version": "fusione.p1.v1",
                "request": request,
                "result": result,
                "issues": issues,
            },
        )

    def branch(self, wholly=False):
        return {
            "branch": (
                "wholly_owned_domestic_oic" if wholly else "ordinary_domestic_oic"
            ),
            "acquirer": self.a,
            "target": self.b,
            "assumptions": {
                name: self.fact(True, "boolean")
                for name in sorted(self.engine.ASSUMPTIONS)
            },
            "ownership": self.fact("1/1" if wholly else "0/1", "fraction"),
            "ownership_edge": (
                self.row(
                    "OwnershipEdge",
                    {"holder": "alpha", "company": "beta", "ratio": "1/1"},
                )
                if wholly
                else None
            ),
            "rationale": self.fact("Reviewed case scope", "text"),
            "rules": [self.rule],
        }

    def valuation(self, plan, company, value):
        return {
            "plan": plan,
            "company": company,
            "basis": "equity",
            "value": self.fact(value),
            "debt": None,
            "cash": None,
            "adjustments": None,
            "method": self.fact("Reviewed equity value", "text"),
            "valuation_date": self.fact("2026-09-30", "date"),
        }

    def exchange(self, wholly=False):
        plan = self.paper("BranchDecision", self.branch(wholly))
        va = (
            None
            if wholly
            else self.paper("Valuation", self.valuation(plan, self.a, "600000"))
        )
        vb = (
            None
            if wholly
            else self.paper("Valuation", self.valuation(plan, self.b, "400000"))
        )
        return {
            "plan": plan,
            "valuation_a": va,
            "valuation_b": vb,
            "units_a": self.fact("60000"),
            "units_b": None if wholly else self.fact("20000"),
            "nominal": self.fact("1"),
            "unit_type": "shares",
            "shareholders_a": [
                {
                    "id": "alice",
                    "name": self.fact("Alice", "text"),
                    "units": self.fact("60000"),
                }
            ],
            "shareholders_b": (
                []
                if wholly
                else [
                    {
                        "id": "bob",
                        "name": self.fact("Bob", "text"),
                        "units": self.fact("20000"),
                    }
                ]
            ),
            "allocation_policy": self.fact("Exact units, no cash adjustment", "text"),
        }

    def account(self, key, category, amount):
        return {
            "id": key,
            "label": key,
            "category": category,
            "balance": self.fact(amount),
        }

    def bridge(self, wholly=False):
        exchange = self.exchange(wholly)
        ex = self.paper("ExchangeModel", exchange)
        a = [
            self.account("cash", "asset", "500000"),
            self.account("capital", "equity", "-500000"),
        ]
        b = [
            self.account("assets", "asset", "500000"),
            self.account("liabilities", "liability", "-200000"),
            self.account("equity", "equity", "-300000"),
        ]
        if wholly:
            a.extend(
                [
                    self.account("investment", "asset", "480000"),
                    self.account("debt", "liability", "-480000"),
                ]
            )
        allocation = self.account(
            "reviewed_difference",
            "asset" if wholly else "equity",
            "180000" if wholly else "-260000",
        )
        return {
            "plan": exchange["plan"],
            "exchange": ex,
            "balances_a": a,
            "balances_b": b,
            "date_a": self.fact("2026-09-30", "date"),
            "date_b": self.fact("2026-09-30", "date"),
            "investment_account": "investment" if wholly else None,
            "eliminations": [],
            "difference_allocations": [allocation],
            "accounting_policy": self.fact(
                "Reviewed accounting and tax policy", "text"
            ),
            "tax_register": [],
        }

    def calendar(self, anchor="2026-01-31", count=1, unit="months", actual=None):
        return {
            "plan": self.paper("BranchDecision", self.branch()),
            "events": [
                {
                    "id": "event",
                    "label": "Reviewed event",
                    "anchors": [self.fact(anchor, "date")],
                    "count": count,
                    "unit": unit,
                    "rule": self.rule,
                    "owner": self.fact("Reviewer", "text"),
                    "actual": None if actual is None else self.fact(actual, "date"),
                    "constraint": "not_before",
                    "adjusted_boundary": None,
                    "adjustment_reason": None,
                }
            ],
            "computation_policy": self.fact(
                "Reviewed day and month convention", "text"
            ),
        }


@pytest.fixture
def inputs(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/fusione-guidata/scripts"))
    return Inputs(importlib.import_module("fusione_p1"))


@pytest.mark.parametrize(
    "wholly,expected",
    [(False, "ordinary_domestic_oic"), (True, "wholly_owned_domestic_oic")],
)
def test_selected_branch_preserves_reviewed_identity(inputs, wholly, expected):
    request = inputs.branch(wholly)
    result, issues = inputs.derive("BranchDecision", request)
    assert result["branch"] == expected
    assert issues == []
    assert result["legal_execution"] == "not_authorized"


@pytest.mark.parametrize(
    "assumption",
    [
        "domestic_oic",
        "incorporation",
        "homogeneous_rights",
        "no_cash_adjustment",
        "no_own_or_reciprocal_holdings",
        "no_mlbo",
        "no_special_regulated_or_crisis_case",
    ],
)
def test_scope_contradiction_blocks_selected_branch(inputs, assumption):
    request = inputs.branch()
    request["assumptions"][assumption] = inputs.fact(False, "boolean")
    _, issues = inputs.derive("BranchDecision", request)
    assert issues == [assumption]


def test_partial_ownership_is_not_accepted_as_wholly_owned(inputs):
    request = inputs.branch(True)
    request["ownership"] = inputs.fact("9/10", "fraction")
    _, issues = inputs.derive("BranchDecision", request)
    assert issues == ["ownership_outside_selected_branch"]


def test_foreign_entity_is_not_accepted_as_domestic_oic(inputs):
    request = inputs.branch()
    inputs.records["beta"]["data"]["residence"] = "CH"
    _, issues = inputs.derive("BranchDecision", request)
    assert issues == ["company_scope_requires_review"]


def test_reverse_ownership_edge_does_not_support_direct_incorporation(inputs):
    request = inputs.branch(True)
    inputs.records[request["ownership_edge"]["id"]]["data"]["holder"] = "beta"
    _, issues = inputs.derive("BranchDecision", request)
    assert issues == ["direct_ownership_not_demonstrated"]


def test_unimplemented_branch_returns_explicit_unsupported_result(inputs):
    request = inputs.branch()
    request["branch"] = "mlbo"
    result, issues = inputs.derive("BranchDecision", request)
    assert result["support_status"] == "unsupported"
    assert issues == ["unsupported_branch"]


@pytest.mark.parametrize(
    "basis,debt,cash,adjustments,expected",
    [
        ("equity", None, None, None, "600000.00"),
        ("enterprise", "120000", "30000", "-10000", "500000.00"),
    ],
)
def test_equity_bridge_preserves_exact_components(
    inputs, basis, debt, cash, adjustments, expected
):
    plan = inputs.paper("BranchDecision", inputs.branch())
    request = inputs.valuation(plan, inputs.a, "600000")
    request.update(
        basis=basis,
        debt=None if debt is None else inputs.fact(debt),
        cash=None if cash is None else inputs.fact(cash),
        adjustments=None if adjustments is None else inputs.fact(adjustments),
    )
    result, issues = inputs.derive("Valuation", request)
    assert result["equity"] == expected
    assert issues == []


def test_enterprise_bridge_exposes_negative_equity(inputs):
    plan = inputs.paper("BranchDecision", inputs.branch())
    request = inputs.valuation(plan, inputs.a, "10")
    request.update(
        basis="enterprise",
        debt=inputs.fact("20"),
        cash=inputs.fact("0"),
        adjustments=inputs.fact("0"),
    )
    result, issues = inputs.derive("Valuation", request)
    assert result["equity"] == "-10.00"
    assert issues == ["nonpositive_equity"]


@pytest.mark.parametrize("value", ["0", "-1", 1.2, "NaN"])
def test_valuation_rejects_invalid_economic_inputs(inputs, value):
    plan = inputs.paper("BranchDecision", inputs.branch())
    request = inputs.valuation(plan, inputs.a, value)
    with pytest.raises(inputs.engine.CaseError):
        inputs.derive("Valuation", request)


def test_independent_exchange_calculates_owner_level_exact_shares(inputs):
    request = inputs.exchange()
    result, issues = inputs.derive("ExchangeModel", request)
    assert result["exchange_ratio"] == "2/1"
    assert result["capital_increase_exact"] == "40000/1"
    assert result["allocations"][1]["resulting_fraction"] == "2/5"
    assert issues == []


def test_wholly_owned_branch_issues_no_replacement_shares(inputs):
    request = inputs.exchange(True)
    result, issues = inputs.derive("ExchangeModel", request)
    assert result["new_units"] == "0/1"
    assert result["exchange_ratio"] is None
    assert result["allocations"][0]["resulting_fraction"] == "1/1"
    assert issues == []


def test_fractional_shares_are_not_silently_rounded(inputs):
    request = inputs.exchange()
    request["shareholders_b"] = [
        {"id": "bob", "name": inputs.fact("Bob", "text"), "units": inputs.fact("1")},
        {
            "id": "bea",
            "name": inputs.fact("Bea", "text"),
            "units": inputs.fact("19999"),
        },
    ]
    inputs.records[request["valuation_b"]["id"]]["data"]["result"]["equity"] = "400001"
    result, issues = inputs.derive("ExchangeModel", request)
    assert result["new_units"] == "400001/10"
    assert result["allocations"][1]["fractional_remainder"] == "1/200000"
    assert issues == ["fractional_shares_require_dedicated_allocation"]


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_owner",
        "unbalanced_owners",
        "wrong_plan",
        "different_dates",
        "different_company",
        "invalid_unit",
        "fractional_input_shares",
    ],
)
def test_exchange_rejects_inconsistent_population_or_valuation(inputs, mutation):
    request = inputs.exchange()
    if mutation == "duplicate_owner":
        request["shareholders_a"].append(copy.deepcopy(request["shareholders_a"][0]))
    elif mutation == "unbalanced_owners":
        request["units_a"] = inputs.fact("60001")
    elif mutation == "wrong_plan":
        inputs.records[request["valuation_b"]["id"]]["data"]["result"][
            "plan"
        ] = inputs.a
    elif mutation == "different_dates":
        inputs.records[request["valuation_b"]["id"]]["data"]["result"][
            "valuation_date"
        ] = "2026-09-29"
    elif mutation == "different_company":
        inputs.records[request["valuation_b"]["id"]]["data"]["result"][
            "company"
        ] = "alpha"
    elif mutation == "invalid_unit":
        request["unit_type"] = "percentage"
    else:
        request["shareholders_a"][0]["units"] = inputs.fact("60000.1")
    with pytest.raises(inputs.engine.CaseError):
        inputs.derive("ExchangeModel", request)


@pytest.mark.parametrize(
    "wholly,expected,difference_type",
    [(False, "-260000.00", "concambio"), (True, "180000.00", "annullamento")],
)
def test_accounting_bridge_reconciles_with_reviewed_difference_allocation(
    inputs, wholly, expected, difference_type
):
    request = inputs.bridge(wholly)
    result, issues = inputs.derive("BookBridge", request)
    assert result["difference_signed_debit"] == expected
    assert result["difference_type"] == difference_type
    assert result["opening_residual"] == "0.00"
    assert result["automatic_goodwill"] is False
    assert issues == []


def test_unallocated_difference_is_visible_and_unapprovable(inputs):
    request = inputs.bridge(True)
    request["difference_allocations"] = []
    result, issues = inputs.derive("BookBridge", request)
    assert result["opening_balances"][-1]["category"] == "unallocated"
    assert issues == ["difference_allocation_requires_professional_policy"]


@pytest.mark.parametrize(
    "target_balance,eligible,expected",
    [
        ("-100", True, []),
        ("-98", True, ["unresolved_intercompany:receivable:payable:2.00"]),
        ("-100", False, ["unresolved_intercompany:receivable:payable:0.00"]),
    ],
)
def test_intercompany_difference_is_retained_without_forcing_balance(
    inputs, target_balance, eligible, expected
):
    request = inputs.bridge(True)
    request["balances_a"].extend(
        [
            inputs.account("receivable", "asset", "100"),
            inputs.account("funding", "liability", "-100"),
        ]
    )
    request["balances_b"].extend(
        [
            inputs.account("payable", "liability", target_balance),
            inputs.account("cash_addition", "asset", str(-int(target_balance))),
        ]
    )
    request["eliminations"] = [
        {
            "a": "receivable",
            "b": "payable",
            "eligible": inputs.fact(eligible, "boolean"),
        }
    ]
    _, issues = inputs.derive("BookBridge", request)
    assert issues == expected


def test_unbalanced_trial_balance_remains_an_exception(inputs):
    request = inputs.bridge()
    request["balances_b"][0]["balance"] = inputs.fact("500100")
    _, issues = inputs.derive("BookBridge", request)
    assert issues == [
        "opening_balance_does_not_reconcile",
        "opening_journal_does_not_reconcile",
        "unbalanced_target_trial_balance",
    ]


def test_fiscal_cost_and_book_value_are_not_conflated(inputs):
    request = inputs.bridge(True)
    request["tax_register"] = [
        {
            "id": "asset_1",
            "owner": inputs.fact("Beta", "text"),
            "category": "asset",
            "book": inputs.fact("680000"),
            "tax": inputs.fact("500000"),
            "assessment": inputs.fact("Professional review required", "text"),
        }
    ]
    result, _ = inputs.derive("BookBridge", request)
    assert result["tax_register"][0]["book"] == "680000.00"
    assert result["tax_register"][0]["tax"] == "500000.00"


@pytest.mark.parametrize(
    "anchor,count,unit,expected",
    [
        ("2026-01-31", 1, "months", "2026-02-28"),
        ("2024-01-31", 1, "months", "2024-02-29"),
        ("2026-03-31", 6, "months", "2026-09-30"),
        ("2026-03-31", 180, "days", "2026-09-27"),
        ("2026-09-30", -6, "months", "2026-03-30"),
        ("2026-12-31", 1, "days", "2027-01-01"),
    ],
)
def test_calendar_preserves_calendar_months_and_day_convention(
    inputs, anchor, count, unit, expected
):
    request = inputs.calendar(anchor, count, unit)
    result, issues = inputs.derive("Deadline", request)
    assert result["events"][0]["computed_boundary"] == expected
    assert issues == []


def test_calendar_uses_last_evidenced_company_event(inputs):
    request = inputs.calendar("2026-09-01", 30, "days")
    request["events"][0]["anchors"].append(inputs.fact("2026-09-03", "date"))
    result, _ = inputs.derive("Deadline", request)
    assert result["events"][0]["computed_boundary"] == "2026-10-03"


@pytest.mark.parametrize(
    "constraint,actual,issues",
    [
        ("not_before", "2026-01-30", ["calendar_violation:event"]),
        ("not_before", "2026-02-28", []),
        ("not_after", "2026-03-01", ["calendar_violation:event"]),
    ],
)
def test_calendar_checks_actual_dates_without_authorizing_execution(
    inputs, constraint, actual, issues
):
    request = inputs.calendar(actual=actual)
    request["events"][0]["constraint"] = constraint
    result, found = inputs.derive("Deadline", request)
    assert found == issues
    assert result["execution_permission"] == "not_determined_by_calendar"


def test_calendar_keeps_raw_and_professionally_adjusted_boundary(inputs):
    request = inputs.calendar()
    request["events"][0].update(
        adjusted_boundary=inputs.fact("2026-03-02", "date"),
        adjustment_reason=inputs.fact("Reviewed nonworking-day convention", "text"),
    )
    result, _ = inputs.derive("Deadline", request)
    assert result["events"][0]["computed_boundary"] == "2026-02-28"
    assert result["events"][0]["reviewed_boundary"] == "2026-03-02"


@pytest.mark.parametrize(
    "field,value",
    [
        ("count", True),
        ("count", 1201),
        ("unit", "business_days"),
        ("constraint", "approved"),
        ("anchors", []),
    ],
)
def test_calendar_rejects_implicit_or_invalid_computation_conventions(
    inputs, field, value
):
    request = inputs.calendar()
    request["events"][0][field] = value
    with pytest.raises(inputs.engine.CaseError):
        inputs.derive("Deadline", request)


def test_request_cannot_mix_two_versions_of_one_input(inputs):
    old = inputs.fact("10")
    newer = {**old, "version": 2}
    with pytest.raises(inputs.engine.CaseError, match="mix revisions"):
        inputs.engine.selected_references({"old": old, "new": newer})


@pytest.fixture
def prepared(inputs, tmp_path):
    module = importlib.import_module("fusione_p1_demo")
    return module.prepare_case(tmp_path.resolve() / "ordinary", "ordinary_domestic_oic")


def test_real_archive_adapter_and_p1_demo_persist_both_complete_cases(inputs, tmp_path):
    module = importlib.import_module("fusione_p1_demo")
    result = module.run_p1_demo(tmp_path.resolve() / "demo")
    assert result["passed"] is True
    assert len(result["checks"]) == 16
    assert Path(result["reports"]["ordinary_domestic_oic"]["review_html"]).is_file()
    assert "Independent professional validation" in result["not_run"]


def test_reopening_case_preserves_exact_p1_approval_and_archive_receipt(prepared):
    module = importlib.import_module("fusione_case")
    reopened = module.CaseStore(prepared.store.root, "synthetic_reviewer")
    assert reopened.status("dossier")["review_state"] == "approved_for_defined_scope"
    assert (
        reopened.read("evidence_units_a")["data"]["archive_receipt"]["client_id"]
        == "client_000000000000000000000001"
    )


def test_unknown_input_is_persisted_as_blocked_workpaper_without_zero_default(prepared):
    module = importlib.import_module("fusione_case")
    store = prepared.store
    old = store.read("equity_alpha")
    unknown = store.put(
        old["id"],
        "Fact",
        {**old["data"], "fact_status": "unknown", "value": None},
        scope=old["scope"],
        dependencies=old["dependencies"],
        expected_version=1,
    )
    request = copy.deepcopy(store.read("valuation_a")["data"]["request"])
    request["value"] = module.reference(unknown)
    row = store.workpaper("blocked_valuation", "Valuation", request, expected_version=0)
    assert row["data"]["result"] is None
    assert row["data"]["issues"] == ["unknown:equity_alpha"]


def test_new_planned_year_reopens_rule_bound_workpapers(prepared):
    store = prepared.store
    old = store.read("operation")
    store.put(
        "operation",
        "Operation",
        {**old["data"], "planned_date": "2027-01-01"},
        scope=[],
        dependencies=[],
        expected_version=1,
    )
    assert "rule_outside_declared_period:rule" in store.status("plan")["issues"]
    assert store.status("dossier")["review_state"] == "needs_review"


def test_cross_company_actor_cannot_import_another_archive(prepared):
    module = importlib.import_module("fusione_case")
    prepared.store.grant("alpha_editor", role="editor", entities=["alpha"])
    store = module.CaseStore(prepared.store.root, "alpha_editor")
    with pytest.raises(module.CaseError, match="company scopes"):
        store.import_archive(
            "foreign",
            prepared.bindings["beta"],
            "input_invalid",
            locator="row",
            description="Denied input",
        )


def test_archive_binding_rejects_wrong_declared_client(prepared):
    module = importlib.import_module("fusione_case")
    root, _, engagement = prepared.clients["alpha"]
    with pytest.raises(module.CaseError, match="identities"):
        prepared.store.bind_archive(
            "wrong", "alpha", root, "client_ffffffffffffffffffffffff", engagement
        )


def test_generic_writer_cannot_forge_computed_output(prepared):
    module = importlib.import_module("fusione_case")
    row = prepared.store.read("exchange")
    with pytest.raises(module.CaseError, match="operation"):
        prepared.store.put(
            "forged",
            "ExchangeModel",
            row["data"],
            scope=row["scope"],
            dependencies=row["dependencies"],
            expected_version=0,
        )


def test_dossier_html_escapes_model_authored_content(inputs, tmp_path):
    module = importlib.import_module("fusione_dossier")
    report = {
        "synthetic": True,
        "records": [
            {
                "record": {
                    "id": "draft",
                    "kind": "LegalDocument",
                    "version": 1,
                    "dependencies": [],
                    "data": {
                        "engine_version": "fusione.p1.v1",
                        "result": {"title": "<script>alert('unsafe')</script>"},
                        "issues": [],
                    },
                },
                "status": {"review_state": "unapproved", "issues": []},
            }
        ],
    }
    paths = module.write_workpapers(report, tmp_path)
    content = Path(paths["review_html"]).read_text()
    assert "<script>" not in content
    assert "&lt;script&gt;" in content
    assert "Content-Security-Policy" in content


def test_cli_workpaper_writes_and_returns_stored_p1_result(prepared, tmp_path, capsys):
    module = importlib.import_module("run_fusione")
    request = {
        "action": "workpaper",
        "object_id": "exchange_again",
        "kind": "ExchangeModel",
        "expected_version": 0,
        "request": prepared.store.read("exchange")["data"]["request"],
    }
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request))
    outcome = module.main(
        [
            "apply",
            "--case",
            str(prepared.store.root),
            "--actor",
            "synthetic_reviewer",
            "--request",
            str(path),
        ]
    )
    assert outcome == 0
    assert (
        json.loads(capsys.readouterr().out)["data"]["result"]["new_units"] == "40000/1"
    )


@pytest.mark.parametrize(
    "wholly,credit_account,credit",
    [(False, "new_capital", "-40000.00"), (True, "a_investment", "-480000.00")],
)
def test_opening_journal_contains_takeover_and_balanced_consideration(
    inputs, wholly, credit_account, credit
):
    request = inputs.bridge(wholly)
    result, issues = inputs.derive("BookBridge", request)
    assert result["opening_journal"] == [
        {
            "account": "b_assets",
            "signed_debit": "500000.00",
            "reason": "target asset/liability assumption",
        },
        {
            "account": "b_liabilities",
            "signed_debit": "-200000.00",
            "reason": "target asset/liability assumption",
        },
        {
            "account": credit_account,
            "signed_debit": credit,
            "reason": (
                "participation cancellation"
                if wholly
                else "new capital for target shareholders"
            ),
        },
        {
            "account": "allocation_reviewed_difference",
            "signed_debit": "180000.00" if wholly else "-260000.00",
            "reason": "reviewed difference allocation",
        },
    ]
    assert result["journal_residual"] == "0.00"
    assert issues == []


def test_unknown_participation_account_is_an_explicit_input_error(inputs):
    request = inputs.bridge(True)
    request["investment_account"] = "missing"
    with pytest.raises(inputs.engine.CaseError, match="Participation account"):
        inputs.derive("BookBridge", request)


def test_unknown_elimination_account_is_an_explicit_input_error(inputs):
    request = inputs.bridge()
    request["eliminations"] = [
        {"a": "missing", "b": "liabilities", "eligible": inputs.fact(True, "boolean")}
    ]
    with pytest.raises(inputs.engine.CaseError, match="Elimination account"):
        inputs.derive("BookBridge", request)


def test_dossier_cannot_be_approved_until_new_workpaper_version_is_reviewed(prepared):
    module = importlib.import_module("fusione_case")
    store = prepared.store
    request = copy.deepcopy(store.read("dossier")["data"]["request"])
    new_calendar = store.workpaper(
        "calendar_new",
        "Deadline",
        store.read("calendar")["data"]["request"],
        expected_version=0,
    )
    request["calendar"] = module.reference(new_calendar)
    draft = store.workpaper("dossier_new", "LegalDocument", request, expected_version=0)
    with pytest.raises(module.CaseError, match="input_unapproved:calendar_new"):
        prepared.approve(draft)


def test_changed_archive_bytes_cannot_be_imported_under_old_receipt(prepared):
    module = importlib.import_module("fusione_case")
    evidence = prepared.store.read("evidence_units_a")["data"]
    Path(evidence["source_path"]).write_text("Changed after receipt")
    with pytest.raises(module.CaseError, match="match|changed|mismatch"):
        prepared.store.import_archive(
            "changed_bytes",
            prepared.bindings["alpha"],
            evidence["archive_receipt"]["input_id"],
            locator="JSON",
            description="Corrupt selected source",
        )


def test_changed_liability_demo_preserves_new_evidenced_value(inputs, tmp_path):
    module = importlib.import_module("fusione_p1_demo")
    module.run_p1_demo(tmp_path.resolve() / "revised")
    store = module.CaseStore(
        tmp_path.resolve() / "revised/ordinary_domestic_oic/case", "synthetic_reviewer"
    )
    revision = store.read("beta_liabilities")
    source = json.loads(store.document_bytes(revision["dependencies"][0]["id"]))
    assert revision["version"] == 2
    assert source["value"] == revision["data"]["value"] == "-200100"
    assert store.read("beta_liabilities", 1)["data"]["value"] == "-200000"
