import sys
import pytest
from pathlib import Path

# Ensure 'src' is on sys.path so 'statements' resolves from the real package
SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from statements.ingest import DocumentIngestor, Document


@pytest.mark.parametrize(
    "ext, expected_method",
    [
        (".csv", "_load_csv"),
        (".xlsx", "_load_xlsx"),
        (".pdf", "_load_pdf"),
    ],
)
def test_ingest_dispatches_to_correct_loader(tmp_path: Path, ext: str, expected_method: str):
    # Arrange
    file_path = tmp_path / f"sample{ext}"
    file_path.write_text("dummy")
    ingestor = DocumentIngestor()

    calls: list[Path] = []

    def expected_stub(path: Path) -> Document:  # type: ignore[override]
        calls.append(path)
        return Document(path=path, kind="expected")

    def forbidden_stub(path: Path):  # type: ignore[override]
        raise AssertionError("Wrong loader called")

    # Patch only the instance methods to avoid executing real loaders
    setattr(ingestor, expected_method, expected_stub)
    for other in {"_load_csv", "_load_xlsx", "_load_pdf"} - {expected_method}:
        setattr(ingestor, other, forbidden_stub)

    # Act
    result = ingestor.ingest(str(file_path))

    # Assert
    assert isinstance(result, Document)
    assert result.kind == "expected"
    assert calls == [file_path]


@pytest.mark.parametrize(
    "ext, expected_method",
    [
        (".CSV", "_load_csv"),
        (".XLS", "_load_xlsx"),
    ],
)
def test_ingest_is_case_insensitive_and_handles_xls(tmp_path: Path, ext: str, expected_method: str):
    # Arrange
    file_path = tmp_path / f"doc{ext}"
    file_path.write_text("dummy")
    ingestor = DocumentIngestor()

    seen: list[Path] = []

    def expected_stub(path: Path) -> Document:  # type: ignore[override]
        seen.append(path)
        return Document(path=path, kind="ok")

    def forbidden_stub(path: Path):  # type: ignore[override]
        raise AssertionError("Wrong loader called")

    setattr(ingestor, expected_method, expected_stub)
    for other in {"_load_csv", "_load_xlsx", "_load_pdf"} - {expected_method}:
        setattr(ingestor, other, forbidden_stub)

    # Act
    out = ingestor.ingest(str(file_path))

    # Assert
    assert out.kind == "ok"
    assert seen == [file_path]


def test_ingest_unsupported_extension_raises(tmp_path: Path):
    # Arrange
    file_path = tmp_path / "notes.txt"
    file_path.write_text("whatever")
    ingestor = DocumentIngestor()

    # Act / Assert
    with pytest.raises(ValueError) as exc:
        ingestor.ingest(str(file_path))

    assert "Unsupported file type: .txt" in str(exc.value)
