#!/usr/bin/env python3
"""Tests for Task B - Fulfilment Split Optimiser.

Runnable from anywhere:

    python -m pytest test_taskB.py -q

The two cross-check tests (T-39 / T-40) are the most valuable ones in here. The
three-level objective is easy to get subtly wrong - above all the *direction* of
the tie-break - and no hand-written expectation catches that reliably. So the
file carries its own brute-force reference, written directly from the task
statement rather than from the solver's structure, and compares the two on every
legal allocation of a small case.
"""

from __future__ import annotations

import itertools
import os
import random
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import taskB  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE_INPUT = os.path.join(HERE, "sample_b_input.txt")
SAMPLE_OUTPUT = os.path.join(HERE, "sample_b_output.txt")

SAMPLE_LINES = ["3 7", "AU 5 8 2", "CN 7 20 1", "US 4 3 4"]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def solve_text(text: str) -> list[str]:
    """Run the pure solver over a block of text."""
    return taskB.solve(text.splitlines())


def solve_rows(header: str, rows: list[str], quantity: int = 0) -> list[str]:
    """Build an input block from a W/Q header and warehouse rows."""
    return solve_text("\n".join([header] + rows))


def brute_force(rows: list[tuple[str, int, int, int]], quantity: int):
    """Reference solver: enumerate every allocation, then rank the three goals.

    Deliberately naive and written from the problem statement, not from the
    implementation under test - that is what makes it a useful referee.
    """
    best = None
    ranges = [range(stock + 1) for _, stock, _, _ in rows]
    for allocation in itertools.product(*ranges):
        if sum(allocation) != quantity:
            continue
        used = sorted(
            (wid, x) for (wid, _, _, _), x in zip(rows, allocation) if x > 0
        )
        if not used:
            continue
        cost = sum(
            fixed + x * unit
            for (_, _, fixed, unit), x in zip(rows, allocation)
            if x > 0
        )
        key = (len(used), cost, used)
        if best is None or key < best:
            best = key
    return best


def render_brute(best) -> list[str]:
    if best is None:
        return ["-1"]
    count, cost, used = best
    return [f"{count} {cost}"] + [f"{wid} {x}" for wid, x in used]


def cli(args: list[str], stdin: str | None = None):
    """Run taskB.py as a real process and capture everything it emits."""
    return subprocess.run(
        [sys.executable, os.path.join(HERE, "taskB.py"), *args],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=HERE,
    )


# --------------------------------------------------------------------------
# 10.1 Official sample - regression baseline
# --------------------------------------------------------------------------


def test_sample_matches_expected_lines() -> None:
    """T-01."""
    assert taskB.solve(SAMPLE_LINES) == ["1 27", "CN 7"]


def test_sample_output_file_is_byte_identical() -> None:
    """T-02: the shipped sample output must match the shipped sample input."""
    process = cli([SAMPLE_INPUT])
    with open(SAMPLE_OUTPUT, "r", encoding="utf-8", newline="") as handle:
        expected = handle.read()
    assert process.stdout == expected
    assert process.returncode == 0


# --------------------------------------------------------------------------
# 10.2 Impossible orders (named by the task)
# --------------------------------------------------------------------------


def test_total_stock_below_quantity_is_impossible() -> None:
    """T-03."""
    assert solve_rows("3 20", ["A 5 1 1", "B 6 1 1", "C 4 1 1"]) == ["-1"]


def test_all_zero_stock_is_impossible() -> None:
    """T-04."""
    assert solve_rows("2 1", ["A 0 0 0", "B 0 0 0"]) == ["-1"]


def test_single_warehouse_short_of_quantity() -> None:
    """T-05."""
    assert solve_rows("1 10", ["A 9 0 1"]) == ["-1"]


def test_capacity_one_short_of_needing_two_warehouses() -> None:
    """T-06: just past the boundary - total stock exceeds Q but no single fits."""
    assert solve_rows("2 6", ["A 5 0 1", "B 2 0 1"]) == ["2 6", "A 4", "B 2"]


def test_capacity_exactly_equal_to_quantity_uses_everything() -> None:
    """T-07."""
    result = solve_rows("2 7", ["A 5 0 1", "B 2 0 1"])
    assert result == ["2 7", "A 5", "B 2"]
    assert sum(int(line.split()[1]) for line in result[1:]) == 7


# --------------------------------------------------------------------------
# 10.3 Zero-stock warehouses (named by the task)
# --------------------------------------------------------------------------


def test_zero_stock_warehouse_is_absent_from_the_result() -> None:
    """T-08."""
    assert solve_rows("2 5", ["A 5 0 1", "B 0 0 0"]) == ["1 5", "A 5"]


def test_zero_stock_warehouse_never_wins_a_tie() -> None:
    """T-09: 'A' has the smallest id but cannot ship anything."""
    assert solve_rows("2 3", ["A 0 0 0", "B 3 0 1"]) == ["1 3", "B 3"]


def test_zero_stock_with_free_cost_is_still_not_used() -> None:
    """T-10: a free warehouse cannot be 'used' with qty 0 - being used means qty >= 1."""
    assert solve_rows("2 3", ["A 0 0 0", "B 3 9 9"]) == ["1 36", "B 3"]


def test_subset_of_zero_stock_plus_one_stocked_warehouse() -> None:
    """T-11."""
    assert solve_rows("4 2", ["A 0 0 0", "B 0 1 1", "C 2 5 5", "D 0 0 0"]) == [
        "1 15",
        "C 2",
    ]


# --------------------------------------------------------------------------
# 10.4 Warehouse count outranks cost
# --------------------------------------------------------------------------


def test_single_warehouse_wins_even_when_two_are_cheaper() -> None:
    """T-12 (key case): objective 1 dominates objective 2.

    Only A can cover Q on its own, and it is expensive: 100 + 5*10 = 150.
    B and C cannot each cover Q, but together they can for 2*1 + 3*1 = 5.
    Objective 1 is applied first, so the costly single warehouse still wins.
    """
    assert solve_rows("3 5", ["A 5 100 10", "B 2 0 1", "C 3 0 1"]) == ["1 150", "A 5"]


def test_exactly_two_warehouses_are_used() -> None:
    """T-13."""
    result = solve_rows("2 5", ["A 3 0 1", "B 3 0 1"])
    assert result[0] == "2 5"
    assert len(result) - 1 == 2


def test_many_small_cheap_warehouses_still_lose_to_one_big_expensive_one() -> None:
    """T-14."""
    rows = [f"S{i} 2 0 1" for i in range(8)]
    assert solve_rows("9 5", ["BIG 5 500 0"] + rows) == ["1 500", "BIG 5"]


def test_count_is_driven_by_largest_stocks_not_by_cost() -> None:
    """T-15: the cheapest warehouse has stock 1 and cannot cover Q alone."""
    # A is free but ships only 1 unit. One warehouse could do it (B or C, stock
    # 5 each) but two would tie on cost - count still wins, so B vs C on id.
    assert solve_rows("3 5", ["A 1 0 0", "B 5 100 100", "C 5 100 100"]) == [
        "1 600",
        "B 5",
    ]


# --------------------------------------------------------------------------
# 10.5 Cost minimisation
# --------------------------------------------------------------------------


def test_lower_unit_cost_wins_within_a_fixed_count() -> None:
    """T-16."""
    assert solve_rows("2 10", ["A 10 0 5", "B 10 0 1"]) == ["1 10", "B 10"]


def test_fixed_cost_versus_unit_cost_split() -> None:
    """T-17: A has the higher unit cost, so it should ship as little as it can."""
    # A ships the minimum of 5 because B can only take 10 of the 15.
    assert solve_rows("3 15", ["A 10 0 10", "B 10 100 1", "C 0 0 0"]) == [
        "2 160",
        "A 5",
        "B 10",
    ]


def test_allocation_sums_to_exactly_quantity() -> None:
    """T-18."""
    result = solve_rows("3 7", ["A 10 0 1", "B 10 0 1", "C 10 0 1"])
    assert result[0] == "1 7"
    assert sum(int(line.split()[1]) for line in result[1:]) == 7


def test_three_warehouses_split_across_two() -> None:
    """T-19."""
    assert solve_rows("3 6", ["A 4 0 1", "B 4 0 1", "C 4 100 100"]) == [
        "2 6",
        "A 2",
        "B 4",
    ]


def test_all_costs_zero() -> None:
    """T-20."""
    assert solve_rows("2 5", ["A 3 0 0", "B 3 0 0"]) == ["2 0", "A 2", "B 3"]


# --------------------------------------------------------------------------
# 10.6 Cost ties -> lexicographic order (named by the task)
# --------------------------------------------------------------------------


def test_tie_between_warehouses_prefers_the_smaller_id() -> None:
    """T-21."""
    assert solve_rows("2 5", ["A 5 0 1", "B 5 0 1"]) == ["1 5", "A 5"]


def test_tie_on_the_same_id_prefers_the_smaller_quantity() -> None:
    """T-22 (the core case for the tie-break decision)."""
    # Every split of 6 across A and B costs the same, so the first pair decides:
    # (A,1) < (A,2) < ... < (A,5).
    assert solve_rows("2 6", ["A 5 0 1", "B 5 0 1"]) == ["2 6", "A 1", "B 5"]


def test_total_tie_on_zero_cost_picks_the_earliest_pair() -> None:
    """T-23: free shipping everywhere - only the tie-break picks a winner."""
    assert solve_rows("2 5", ["A 3 0 0", "B 3 0 0"]) == ["2 0", "A 2", "B 3"]


def test_two_digit_quantities_are_compared_numerically() -> None:
    """T-24: numeric tuples beat rendered strings ('A 10' < 'A 2' as text)."""
    # Both (A 2, B 10) and (A 10, B 2) cost 12. Numerically (A,2) is smaller.
    assert solve_rows("2 12", ["A 10 0 1", "B 10 0 1"]) == ["2 12", "A 2", "B 10"]


def test_cost_tie_does_not_add_a_warehouse() -> None:
    """T-25: one warehouse at cost 5 beats two warehouses at cost 5."""
    assert solve_rows("3 5", ["A 5 0 1", "B 2 0 1", "C 3 0 1"]) == ["1 5", "A 5"]


# --------------------------------------------------------------------------
# 10.7 Large quantities (named by the task)
# --------------------------------------------------------------------------


def test_quantity_at_the_upper_bound_from_one_warehouse() -> None:
    """T-26."""
    assert solve_rows("1 2000", ["A 2000 100 1"]) == ["1 2100", "A 2000"]


def test_costs_at_the_upper_bound_do_not_overflow() -> None:
    """T-27: 10^6 + 2000 * 10^6 = 2001 * 10^6."""
    assert solve_rows("1 2000", ["A 2000 1000000 1000000"]) == [
        "1 2001000000",
        "A 2000",
    ]


def test_worst_case_warehouse_count() -> None:
    """T-28: 30 warehouses of 67 units cover 2000 only with all 30 of them."""
    rows = [f"W{i:02d} 67 10 5" for i in range(30)]
    result = solve_rows("30 2000", rows)
    assert result[0] == "30 10300"
    assert len(result) - 1 == 30


def test_maximum_capacity_with_varied_costs() -> None:
    """T-29."""
    rows = [f"W{i:02d} 2000 {i} 1" for i in range(30)]
    # All can cover Q alone; the cheapest is W00 (fixed 0).
    assert solve_rows("30 2000", rows) == ["1 2000", "W00 2000"]


# --------------------------------------------------------------------------
# 10.8 Input contract and the single failure exit
# --------------------------------------------------------------------------


def test_crlf_and_lf_are_equivalent() -> None:
    """T-30."""
    lf = taskB.solve(SAMPLE_LINES)
    crlf = taskB.solve([line + "\r" for line in SAMPLE_LINES])
    assert lf == crlf == ["1 27", "CN 7"]


def test_tabs_and_repeated_spaces_are_separators() -> None:
    """T-31."""
    assert solve_text("3\t7\nAU\t5\t8\t2\nCN  7  20  1\nUS 4 3 4") == ["1 27", "CN 7"]


def test_blank_lines_are_skipped_and_do_not_consume_the_warehouse_budget() -> None:
    """T-32."""
    assert solve_text("3 7\n\nAU 5 8 2\n   \nCN 7 20 1\n\nUS 4 3 4\n\n") == [
        "1 27",
        "CN 7",
    ]


def test_rows_beyond_w_are_ignored() -> None:
    """T-33: the trailing row would otherwise make CHEAP look better."""
    assert solve_text("1 3\nA 3 0 1\nB 100 0 0") == ["1 3", "A 3"]


def test_fewer_rows_than_w_yields_the_failure_output() -> None:
    """T-34."""
    assert solve_text("3 7\nAU 5 8 2\nCN 7 20 1") == ["-1"]


@pytest.mark.parametrize(
    "header",
    ["3", "7", "3 7 1", "0 7", "31 7", "3 0", "3 2001", "three 7", "3 seven", "  ", "3 +7"],
)
def test_invalid_header_yields_the_failure_output(header: str) -> None:
    """T-35."""
    assert solve_text(f"{header}\nA 5 0 1") == ["-1"]


@pytest.mark.parametrize(
    "row",
    [
        "A 5 0",  # too few fields
        "A 5 0 1 9",  # too many fields
        "A -1 0 1",  # negative stock
        "A 2001 0 1",  # stock above the bound
        "A 5 1000001 1",  # fixed cost above the bound
        "A 5 0 1000001",  # unit cost above the bound
        "A +5 0 1",  # int() would accept this; the strict grammar must not
        "A 1_0 0 1",  # ditto for underscores
        "A ٥ 0 1",  # Arabic-Indic digit, also accepted by int()
        "A 1.0 0 1",  # not an integer
    ],
)
def test_invalid_warehouse_row_yields_the_failure_output(row: str) -> None:
    """T-36."""
    assert solve_text(f"2 5\n{row}\nB 5 0 1") == ["-1"]


def test_zero_stock_is_valid_unlike_a_malformed_row() -> None:
    """T-37: stock = 0 is legal input and must not be confused with an error."""
    assert solve_rows("2 3", ["A 0 0 0", "B 3 0 1"]) == ["1 3", "B 3"]


def test_cli_reads_stdin_and_a_file() -> None:
    """T-38 (stdin and file path)."""
    stdin_run = cli([], stdin="\n".join(SAMPLE_LINES) + "\n")
    file_run = cli([SAMPLE_INPUT])
    assert stdin_run.stdout == file_run.stdout == "1 27\nCN 7\n"
    assert stdin_run.returncode == file_run.returncode == 0


def test_cli_with_a_missing_file_prints_the_failure_output() -> None:
    """T-38 (missing file)."""
    process = cli([os.path.join(HERE, "does_not_exist_12345.txt")])
    assert process.stdout == "-1\n"
    assert process.returncode == 0


def test_empty_input_and_header_only_input() -> None:
    """T-38b."""
    assert solve_text("") == ["-1"]
    assert solve_text("3 7") == ["-1"]
    assert solve_text("\n   \n") == ["-1"]


@pytest.mark.parametrize(
    "text",
    [
        "",  # empty
        "3 7",  # header only
        "3 7\nA 5 0 1",  # too few rows
        "9 7\nA 5 0 1",  # W out of range
        "3 7\nA +5 0 1\nB 5 0 1\nC 5 0 1",  # malformed row
        "2 100\nA 5 0 1\nB 5 0 1",  # infeasible
    ],
)
def test_every_failure_uses_the_single_exit_contract(text: str) -> None:
    """T-38c: stdout is the whole contract - no stderr, exit code stays 0."""
    process = cli([], stdin=text)
    assert process.stdout == "-1\n"
    assert process.stderr == ""
    assert process.returncode == 0


# --------------------------------------------------------------------------
# 10.9 Cross-check against brute force (the main correctness guard)
# --------------------------------------------------------------------------


def test_exhaustive_small_cases_match_brute_force() -> None:
    """T-39: every legal allocation of a small case, ranked by brute force."""
    checked = 0
    ids = ["A", "B", "C"]
    for stocks in itertools.product(range(3), repeat=3):
        for units in itertools.product(range(2), repeat=3):
            rows = [(wid, s, 0, u) for wid, s, u in zip(ids, stocks, units)]
            for quantity in range(1, 6):
                text = [f"3 {quantity}"] + [
                    f"{wid} {s} {f} {u}" for wid, s, f, u in rows
                ]
                got = taskB.solve(text)
                want = render_brute(brute_force(rows, quantity))
                assert got == want, (text, got, want)
                checked += 1
    assert checked == 3 ** 3 * 2 ** 3 * 5


def test_random_small_cases_match_brute_force() -> None:
    """T-40."""
    rng = random.Random(20260924)
    ids = ["A", "B", "C", "D"]
    for _ in range(900):
        width = rng.randint(1, 4)
        rows = [
            (wid, rng.randint(0, 4), rng.randint(0, 5), rng.randint(0, 4))
            for wid in ids[:width]
        ]
        quantity = rng.randint(1, 8)
        text = [f"{width} {quantity}"] + [
            f"{wid} {s} {f} {u}" for wid, s, f, u in rows
        ]
        got = taskB.solve(text)
        want = render_brute(brute_force(rows, quantity))
        assert got == want, (text, got, want)


# --------------------------------------------------------------------------
# 10.10 Performance
# --------------------------------------------------------------------------


def test_worst_case_finishes_within_a_loose_budget() -> None:
    """T-41.

    The limit is deliberately generous. The goal is to catch an accidental
    quadratic (or worse) transition, not to assert a machine-specific timing -
    a tight bound would flake on a loaded CI box.
    """
    rows = [f"W{i:02d} 67 10 5" for i in range(30)]
    text = "\n".join(["30 2000"] + rows)

    started = time.perf_counter()
    result = taskB.solve(text.splitlines())
    elapsed = time.perf_counter() - started

    assert result[0] == "30 10300"
    assert elapsed < 10.0, f"worst case took {elapsed:.2f}s"
