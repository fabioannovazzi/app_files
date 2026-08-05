from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT / "plugins" / "bilancio-xbrl-it" / "scripts" / "build_taxonomy_catalogue.py"
)
VALIDATOR_SCRIPT = (
    ROOT / "plugins" / "bilancio-xbrl-it" / "scripts" / "validate_xbrl.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("bilancio_xbrl_taxonomy", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


taxonomy = _load_module()


class _FakeConcept:
    qname = SimpleNamespace(prefix="itcc", localName="MovementTuple")
    typeQname = SimpleNamespace(prefix="xbrli", localName="stringItemType")
    periodType = None
    balance = None
    isAbstract = False
    isNillable = False
    isItem = False
    isTuple = True
    isDimensionItem = False
    isHypercubeItem = False
    substitutionGroupQname = SimpleNamespace(prefix="xbrli", localName="tuple")

    @staticmethod
    def label(lang: str | None = None) -> str:
        return "Movimenti"


def _load_validator_module():
    spec = importlib.util.spec_from_file_location(
        "bilancio_xbrl_validator", VALIDATOR_SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


validator = _load_validator_module()


def test_parse_entry_points_complete_form_set_is_preserved() -> None:
    values = [
        "ORDINARY=taxonomy/ordinary.xsd",
        "ABBREVIATED=taxonomy/abbreviated.xsd",
        "MICRO=taxonomy/micro.xsd",
    ]

    result = taxonomy._parse_entry_points(values)

    assert result == {
        "ORDINARY": "taxonomy/ordinary.xsd",
        "ABBREVIATED": "taxonomy/abbreviated.xsd",
        "MICRO": "taxonomy/micro.xsd",
    }


def test_concept_record_preserves_item_and_tuple_eligibility() -> None:
    result = taxonomy._concept_record(_FakeConcept())

    assert result["is_item"] is False
    assert result["is_tuple"] is True
    assert result["substitution_group"] == "xbrli:tuple"


def test_parse_entry_points_missing_form_is_rejected() -> None:
    values = [
        "ORDINARY=taxonomy/ordinary.xsd",
        "ABBREVIATED=taxonomy/abbreviated.xsd",
    ]

    with pytest.raises(ValueError, match="requires ordinary, abbreviated, and micro"):
        taxonomy._parse_entry_points(values)


def test_safe_extract_path_traversal_member_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "taxonomy.zip"
    with ZipFile(archive, "w") as package:
        package.writestr("../outside.xsd", "unsafe")

    with pytest.raises(ValueError, match="unsafe path"):
        taxonomy._safe_extract(archive, tmp_path / "extract")


def test_safe_extract_regular_member_writes_inside_destination(tmp_path: Path) -> None:
    archive = tmp_path / "taxonomy.zip"
    with ZipFile(archive, "w") as package:
        package.writestr("taxonomy/entry.xsd", "<schema/>")
    destination = tmp_path / "extract"

    taxonomy._safe_extract(archive, destination)

    assert (destination / "taxonomy" / "entry.xsd").read_text(
        encoding="utf-8"
    ) == "<schema/>"


def test_validator_non_xbrl_root_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = tmp_path / "invalid.xbrl"
    instance.write_text("<xbrl/>", encoding="utf-8")

    captured: list[str] = []

    def fake_run(command, **_kwargs):
        captured.extend(command)
        log_file = Path(command[command.index("--logFile") + 1])
        log_file.write_text(
            '<log><entry level="info" code="info">validated</entry></log>',
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(validator.subprocess, "run", fake_run)

    result = validator.validate_instance(instance, tmp_path / "report.json")

    assert result["status"] == "FAIL"
    assert result["messages"][0]["code"] == "VERA.XBRL_ROOT"
    assert captured[captured.index("--calc") + 1] == "xbrl21"
    assert result["command"][result["command"].index("--calc") + 1] == "xbrl21"


def test_validator_arelle_error_log_fails_even_with_zero_returncode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = tmp_path / "instance.xbrl"
    instance.write_text(
        """<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
        xmlns:link="http://www.xbrl.org/2003/linkbase"
        xmlns:xlink="http://www.w3.org/1999/xlink">
        <link:schemaRef xlink:type="simple" xlink:href="taxonomy.xsd"/>
        <xbrli:context id="current"/>
        </xbrli:xbrl>""",
        encoding="utf-8",
    )

    def fake_run(command, **_kwargs):
        log_file = Path(command[command.index("--logFile") + 1])
        log_file.write_text(
            '<log><entry level="error" code="xbrl.5.1">invalid fact</entry></log>',
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(validator.subprocess, "run", fake_run)

    result = validator.validate_instance(instance, tmp_path / "report.json")

    assert result["status"] == "FAIL"
    assert result["messages"][0]["code"] == "xbrl.5.1"


def test_validator_calculation_inconsistency_fails_with_zero_returncode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = tmp_path / "instance.xbrl"
    instance.write_text(
        """<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
        xmlns:link="http://www.xbrl.org/2003/linkbase"
        xmlns:xlink="http://www.w3.org/1999/xlink">
        <link:schemaRef xlink:type="simple" xlink:href="taxonomy.xsd"/>
        <xbrli:context id="current"/>
        </xbrli:xbrl>""",
        encoding="utf-8",
    )

    def fake_run(command, **_kwargs):
        log_file = Path(command[command.index("--logFile") + 1])
        log_file.write_text(
            '<log><entry level="inconsistency" code="xbrl.5.2.5.2:calcInconsistency">mismatch</entry></log>',
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(validator.subprocess, "run", fake_run)

    result = validator.validate_instance(instance, tmp_path / "report.json")

    assert result["status"] == "FAIL"
    assert result["messages"][0]["code"] == "xbrl.5.2.5.2:calcInconsistency"


@pytest.mark.parametrize("level", ["critical", "exception", "fatal"])
def test_validator_severe_arelle_levels_fail_with_zero_returncode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, level: str
) -> None:
    instance = tmp_path / "instance.xbrl"
    instance.write_text(
        """<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
        xmlns:link="http://www.xbrl.org/2003/linkbase"
        xmlns:xlink="http://www.w3.org/1999/xlink">
        <link:schemaRef xlink:type="simple" xlink:href="taxonomy.xsd"/>
        <xbrli:context id="current"/>
        </xbrli:xbrl>""",
        encoding="utf-8",
    )

    def fake_run(command, **_kwargs):
        log_file = Path(command[command.index("--logFile") + 1])
        log_file.write_text(
            f'<log><entry level="{level}" code="VERA.SEVERE">failure</entry></log>',
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(validator.subprocess, "run", fake_run)

    result = validator.validate_instance(instance, tmp_path / "report.json")

    assert result["status"] == "FAIL"
    assert result["messages"][0]["level"] == level


def test_validator_taxonomy_checksum_mismatch_is_rejected(tmp_path: Path) -> None:
    instance = tmp_path / "instance.xbrl"
    instance.write_text("<xbrl/>", encoding="utf-8")
    package = tmp_path / "taxonomy.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr("taxonomy.xsd", "<schema/>")

    with pytest.raises(ValueError, match="checksum does not match"):
        validator.validate_instance(
            instance,
            tmp_path / "report.json",
            package,
            "0" * 64,
        )
