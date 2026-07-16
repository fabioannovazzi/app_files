from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, Sequence


class JsonPathError(ValueError):
    """Raised when a JSON path cannot be parsed."""


@dataclass(slots=True)
class _KeyToken:
    name: str


@dataclass(slots=True)
class _IndexToken:
    index: int


@dataclass(slots=True)
class _WildcardToken:
    map_values: bool = False


_Token = _KeyToken | _IndexToken | _WildcardToken


def _parse(expression: str) -> tuple[_Token, ...]:
    if not expression:
        raise JsonPathError("Empty JSON path expression.")

    expr = expression.strip()
    if expr.startswith("$"):
        expr = expr[1:]
    if expr.startswith("."):
        expr = expr[1:]

    tokens: list[_Token] = []
    i = 0
    length = len(expr)
    while i < length:
        char = expr[i]
        if char == ".":
            i += 1
            start = i
            while i < length and expr[i] not in ".[":
                i += 1
            name = expr[start:i].strip()
            if not name:
                raise JsonPathError(f"Invalid JSON path near: {expression!r}")
            tokens.append(_KeyToken(name=name))
        elif char == "[":
            i += 1
            end = expr.find("]", i)
            if end == -1:
                raise JsonPathError(f"Unclosed bracket in JSON path: {expression!r}")
            content = expr[i:end].strip()
            if content == "*":
                tokens.append(_WildcardToken())
            else:
                try:
                    index = int(content)
                except ValueError as exc:
                    raise JsonPathError(f"Invalid array index {content!r}") from exc
                tokens.append(_IndexToken(index=index))
            i = end + 1
        elif char.isspace():
            i += 1
        else:
            start = i
            while i < length and expr[i] not in ".[":
                i += 1
            name = expr[start:i].strip()
            if name:
                tokens.append(_KeyToken(name=name))
    return tuple(tokens)


def _iter_sequence(value) -> Iterator:
    if isinstance(value, (str, bytes)):
        return iter(())
    if isinstance(value, dict):
        return iter(value.values())
    if isinstance(value, Sequence):
        return iter(value)
    return iter(())


def _resolve(data, tokens: Sequence[_Token]) -> tuple:
    current = [data]
    for token in tokens:
        next_values: list = []
        if isinstance(token, _KeyToken):
            for item in current:
                if isinstance(item, dict) and token.name in item:
                    next_values.append(item[token.name])
                elif isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
                    for element in item:
                        if isinstance(element, dict) and token.name in element:
                            next_values.append(element[token.name])
        elif isinstance(token, _IndexToken):
            for item in current:
                if isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
                    try:
                        next_values.append(item[token.index])
                    except IndexError:
                        continue
        elif isinstance(token, _WildcardToken):
            for item in current:
                next_values.extend(_iter_sequence(item))
        current = next_values
    return tuple(current)


def extract_values(data, expression: str) -> tuple:
    tokens = _parse(expression)
    return _resolve(data, tokens)


def extract_first_non_null(data, expressions: Iterable[str]) -> object | None:
    for expression in expressions:
        for value in extract_values(data, expression):
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            return value
    return None


def extract_all_non_empty(data, expressions: Iterable[str]) -> tuple:
    collected: list = []
    for expression in expressions:
        for value in extract_values(data, expression):
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            collected.append(value)
    return tuple(collected)


__all__ = [
    "JsonPathError",
    "extract_all_non_empty",
    "extract_first_non_null",
    "extract_values",
]
