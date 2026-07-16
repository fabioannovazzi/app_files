import logging

import pytest

from modules.check_entries.constants import MismatchSeverity, parse_severity


@pytest.mark.parametrize(
    "value, expected",
    [
        ("critical", MismatchSeverity.CRITICAL),  # direct enum value
        ("Schwerwiegend", MismatchSeverity.MAJOR),  # non-English label alias
        ("MiNoR", MismatchSeverity.MINOR),  # case-insensitive input
    ],
)
def test_parse_severity_known_variants(value, expected):
    # Act
    result = parse_severity(value)

    # Assert
    assert result is expected


@pytest.mark.parametrize("value", [None, ""])  # defaults for falsy inputs
def test_parse_severity_none_or_empty_defaults_minor_no_log(caplog, value):
    caplog.set_level(logging.WARNING, logger="modules.check_entries.constants")

    # Act
    result = parse_severity(value)  # type: ignore[arg-type]

    # Assert
    assert result is MismatchSeverity.MINOR
    # No warning emitted for None/empty inputs
    assert not caplog.records


def test_parse_severity_unknown_value_logs_warning_and_defaults_minor(caplog):
    with caplog.at_level(logging.WARNING, logger="modules.check_entries.constants"):
        # Act
        result = parse_severity("notaseverity")

    # Assert
    assert result is MismatchSeverity.MINOR
    # Exactly one warning about unknown severity with accepted list
    msgs = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(msgs) == 1
    assert "Unknown mismatch severity 'notaseverity'" in msgs[0].message
    assert "Accepted severities:" in msgs[0].message
