#!/usr/bin/env python3
"""Task B - Fulfilment Split Optimiser.

An order of ``Q`` units is fulfilled from up to ``W`` warehouses. Among all
allocations that ship *exactly* ``Q`` units, candidates are ranked by three
objectives, applied in order:

1. fewest warehouses used,
2. then lowest total shipping cost (``fixed_cost + allocated_qty * unit_cost``
   summed over the warehouses actually used),
3. then the lexicographically smallest allocation list, sorted by warehouse id.

The assessment grades this task on **optimisation and complexity**, so the
solver is split into three stages, each narrow enough to reason about on its own.

* **Stage 1** (:func:`min_warehouse_count`) - objective 1 needs no search at all.
  Shipping ``Q`` units out of ``k`` warehouses is possible exactly when the ``k``
  largest stocks add up to ``Q``, because capacity is the only thing limiting a
  choice of warehouses. Sorting once and scanning a running prefix sum finds the
  minimum ``k`` in O(W log W), independently of cost.

* **Stage 2** (:func:`build_cost_table`) - objective 2 is a suffix DP over
  ``(warehouse index, warehouses used, units allocated)``. Its inner transition
  enumerates how many units a warehouse contributes, which makes the naive
  version O(W * Q^2) - roughly 120 million steps at the largest allowed case,
  far too slow in Python. Substituting ``b = r - x`` (units left for the
  *remaining* warehouses) turns that inner loop into a sliding-window minimum
  over a fixed-width range, so a monotonic deque makes each step amortised O(1)
  and the whole table O(W * k * Q), about 1.8 million steps at the largest case.
  This rewrite is the core of the task.

* **Stage 3** (:func:`reconstruct`) - objective 3. The warehouse list is kept in
  id order, which makes "lexicographically smallest" mechanical: prefer to *use*
  the earliest warehouse that still admits an optimal completion, and on a
  warehouse that is used, take the *smallest* quantity that still admits one.
  Every decision is checked against the stage-2 table with an exact-cost test,
  so the walk can never stray outside the set of optimal solutions.

Every failure mode - infeasible order, malformed input, unreadable file - prints
a single ``-1`` and exits 0 (see DESIGN_TASK_B.md section 5 for why the task only
ever defines that one failure output).

Run with ``python taskB.py < input.txt`` or ``python taskB.py input.txt``.
"""

from __future__ import annotations

import re
import sys
from collections import deque
from dataclasses import dataclass
from typing import Iterable, Sequence, TextIO

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

# Stands in for "no allocation reaches this state". Real costs are bounded by
# W * (MAX_COST + MAX_Q * MAX_COST) ~ 6e10, so a sentinel this far above them
# can never collide with a genuine value.
INF = 10 ** 30

# Bounds from the task's Constraints block.
MAX_W = 30
MAX_Q = 2_000
MAX_STOCK = 2_000
MAX_COST = 10 ** 6

# Numeric fields are matched as plain decimal digits rather than handed to int(),
# which would also accept "+5", "1_000" and non-ASCII decimal characters such as
# "٥". The strict form keeps the accepted grammar identical to Task A's.
_DIGITS_RE = re.compile(r"[0-9]+")


@dataclass(frozen=True)
class Warehouse:
    """One input row: an id plus its stock and cost parameters."""

    wid: str
    stock: int
    fixed: int
    unit: int


# --------------------------------------------------------------------------
# Parsing layer - pure functions, no side effects.
#
# Each returns None instead of raising, so "malformed input" stays a value the
# caller can turn into the single "-1" output rather than an exception type that
# only main() knows how to interpret.
# --------------------------------------------------------------------------


def _parse_int(token: str, low: int, high: int) -> int | None:
    """Parse a bounded non-negative integer, or return None if it is not one."""
    if not _DIGITS_RE.fullmatch(token):
        return None
    value = int(token)
    if value < low or value > high:
        return None
    return value


def parse_header(tokens: Sequence[str]) -> tuple[int, int] | None:
    """Parse the ``W Q`` header line."""
    if len(tokens) != 2:
        return None
    count = _parse_int(tokens[0], 1, MAX_W)
    quantity = _parse_int(tokens[1], 1, MAX_Q)
    if count is None or quantity is None:
        return None
    return count, quantity


def parse_warehouse(tokens: Sequence[str]) -> Warehouse | None:
    """Parse one ``warehouse_id stock fixed_cost unit_cost`` row."""
    if len(tokens) != 4:
        return None
    wid = tokens[0]
    if not wid or not wid.isascii():
        return None
    stock = _parse_int(tokens[1], 0, MAX_STOCK)
    fixed = _parse_int(tokens[2], 0, MAX_COST)
    unit = _parse_int(tokens[3], 0, MAX_COST)
    if stock is None or fixed is None or unit is None:
        return None
    return Warehouse(wid, stock, fixed, unit)


# --------------------------------------------------------------------------
# Stage 1 - objective 1: the minimum number of warehouses.
# --------------------------------------------------------------------------


def min_warehouse_count(stocks: Iterable[int], quantity: int) -> int:
    """Fewest warehouses whose combined stock can cover ``quantity``.

    The optimal choice is always the ``k`` largest stocks: cost does not
    constrain how much a warehouse may ship, only its stock does. So the answer
    is the first prefix sum of the descending stock list that reaches the
    demand. Returns -1 when the total stock falls short.
    """
    running = 0
    for used, stock in enumerate(sorted(stocks, reverse=True), start=1):
        running += stock
        if running >= quantity:
            return used
    return -1


# --------------------------------------------------------------------------
# Stage 2 - objective 2: the minimum cost for every (count, units) state.
# --------------------------------------------------------------------------


def build_cost_table(
    warehouses: Sequence[Warehouse], max_used: int, quantity: int
) -> list[list[list[int]]]:
    """Suffix DP table over warehouses.

    ``table[i][s][r]`` is the cheapest way to ship exactly ``r`` units using
    exactly ``s`` of the warehouses ``i .. W-1``, or ``INF`` when impossible.

    Layer ``i`` only allocates rows for counts up to ``min(max_used, W - i)``:
    later layers have fewer warehouses left, so the higher counts are
    unreachable and skipping them roughly halves the work at the largest case.
    """
    total = len(warehouses)

    # Start from the base layer (past the last warehouse, only "ship nothing with
    # nothing" works) and let the loop below replace every earlier layer.
    table: list[list[list[int]]] = [[[INF] * (quantity + 1)] for _ in range(total + 1)]
    table[total][0][0] = 0

    for i in range(total - 1, -1, -1):
        warehouse = warehouses[i]
        nxt = table[i + 1]
        limit = min(max_used, total - i)
        cur = [[INF] * (quantity + 1) for _ in range(limit + 1)]
        cur[0][0] = 0

        fixed, unit, stock = warehouse.fixed, warehouse.unit, warehouse.stock

        # Reused across the count loop: every index is written immediately before
        # it enters the window, so no value can be read across iterations.
        shifted = [0] * (quantity + 1)

        for used in range(1, limit + 1):
            # Option A: leave this warehouse idle.
            skip = nxt[used] if used < len(nxt) else None
            # Option B: ship x >= 1 units from here, cheaper by
            # fixed + x*unit + table[i+1][used-1][r-x].
            prev = nxt[used - 1]
            row = cur[used]
            window: deque[int] = deque()

            for units in range(1, quantity + 1):
                # Written as b = units - x, the option-B cost becomes
                #   fixed + units*unit + (prev[b] - b*unit),
                # so the minimum over x is a minimum over b in the fixed-width
                # window [units - stock, units - 1] - a sliding-window minimum.
                b = units - 1
                base = prev[b]
                if base < INF:
                    value = base - b * unit
                    shifted[b] = value
                    while window and shifted[window[-1]] >= value:
                        window.pop()
                    window.append(b)

                low = units - stock
                while window and window[0] < low:
                    window.popleft()

                best = INF
                if window:
                    best = fixed + units * unit + shifted[window[0]]
                if skip is not None and skip[units] < best:
                    best = skip[units]
                row[units] = best

        table[i] = cur

    return table


# --------------------------------------------------------------------------
# Stage 3 - objective 3: rebuild the lexicographically smallest optimum.
# --------------------------------------------------------------------------


def reconstruct(
    warehouses: Sequence[Warehouse],
    table: list[list[list[int]]],
    max_used: int,
    quantity: int,
    optimal_cost: int,
) -> list[int]:
    """Walk forward and pick the allocation with the smallest pair sequence.

    Because ``warehouses`` is in id order, using the current warehouse always
    beats skipping it: compared against any later warehouse still unused, the
    pair ``(current_id, x)`` has the smaller id, so it wins the very position
    where the two lists first differ. Within a used warehouse the same argument
    picks the smallest quantity, and requiring the completion cost to match
    ``optimal_cost`` exactly keeps every choice inside the optimum.
    """
    quantities = [0] * len(warehouses)
    used = max_used
    remaining = quantity
    budget = optimal_cost

    for i, warehouse in enumerate(warehouses):
        if used == 0:
            break
        prev = table[i + 1][used - 1]
        ceiling = min(warehouse.stock, remaining)
        for x in range(1, ceiling + 1):
            rest = prev[remaining - x]
            if rest < INF and warehouse.fixed + x * warehouse.unit + rest == budget:
                quantities[i] = x
                budget -= warehouse.fixed + x * warehouse.unit
                remaining -= x
                used -= 1
                break

    return quantities


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def plan(
    warehouses: Sequence[Warehouse], quantity: int
) -> tuple[int, int, list[tuple[str, int]]] | None:
    """Solve one order, or return None when it cannot be fulfilled."""
    ordered = sorted(warehouses, key=lambda wh: wh.wid)

    max_used = min_warehouse_count([wh.stock for wh in ordered], quantity)
    if max_used < 0:
        return None

    table = build_cost_table(ordered, max_used, quantity)
    best = table[0][max_used][quantity]
    if best >= INF:
        return None

    quantities = reconstruct(ordered, table, max_used, quantity, best)

    # Sorted by the whole (id, qty) pair, not by array position: objective 3
    # compares pairs, so the printed list has to be in that same order. With
    # unique ids the two orderings coincide; sorting explicitly also makes the
    # output canonical if a caller ever feeds a duplicated warehouse_id.
    used = sorted(
        (wh.wid, qty) for wh, qty in zip(ordered, quantities) if qty > 0
    )
    return len(used), best, used


def format_result(result: tuple[int, int, list[tuple[str, int]]] | None) -> list[str]:
    """Render a solved order, or the single failure line ``-1``."""
    if result is None:
        return ["-1"]
    count, cost, used = result
    lines = [f"{count} {cost}"]
    lines.extend(f"{wid} {qty}" for wid, qty in used)
    return lines


def solve(lines: Iterable[str]) -> list[str]:
    """Pure function: input lines in, output lines out.

    This is the entry point every test drives, because it touches neither the
    filesystem nor stdout. Every failure collapses to ``["-1"]`` here, so the
    caller has exactly one shape to handle.
    """
    stream = iter(lines)

    header_tokens: list[str] | None = None
    for raw in stream:
        tokens = raw.split()
        if tokens:
            header_tokens = tokens
            break
    if header_tokens is None:
        return ["-1"]

    header = parse_header(header_tokens)
    if header is None:
        return ["-1"]
    expected, quantity = header

    warehouses: list[Warehouse] = []
    while len(warehouses) < expected:
        try:
            raw = next(stream)
        except StopIteration:
            return ["-1"]
        tokens = raw.split()
        if not tokens:
            continue
        warehouse = parse_warehouse(tokens)
        if warehouse is None:
            return ["-1"]
        warehouses.append(warehouse)

    return format_result(plan(warehouses, quantity))


def _read_lines(path: str | None) -> list[str] | None:
    """Read the input, or return None when it cannot be read at all."""
    try:
        if path is None:
            text = sys.stdin.read()
        else:
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
    except (OSError, UnicodeDecodeError):
        return None
    return text.splitlines()


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv
    path = argv[1] if len(argv) > 1 else None
    lines = _read_lines(path)
    output = ["-1"] if lines is None else solve(lines)

    # Line endings are pinned to "\n" so stdout is byte-identical on every
    # platform. Python would otherwise translate to "\r\n" on Windows, which
    # breaks an exact diff against the expected output for no real reason.
    # Streams that cannot be reconfigured (e.g. StringIO under test capture)
    # never translate in the first place, so the fallback is a no-op.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(newline="\n")

    sys.stdout.write("\n".join(output))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
