from modules.llm.function_calls import mapping_examples


def test_mapping_examples_include_spanish_journal_columns() -> None:
    examples = mapping_examples()

    assert "Example 7 (Spanish" in examples
    assert '"Fecha"' in examples
    assert '"N.º asiento"' in examples
    assert '"Debe"' in examples
    assert '"Haber"' in examples
