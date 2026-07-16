import pytest

from modules.add_attributes.validators import is_valid_product_name


@pytest.mark.parametrize(
    "name",
    [
        "Widget 3000",  # typical product name
        "X",  # shortest non-empty meaningful name
        "  Tire  ",  # surrounding whitespace is ignored
    ],
)
def test_is_valid_product_name_golden(name):
    # Act
    result = is_valid_product_name(name)

    # Assert
    assert result is True


@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",
        "\n\t",
    ],
)
def test_is_valid_product_name_empty_or_whitespace_is_invalid(name):
    # Act
    result = is_valid_product_name(name)

    # Assert
    assert result is False


@pytest.mark.parametrize(
    "name",
    [
        "N/A",
        "n/a",
        "NA",
        " na ",
        "  n/A  ",
    ],
)
def test_is_valid_product_name_placeholders_are_invalid_case_insensitive(name):
    # Act
    result = is_valid_product_name(name)

    # Assert
    assert result is False


@pytest.mark.parametrize("value", [None, 0, 1.23, ["n/a"], {"name": "N/A"}])
def test_is_valid_product_name_rejects_non_string_inputs(value):
    # Act
    result = is_valid_product_name(value)  # type: ignore[arg-type]

    # Assert
    assert result is False
