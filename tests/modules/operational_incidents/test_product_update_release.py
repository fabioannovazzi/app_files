"""An update remedy must verify the affected product, never another product's ZIP."""

from __future__ import annotations

import json
from zipfile import ZipFile

import pytest

from scripts.manage_incidents import verify_update_release


def release(root, product, version, *, cowork_version=None):
    for path, manifest, observed in (
        (
            f"plugin_packages/{product}/{product}-plugin.zip",
            ".codex-plugin/plugin.json",
            version,
        ),
        (
            f"static/shared/{product}/downloads/{product}-cowork-plugin.zip",
            ".claude-plugin/plugin.json",
            cowork_version or version,
        ),
    ):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(target, "w") as archive:
            archive.writestr(
                manifest, json.dumps({"name": product, "version": observed})
            )


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
def test_update_accepts_exact_affected_product_release(tmp_path, product):
    release(tmp_path, product, "0.1.123")

    assert verify_update_release(tmp_path, product, "0.1.123") is None


@pytest.mark.parametrize("product", ["clara", "lucia"])
def test_vera_release_cannot_validate_another_products_update(tmp_path, product):
    release(tmp_path, "vera", "0.1.123")
    release(tmp_path, product, "0.1.122")

    with pytest.raises(ValueError, match=product.title()):
        verify_update_release(tmp_path, product, "0.1.123")


def test_update_rejects_mismatched_cowork_release(tmp_path):
    release(tmp_path, "clara", "0.1.123", cowork_version="0.1.122")

    with pytest.raises(ValueError, match="both hosts"):
        verify_update_release(tmp_path, "clara", "0.1.123")
