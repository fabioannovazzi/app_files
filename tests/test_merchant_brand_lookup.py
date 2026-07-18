import json
import sys
import types
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:  # pragma: no cover - exercised implicitly by imports
    import modules.utilities.cache  # type: ignore
    import modules.utilities.config  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    modules_pkg = sys.modules.setdefault("modules", types.ModuleType("modules"))
    setattr(modules_pkg, "__path__", [str(ROOT / "modules")])
    utilities_pkg = sys.modules.setdefault(
        "modules.utilities", types.ModuleType("modules.utilities")
    )
    setattr(utilities_pkg, "__path__", [str(ROOT / "modules" / "utilities")])

    cache_module = types.ModuleType("modules.utilities.cache")

    def _default_cache_path(name: str) -> Path:
        return Path(name)

    cache_module.get_cache_path = _default_cache_path  # type: ignore[attr-defined]
    sys.modules["modules.utilities.cache"] = cache_module

    config_module = types.ModuleType("modules.utilities.config")

    def _default_get_naming_params() -> Dict[str, str]:
        return {}

    config_module.get_naming_params = (  # type: ignore[attr-defined]
        _default_get_naming_params
    )
    sys.modules["modules.utilities.config"] = config_module

import pytest

import src.merchant_brand_lookup as mbl

LOOKUP_NAMING = {
    "merchantBrandWebsiteLookup": "step",
    "industry": "industry",
    "industryDescription": "industry_description",
}


@pytest.fixture(autouse=True)
def _market_context():
    """Provide default industry context so lookups can proceed."""

    mbl.set_lookup_market_context(industry="cosmetics")
    yield
    mbl.set_lookup_market_context()


def _patch_storage(monkeypatch, tmp_path: Path) -> Path:
    """Point module storage to a temp file and reset cache."""
    fp = tmp_path / "web.json"
    monkeypatch.setattr(mbl, "FILE_PATH", fp, raising=False)
    monkeypatch.setattr(mbl, "SEED_PATH", tmp_path / "seed.json", raising=False)
    monkeypatch.setattr(mbl, "_WEBSITE_CACHE", None, raising=False)
    meta_fp = tmp_path / "web_meta.json"
    monkeypatch.setattr(mbl, "META_PATH", meta_fp, raising=False)
    return fp


@pytest.mark.parametrize(
    "content,expected",
    [
        (None, {}),  # file missing
        ("{not json", {}),  # invalid JSON
        (
            json.dumps({"acme": "https://acme.com", "globex": None}),
            {"acme": "https://acme.com", "globex": None},
        ),
    ],
)
def test_load_mapping_handles_file_states(tmp_path, monkeypatch, content, expected):
    # Arrange
    fp = _patch_storage(monkeypatch, tmp_path)
    if content is not None:
        fp.write_text(content)

    # Act
    mapping = mbl.load_mapping()

    # Assert
    assert mapping == expected


def test_load_mapping_overlays_writable_cache_on_tracked_seed(tmp_path, monkeypatch):
    fp = _patch_storage(monkeypatch, tmp_path)
    mbl.SEED_PATH.write_text(
        json.dumps(
            {
                "seed only": "https://seed.example",
                "shared": "https://seed-shared.example",
            }
        ),
        encoding="utf-8",
    )
    fp.write_text(
        json.dumps(
            {
                "cache only": "https://cache.example",
                "shared": "https://cache-shared.example",
            }
        ),
        encoding="utf-8",
    )

    mapping = mbl.load_mapping()

    assert mapping == {
        "cache only": "https://cache.example",
        "seed only": "https://seed.example",
        "shared": "https://cache-shared.example",
    }


def test_lookup_websites_adds_and_persists_new_entries(tmp_path, monkeypatch):
    # Arrange
    fp = _patch_storage(monkeypatch, tmp_path)
    # Stub config resolution used by lookup
    monkeypatch.setattr(
        mbl,
        "get_naming_params",
        lambda: LOOKUP_NAMING,
        raising=False,
    )

    called = {}

    def fake_run_step_json(
        llm_wrapper, step, system, prompts, tools, tool_choice, service_tier
    ):
        # record call parameters for assertions
        called["step"] = step
        called["prompts_len"] = len(prompts)
        results = []
        for p in prompts:
            # extract the quoted name from the prompt
            name = p.split("'")[1]
            if name.lower() == "globex":
                results.append({"website": ""})  # treated as missing -> None
            else:
                results.append({"website": f"https://{name}.com"})
        return results

    monkeypatch.setattr(mbl, "run_step_json", fake_run_step_json, raising=False)

    # Act
    out = mbl.lookup_websites(
        llm_wrapper=object(), names=["Acme", "Globex"]
    )  # two new entries

    # Assert
    assert out["acme"] == "https://acme.com"
    assert out["globex"] is None  # empty website becomes None
    # persisted
    on_disk = json.loads(fp.read_text())
    assert on_disk == out
    # called once with two prompts and correct step label
    assert called["prompts_len"] == 2
    assert called["step"] == "step"


def test_lookup_websites_uses_aliases_and_skips_existing(tmp_path, monkeypatch):
    # Arrange
    fp = _patch_storage(monkeypatch, tmp_path)
    existing = {"acme corp": "https://acme.example"}
    fp.write_text(json.dumps(existing))
    # Ensure subsequent load reads from file
    monkeypatch.setattr(mbl, "_WEBSITE_CACHE", None, raising=False)
    # Stub config
    monkeypatch.setattr(
        mbl,
        "get_naming_params",
        lambda: LOOKUP_NAMING,
        raising=False,
    )

    def should_not_be_called(*args, **kwargs):  # no lookups expected
        raise AssertionError(
            "run_step_json should not be called when nothing is missing"
        )

    monkeypatch.setattr(mbl, "run_step_json", should_not_be_called, raising=False)

    # Act
    out = mbl.lookup_websites(
        llm_wrapper=None, names=[" ACME ", "acme"], aliases={"acme": "acme corp"}
    )

    # Assert
    assert out == existing  # no changes
    assert json.loads(fp.read_text()) == existing


def test_save_mapping_merges_on_disk_updates(tmp_path, monkeypatch):
    # Arrange
    fp = _patch_storage(monkeypatch, tmp_path)
    mapping = mbl.load_mapping()
    mapping["alpha"] = "https://alpha.com"
    mbl._save_mapping(mapping)

    # Simulate another process writing new data to disk before the next save.
    fp.write_text(
        json.dumps(
            {
                "alpha": "https://alpha.com",
                "beta": "https://beta.com",
            },
            indent=2,
            sort_keys=True,
        )
    )

    mapping["gamma"] = "https://gamma.com"

    # Act
    mbl._save_mapping(mapping)

    # Assert
    merged = json.loads(fp.read_text())
    assert merged == {
        "alpha": "https://alpha.com",
        "beta": "https://beta.com",
        "gamma": "https://gamma.com",
    }
    assert mapping == merged
    assert mbl._WEBSITE_CACHE == mapping


def test_save_meta_merges_on_disk_updates(tmp_path, monkeypatch):
    # Arrange
    _patch_storage(monkeypatch, tmp_path)
    meta_path = mbl.META_PATH
    meta: Dict[str, Dict[str, str]] = {
        "alpha": {"last_failed": "2024-01-01T00:00:00+00:00"}
    }
    mbl._save_meta(meta)

    meta_path.write_text(
        json.dumps(
            {
                "alpha": {"last_failed": "2024-01-01T00:00:00+00:00"},
                "beta": {"last_failed": "2024-01-02T00:00:00+00:00"},
            },
            indent=2,
            sort_keys=True,
        )
    )

    meta["gamma"] = {"last_failed": "2024-01-03T00:00:00+00:00"}

    # Act
    mbl._save_meta(meta)

    # Assert
    merged = json.loads(meta_path.read_text())
    assert merged == {
        "alpha": {"last_failed": "2024-01-01T00:00:00+00:00"},
        "beta": {"last_failed": "2024-01-02T00:00:00+00:00"},
        "gamma": {"last_failed": "2024-01-03T00:00:00+00:00"},
    }
    assert meta == merged


def test_save_mapping_interleaved_writers_preserve_entries(tmp_path, monkeypatch):
    # Arrange
    fp = _patch_storage(monkeypatch, tmp_path)
    # Simulate two separate writers working with independent dictionaries.
    writer_one = dict(mbl.load_mapping())
    writer_two = dict(writer_one)

    writer_one["alpha"] = "https://alpha.com"
    mbl._save_mapping(writer_one)

    writer_two["beta"] = "https://beta.com"

    # Act
    mbl._save_mapping(writer_two)

    # Assert
    merged = json.loads(fp.read_text())
    assert merged == {
        "alpha": "https://alpha.com",
        "beta": "https://beta.com",
    }
    assert writer_two == merged
    assert mbl._WEBSITE_CACHE == merged


def test_save_meta_interleaved_writers_preserve_entries(tmp_path, monkeypatch):
    # Arrange
    _patch_storage(monkeypatch, tmp_path)
    writer_one = {"alpha": {"last_failed": "2024-01-01T00:00:00+00:00"}}
    writer_two = dict(writer_one)

    mbl._save_meta(writer_one)

    writer_two["beta"] = {"last_failed": "2024-01-02T00:00:00+00:00"}

    # Act
    mbl._save_meta(writer_two)

    # Assert
    merged = json.loads(mbl.META_PATH.read_text())
    assert merged == {
        "alpha": {"last_failed": "2024-01-01T00:00:00+00:00"},
        "beta": {"last_failed": "2024-01-02T00:00:00+00:00"},
    }
    assert writer_two == merged
