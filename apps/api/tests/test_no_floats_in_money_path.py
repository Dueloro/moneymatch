"""Static guard: no floating point in the money path. Integer cents only."""

from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

from moneymatch_api.services import money_math

pytestmark = pytest.mark.nodb

MONEY_MOVING_FUNCTIONS = ("rake_for", "split_pot", "split_weighted")

# Their outputs never touch a ledger row.
DISPLAY_ONLY_FUNCTIONS = ("pool_multiplier_estimate_bps", "h2h_multiplier_bps")


def _module_tree(module) -> ast.Module:
    return ast.parse(pathlib.Path(inspect.getfile(module)).read_text())


def _function_node(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name!r} not found — was it renamed or removed?")


@pytest.mark.parametrize("func_name", MONEY_MOVING_FUNCTIONS)
def test_no_float_literals(func_name: str):
    node = _function_node(_module_tree(money_math), func_name)
    offenders = [
        f"line {n.lineno}: {n.value!r}"
        for n in ast.walk(node)
        if isinstance(n, ast.Constant) and isinstance(n.value, float)
    ]
    assert not offenders, f"{func_name} contains float literals: {offenders}"


@pytest.mark.parametrize("func_name", MONEY_MOVING_FUNCTIONS)
def test_no_true_division(func_name: str):
    node = _function_node(_module_tree(money_math), func_name)
    offenders = [
        f"line {n.lineno}"
        for n in ast.walk(node)
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div)
    ]
    assert not offenders, (
        f"{func_name} uses true division (`/`) at {offenders}; use `//` so the "
        "result stays an integer number of cents"
    )


@pytest.mark.parametrize("func_name", MONEY_MOVING_FUNCTIONS)
def test_no_float_or_round_calls(func_name: str):
    node = _function_node(_module_tree(money_math), func_name)
    offenders = [
        f"line {n.lineno}: {n.func.id}()"
        for n in ast.walk(node)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id in {"float", "round"}
    ]
    assert not offenders, f"{func_name} calls {offenders}"


def test_money_moving_functions_return_integers():
    assert isinstance(money_math.rake_for(12_345, 1000), int)
    split = money_math.split_pot(12_345, 3, 1000)
    assert isinstance(split.rake_cents, int)
    assert all(isinstance(p, int) for p in split.payouts_cents)
    weighted = money_math.split_weighted(12_345, (50, 30, 20), 1000)
    assert isinstance(weighted.rake_cents, int)
    assert all(isinstance(p, int) for p in weighted.payouts_cents)


def test_the_exemption_list_is_honest():
    for name in DISPLAY_ONLY_FUNCTIONS:
        assert hasattr(money_math, name), (
            f"{name} is on the float exemption list but no longer exists"
        )


def test_every_public_money_function_is_classified():
    tree = _module_tree(money_math)
    defined = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    }
    classified = set(MONEY_MOVING_FUNCTIONS) | set(DISPLAY_ONLY_FUNCTIONS)
    unclassified = defined - classified
    assert not unclassified, (
        f"unclassified money_math functions: {sorted(unclassified)}. Add each to "
        "MONEY_MOVING_FUNCTIONS (integer-only) or DISPLAY_ONLY_FUNCTIONS "
        "(deliberately exempt)."
    )
