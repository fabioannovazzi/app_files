import pytest

from modules.check_entries.pdf_matching import (
    build_pdf_map,
    movement_from_filename,
)


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("001-intro.pdf", "001"),  # leading zeros retained
        ("foo123bar.pdf", "123"),  # first digit sequence in stem
        ("dir123/foo45bar.pdf", "45"),  # only stem is considered (not parent dirs)
        ("no_digits_here.pdf", None),  # no digits
        ("report.2021.final.pdf", "2021"),  # multi-suffix stems keep digits
    ],
)
def test_movement_from_filename_various_cases(filename, expected):
    assert movement_from_filename(filename) == expected


def test_build_pdf_map_basic_and_duplicate_names_ignored():
    class Obj:
        def __init__(self, name: str):
            self.name = name

    o1 = Obj("001-intro.pdf")
    o2 = Obj("20 appendix.pdf")
    o3 = Obj("001-intro.pdf")  # duplicate filename; should be ignored

    mapping = build_pdf_map([o1, o2, o3])

    assert set(mapping.keys()) == {"001", "20"}
    assert mapping["001"] is o1  # duplicate name did not replace first
    assert mapping["20"] is o2


def test_build_pdf_map_raises_on_conflicting_names_same_movement():
    class Obj:
        def __init__(self, name: str):
            self.name = name

    a = Obj("10-a.pdf")
    b = Obj("10-b.pdf")

    with pytest.raises(ValueError, match=r"Duplicate row number 10"):
        build_pdf_map([a, b])


def test_build_pdf_map_uses_str_fallback_and_ignores_no_digit_files():
    class NoName:
        def __init__(self, s: str):
            self._s = s

        def __str__(self) -> str:  # used when no `name` attribute exists
            return self._s

    fallback_obj = NoName("77-foo.pdf")
    ignored_obj = NoName("nodigitsfile.pdf")

    mapping = build_pdf_map([fallback_obj, ignored_obj])

    assert set(mapping.keys()) == {"77"}
    assert mapping["77"] is fallback_obj
