import pytest

from modules.check_entries.prompts import (
    compare_beneficiary_prompt,
    extract_beneficiary_prompt,
)


def test_extract_beneficiary_prompt_includes_hints_and_schema():
    # Arrange
    text = "Beneficiary: Alice Co.\nAmount: 100.00\nDate: 2024-05-06"
    amount = "100.00"
    date = "2024-05-06"

    # Act
    prompt = extract_beneficiary_prompt(text, amount=amount, date=date)

    # Assert
    assert isinstance(prompt, dict)

    # input structure and roles
    assert "input" in prompt and isinstance(prompt["input"], list)
    assert len(prompt["input"]) == 2
    system, user = prompt["input"]
    assert system == {
        "role": "system",
        "content": "You are a helpful assistant. Reply in JSON only.",
    }
    assert user["role"] == "user"

    # user content includes hints and PDF text
    content = user["content"]
    assert "Read the following bank statement text" in content
    assert (
        "Labels such as 'Beneficiary', 'Ultimate Creditor', 'Receiver', or 'IBAN holder'"
        in content
    )
    assert f"The relevant transaction amount is {amount}." in content
    assert f"The transaction date is {date}." in content
    assert "PDF text:\n" + text in content

    # schema contract
    assert prompt["text"]["format"]["type"] == "json_schema"
    schema = prompt["text"]["schema"]
    assert schema["name"] == "extract_beneficiary"
    props = schema["schema"]["properties"]
    assert set(schema["schema"]["required"]) == {
        "status",
        "explanation",
        "beneficiary_extracted",
    }
    assert "candidate_names" in props and props["candidate_names"]["type"] == "array"
    assert props["candidate_names"]["items"]["type"] == "string"


def test_extract_beneficiary_prompt_omits_hints_when_none():
    # Arrange
    text = "Receiver: Bob"

    # Act
    prompt = extract_beneficiary_prompt(text)

    # Assert
    user_content = prompt["input"][1]["content"]
    assert "transaction amount" not in user_content
    assert "transaction date" not in user_content
    assert "PDF text:\n" + text in user_content


def test_compare_beneficiary_prompt_intro_and_schema():
    # Arrange
    text = "Ultimate Creditor: ACME LTD"
    expected = "ACME LTD"

    # Act
    prompt = compare_beneficiary_prompt(text, expected)

    # Assert
    # Intro line includes quoted expected name
    user_content = prompt["input"][1]["content"]
    assert (
        "Extract the payee/beneficiary name and compare it to 'ACME LTD'."
        in user_content
    )
    assert "PDF text:\n" + text in user_content

    # Schema expectations
    schema = prompt["text"]["schema"]
    assert schema["name"] == "compare_beneficiary"
    required = set(schema["schema"]["required"])  # order-insensitive
    assert required == {"status", "beneficiary_extracted", "name_similarity", "explanation"}
    name_sim = schema["schema"]["properties"]["name_similarity"]
    assert name_sim["type"] == "number"
    assert name_sim["minimum"] == 0 and name_sim["maximum"] == 100
