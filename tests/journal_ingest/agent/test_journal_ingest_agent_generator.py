import sys
from pathlib import Path

import pytest

try:
    from journal_ingest.agent.generator import generate_layout
except ModuleNotFoundError:  # Fallback for src/ layout without editable install
    src_root = Path(__file__).resolve().parents[3] / "src"
    if src_root.is_dir():
        sys.path.insert(0, str(src_root))
    # Clear any partially-imported namespace package from earlier attempt
    sys.modules.pop("journal_ingest", None)
    sys.modules.pop("journal_ingest.agent", None)
    from journal_ingest.agent.generator import generate_layout


def test_generate_layout_raises_not_implemented_with_clear_message():
    # Arrange & Act / Assert
    with pytest.raises(NotImplementedError) as excinfo:
        generate_layout(b"fake pdf bytes")

    # Assert: explicit, stable error message
    assert str(excinfo.value) == "Agent generation is not implemented."


@pytest.mark.parametrize(
    "file_bytes, meta",
    [
        (b"", None),
        (b"%PDF-1.4\n", {}),
        (b"some bytes", {"pages": 2}),
    ],
)
def test_generate_layout_always_raises_not_implemented_for_any_input(file_bytes, meta):
    # Arrange & Act / Assert
    with pytest.raises(NotImplementedError):
        generate_layout(file_bytes, meta)
