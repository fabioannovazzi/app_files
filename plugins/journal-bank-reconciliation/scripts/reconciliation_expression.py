"""Fuel-bounded Python expressions for model-authored candidate discovery.

This is an interpreter, not eval/exec or a general Python sandbox. Only JSON
values and the explicitly implemented operations exist. It has no ambient file,
network, import, process, attribute-reflection or mutation capability. Returned
candidates still require source, arithmetic and semantic validation.
"""

from __future__ import annotations

import ast
import operator
from typing import Any

__all__ = ["evaluate_candidates", "ExpressionLimit"]


class ExpressionLimit(ValueError):
    """The supplied expression exceeds the discovery contract."""


class _Interpreter:
    def __init__(self, steps: int, items: int):
        self.steps = steps
        self.items = items

    def bounded(self, value: Any) -> Any:
        if isinstance(value, (str, list, tuple, dict)) and len(value) > self.items:
            raise ExpressionLimit("Expression collection limit exceeded")
        if isinstance(value, (int, float)) and abs(value) > 10**15:
            raise ExpressionLimit("Expression numeric limit exceeded")
        return value

    def visit(self, node: ast.AST, env: dict[str, Any]) -> Any:
        self.steps -= 1
        if self.steps < 0:
            raise ExpressionLimit("Expression operation budget exhausted")
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (str, int, float, bool, type(None))):
                raise ExpressionLimit("Unsupported constant")
            return self.bounded(node.value)
        if isinstance(node, ast.Name):
            if node.id not in env:
                raise ExpressionLimit("Unknown expression name")
            return env[node.id]
        if isinstance(node, (ast.List, ast.Tuple)):
            return self.bounded([self.visit(n, env) for n in node.elts])
        if isinstance(node, ast.Dict):
            if any(k is None for k in node.keys):
                raise ExpressionLimit("Dictionary unpacking is unsupported")
            return self.bounded(
                {
                    self.visit(k, env): self.visit(v, env)
                    for k, v in zip(node.keys, node.values)
                }
            )
        if isinstance(node, ast.Subscript):
            value, key = self.visit(node.value, env), self.visit(node.slice, env)
            if not isinstance(value, dict) or not isinstance(key, str):
                raise ExpressionLimit("Only named source fields may be subscripted")
            return value[key]
        if isinstance(node, ast.UnaryOp):
            value = self.visit(node.operand, env)
            if isinstance(node.op, ast.Not):
                return not value
            if isinstance(node.op, ast.USub) and isinstance(value, (int, float)):
                return self.bounded(-value)
        if isinstance(node, ast.BoolOp):
            for part in node.values:
                value = self.visit(part, env)
                if isinstance(node.op, ast.And) and not value:
                    return value
                if isinstance(node.op, ast.Or) and value:
                    return value
            return value
        if isinstance(node, ast.IfExp):
            return self.visit(
                node.body if self.visit(node.test, env) else node.orelse, env
            )
        if isinstance(node, ast.BinOp):
            left, right = self.visit(node.left, env), self.visit(node.right, env)
            operations = {
                ast.Add: operator.add,
                ast.Sub: operator.sub,
                ast.Mult: operator.mul,
                ast.FloorDiv: operator.floordiv,
                ast.Mod: operator.mod,
            }
            if type(node.op) not in operations or not all(
                isinstance(v, (int, float)) for v in (left, right)
            ):
                raise ExpressionLimit("Only bounded numeric arithmetic is supported")
            return self.bounded(operations[type(node.op)](left, right))
        if isinstance(node, ast.Compare):
            operations = {
                ast.Eq: operator.eq,
                ast.NotEq: operator.ne,
                ast.Lt: operator.lt,
                ast.LtE: operator.le,
                ast.Gt: operator.gt,
                ast.GtE: operator.ge,
                ast.In: lambda a, b: a in b,
                ast.NotIn: lambda a, b: a not in b,
            }
            left = self.visit(node.left, env)
            for op, other in zip(node.ops, node.comparators):
                right = self.visit(other, env)
                if type(op) not in operations:
                    raise ExpressionLimit("Unsupported comparison")
                if not operations[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, (ast.ListComp, ast.GeneratorExp)):
            result = []

            def collect(index: int, scope: dict[str, Any]) -> None:
                if index == len(node.generators):
                    result.append(self.visit(node.elt, scope))
                    self.bounded(result)
                    return
                clause = node.generators[index]
                if not isinstance(clause.target, ast.Name) or clause.is_async:
                    raise ExpressionLimit(
                        "Only simple comprehension variables are supported"
                    )
                values = self.visit(clause.iter, scope)
                if not isinstance(values, (list, tuple, dict, str)):
                    raise ExpressionLimit("Unsupported comprehension input")
                for value in values:
                    self.steps -= 1
                    if self.steps < 0:
                        raise ExpressionLimit("Expression operation budget exhausted")
                    child = {**scope, clause.target.id: value}
                    if all(self.visit(condition, child) for condition in clause.ifs):
                        collect(index + 1, child)

            collect(0, env)
            return result
        if isinstance(node, ast.Call) and not node.keywords:
            args = [self.visit(arg, env) for arg in node.args]
            if isinstance(node.func, ast.Name):
                functions = {"len": len, "abs": abs, "sum": sum, "min": min, "max": max}
                if node.func.id in functions:
                    return self.bounded(functions[node.func.id](*args))
            if isinstance(node.func, ast.Attribute):
                value = self.visit(node.func.value, env)
                if (
                    isinstance(value, dict)
                    and node.func.attr == "get"
                    and 1 <= len(args) <= 2
                ):
                    return value.get(*args)
                if isinstance(value, str):
                    if node.func.attr in {"lower", "casefold", "strip"} and not args:
                        return self.bounded(getattr(value, node.func.attr)())
                    if (
                        node.func.attr == "replace"
                        and len(args) == 2
                        and all(isinstance(a, str) for a in args)
                    ):
                        # Prevent expansion before allocating a replacement string.
                        if len(args[1]) > len(args[0]):
                            raise ExpressionLimit(
                                "Expanding replacements are unsupported"
                            )
                        return self.bounded(value.replace(*args))
            raise ExpressionLimit("Call is outside the expression capability set")
        raise ExpressionLimit(f"Unsupported expression syntax: {type(node).__name__}")


def evaluate_candidates(
    expression: str,
    bank: list[dict],
    journal: list[dict],
    *,
    max_steps: int = 100_000,
    max_items: int = 4096,
) -> list[dict]:
    """Evaluate a discovery expression; never execute Python or allocate matches."""
    if not isinstance(expression, str) or len(expression) > 16_384:
        raise ExpressionLimit("Expression source limit exceeded")
    tree = ast.parse(expression, mode="eval")
    if sum(1 for _ in ast.walk(tree)) > 1024:
        raise ExpressionLimit("Expression syntax limit exceeded")
    # Row IDs are routing handles, never a case-specific rule literal.
    # Generated code expresses relationships between fields, not selected values.
    # Rule parameters (for example a date window) belong in the named tool API.
    parents = {
        child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)
    }
    fields = {key for row in bank + journal for key in row}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, int)
        ):
            raise ExpressionLimit(
                "Positional row selection is not a general matching rule"
            )
        if not isinstance(node, ast.Constant):
            continue
        parent = parents.get(node)
        if (
            isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)
            and node.value != 0
        ):
            raise ExpressionLimit(
                "Case amounts and numeric thresholds must not be embedded in generated rules"
            )
        if isinstance(node.value, str) and node.value:
            field_access = (
                isinstance(parent, ast.Subscript)
                and parent.slice is node
                and node.value in fields
            )
            field_access = field_access or (
                isinstance(parent, ast.Call)
                and isinstance(parent.func, ast.Attribute)
                and parent.func.attr == "get"
                and parent.args
                and parent.args[0] is node
                and node.value in fields
            )
            result_key = (
                isinstance(parent, ast.Dict)
                and node in parent.keys
                and node.value in {"bank_ids", "journal_ids"}
            )
            punctuation_transform = (
                isinstance(parent, ast.Call)
                and isinstance(parent.func, ast.Attribute)
                and parent.func.attr == "replace"
                and not any(c.isalnum() for c in node.value)
            )
            if not (field_access or result_key or punctuation_transform):
                raise ExpressionLimit(
                    "Case-specific value literals are forbidden in generated rules"
                )
    identifiers = {r["transaction_id"] for r in bank + journal}
    if any(
        isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and n.value in identifiers
        for n in ast.walk(tree)
    ):
        raise ExpressionLimit("Transaction-specific rule literals are forbidden")
    result = _Interpreter(max_steps, max_items).visit(
        tree.body, {"bank": bank, "journal": journal}
    )
    if not isinstance(result, list) or not all(
        isinstance(item, dict) for item in result
    ):
        raise ExpressionLimit("Discovery must return a list of candidate objects")
    return result
