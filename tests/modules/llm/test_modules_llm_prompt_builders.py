from modules.utilities.config import get_naming_params
from modules.llm.prompt_builders import add_prompt_date


def test_add_prompt_date_appends_period():
    # Arrange
    naming = get_naming_params()
    chart_dict = {naming["toPlotPeriod"]: "2024Q4"}
    base = "Context:"

    # Act
    result = add_prompt_date(base, chart_dict)

    # Assert
    assert result == base + " Data refers to the 2024Q4 period. "
