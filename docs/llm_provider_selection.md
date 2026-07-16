# LLM Provider Selection

Every task retrieves its LLM provider and model through [`select_provider`](../modules/utilities/config.py) in `modules.utilities.config`. The function centralizes provider and model choices in a `QueryChoiceDict`, ensuring consistent configuration across the system.

To update which provider or model a task uses, modify the appropriate entry in the `QueryChoiceDict` inside `select_provider`.

Representative call sites include:

- [`modules/llm/model_router.py`](../modules/llm/model_router.py)
- [`src/check_statements_logic.py`](../src/check_statements_logic.py)

