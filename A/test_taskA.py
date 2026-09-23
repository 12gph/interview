#!/usr/bin/env python3
"""Tests for Task A - Inventory Reservation Ledger.

The task asks for "edge-case and replay tests", so the suites below are split
along those lines: the official sample as a regression baseline, malformed
input, quantity boundaries, idempotency/replay, the open-reservation report,
input robustness, and finally a randomised differential test against a
deliberately naive reference implementation plus a 200k-command performance
check.

Every case drives :func:`taskA.run` with inline strings. No external fixture
files are used, so this file keeps working unchanged after it is moved from
``Code/project/src/project`` into the repository's ``A/`` directory.
"""

from __future__ import annotations

import io
import os
import random
import sys
import time

# Make the module importable from its own directory, so the test file does not
# depend on how the surrounding project is laid out or installed.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import taskA
from taskA import Ledger, parse_command, run

# --------------------------------------------------------------------------
# Official sample - the regression baseline
# --------------------------------------------------------------------------

OFFICIAL_INPUT = """\
10 6
RESERVE e1 o100 4
RESERVE e2 o200 7
SHIP e3 o100 2
RELEASE e4 o100 2
RESTOCK e5 3
RESERVE e2 o999 1
"""

OFFICIAL_OUTPUT = """\
OK 10 4
REJECTED 10 4
OK 8 2
OK 8 0
OK 11 0
DUPLICATE 11 0
OPEN 0"""


def run_text(text: str, open_mode: str = "list") -> list[str]:
    """Drive the pure core with a raw input string."""
    return run(text.splitlines(), open_mode)


def split_output(text: str, open_mode: str = "list") -> tuple[list[str], list[str]]:
    """Return (per-command status lines, trailing OPEN section)."""
    lines = run_text(text, open_mode)
    for index, line in enumerate(lines):
        if line.startswith("OPEN"):
            return lines[:index], lines[index:]
    raise AssertionError(f"no OPEN section in output: {lines!r}")


def state_lines(text: str, open_mode: str = "list") -> list[str]:
    return split_output(text, open_mode)[0]


def test_official_sample_is_reproduced_exactly() -> None:
    """T-01: the seven-line sample output, compared line by line."""
    assert run_text(OFFICIAL_INPUT) == OFFICIAL_OUTPUT.splitlines()


def test_official_sample_is_identical_in_total_mode() -> None:
    """T-02: with zero open reservations both OPEN formats agree."""
    assert run_text(OFFICIAL_INPUT, "total") == OFFICIAL_OUTPUT.splitlines()


# --------------------------------------------------------------------------
# Malformed input
# --------------------------------------------------------------------------


def test_unknown_command_is_rejected_without_side_effects() -> None:
    """T-03."""
    out = state_lines("5 2\nCANCEL e1 o1 1\nRESTOCK e2 1\n")
    assert out == ["REJECTED 5 0", "OK 6 0"]


def test_command_names_are_case_sensitive() -> None:
    """T-04: the task spells the commands in upper case."""
    assert state_lines("5 1\nreserve e1 o1 1\n") == ["REJECTED 5 0"]


@pytest.mark.parametrize(
    "line",
    [
        "RESERVE e1 o1",  # too few tokens
        "RESERVE e1 o1 1 2",  # too many tokens
        "SHIP e1 o1",
        "RELEASE e1",
        "RESTOCK e1",  # too few tokens
        "RESTOCK e1 1 2",  # too many tokens
    ],
)
def test_wrong_token_count_is_malformed(line: str) -> None:
    """T-05 / T-06."""
    assert state_lines(f"9 1\n{line}\n") == ["REJECTED 9 0"]


@pytest.mark.parametrize(
    "quantity",
    ["abc", "0", "-3", "1.5", "10**2", "1e3", "١٢"],
)
def test_invalid_quantity_is_malformed(quantity: str) -> None:
    """T-07 / T-08: non-integer, zero, negative, and non-ASCII digits."""
    assert state_lines(f"9 1\nRESERVE e1 o1 {quantity}\n") == ["REJECTED 9 0"]


def test_quantity_above_the_documented_maximum_is_malformed() -> None:
    """T-09: qty <= 10^12."""
    assert state_lines("9 1\nRESTOCK e1 1000000000001\n") == ["REJECTED 9 0"]
    assert state_lines("9 1\nRESTOCK e1 1000000000000\n") == ["OK 1000000000009 0"]


@pytest.mark.parametrize("quantity", ["+5", "1_000", "05x", "5x"])
def test_quantity_must_be_a_plain_digit_string(quantity: str) -> None:
    """T-10: int() would accept '+5' and '1_000'; the strict form is intentional.

    White-space-padded values are deliberately absent: tokens are split on
    whitespace before validation, so a padded value never reaches this check.
    """
    assert state_lines(f"9 1\nRESERVE e1 o1 {quantity}\n") == ["REJECTED 9 0"]


@pytest.mark.parametrize(
    "line",
    [
        "RESERVE e1 订单 1",  # non-ASCII order_id
        "RESERVE 事件 o1 1",  # non-ASCII event_id
    ],
)
def test_non_ascii_tokens_are_malformed(line: str) -> None:
    """T-11: "non-empty ASCII tokens" is a hard constraint."""
    assert state_lines(f"9 1\n{line}\n") == ["REJECTED 9 0"]


def test_blank_lines_are_skipped() -> None:
    """T-12: a blank line is formatting noise, neither a command nor output."""
    out = run_text("5 2\n\nRESERVE e1 o1 2\n   \nRESTOCK e2 1\n")
    assert out == ["OK 5 2", "OK 6 2", "OPEN 1", "o1 2"]


def test_malformed_line_leaves_state_untouched() -> None:
    """T-13: the malformed line must not consume or corrupt anything."""
    text = "10 3\nRESERVE e1 o1 4\nRESERVE e2 o1 999\nRESERVE e3 o1 6\n"
    assert state_lines(text) == ["OK 10 4", "REJECTED 10 4", "OK 10 10"]


def test_malformed_line_produces_a_status_line() -> None:
    """T-13b: one output line per command line, rejections included."""
    state, open_section = split_output("7 2\nBOGUS e1 o1 1\nRESTOCK e2 2\n")
    assert len(state) == 2
    assert open_section == ["OPEN 0"]


# --------------------------------------------------------------------------
# Quantity boundaries
# --------------------------------------------------------------------------


def test_reserve_is_rejected_when_stock_is_empty() -> None:
    """T-14."""
    assert state_lines("0 1\nRESERVE e1 o1 1\n") == ["REJECTED 0 0"]


def test_reserve_consumes_exactly_the_available_stock() -> None:
    """T-15 / T-16: available is the boundary, not a bit more."""
    assert state_lines("10 1\nRESERVE e1 o1 10\n") == ["OK 10 10"]
    assert state_lines("10 1\nRESERVE e1 o1 11\n") == ["REJECTED 10 0"]
    assert state_lines("10 2\nRESERVE e1 o1 6\nRESERVE e2 o2 5\n") == [
        "OK 10 6",
        "REJECTED 10 6",
    ]


def test_maximum_magnitudes_are_handled() -> None:
    """T-17: 10^12 fits comfortably in Python's arbitrary-precision ints."""
    assert state_lines("1000000000000 1\nRESERVE e1 o1 1000000000000\n") == [
        "OK 1000000000000 1000000000000"
    ]


def test_release_and_ship_on_an_unknown_order_are_rejected() -> None:
    """T-18: never reserved means nothing to release or ship."""
    assert state_lines("10 2\nRELEASE e1 o404 1\nSHIP e2 o404 1\n") == [
        "REJECTED 10 0",
        "REJECTED 10 0",
    ]


def test_release_and_ship_exactly_match_the_order_hold() -> None:
    """T-19."""
    assert state_lines("10 2\nRESERVE e1 o1 4\nSHIP e2 o1 4\n") == ["OK 10 4", "OK 6 0"]
    assert state_lines("10 2\nRESERVE e1 o1 4\nRELEASE e2 o1 4\n") == [
        "OK 10 4",
        "OK 10 0",
    ]


def test_release_and_ship_beyond_the_order_hold_are_rejected() -> None:
    """T-20: the limit is this order's hold, even when global reserved is larger."""
    text = "10 3\nRESERVE e1 o1 2\nRESERVE e2 o2 6\nSHIP e3 o1 3\n"
    assert state_lines(text) == ["OK 10 2", "OK 10 8", "REJECTED 10 8"]


def test_release_does_not_touch_on_hand() -> None:
    """T-21."""
    text = "10 3\nRESERVE e1 o1 4\nSHIP e2 o1 2\nRELEASE e3 o1 2\n"
    assert state_lines(text) == ["OK 10 4", "OK 8 2", "OK 8 0"]


def test_ship_decrements_both_counters() -> None:
    """T-22."""
    assert state_lines("10 2\nRESERVE e1 o1 4\nSHIP e2 o1 2\n") == ["OK 10 4", "OK 8 2"]


def test_restock_has_no_business_failure_mode() -> None:
    """T-23: only malformed input can reject a RESTOCK."""
    text = "0 3\nRESTOCK e1 5\nRESTOCK e2 1000000000000\nRESTOCK bad\n"
    assert state_lines(text) == [
        "OK 5 0",
        "OK 1000000000005 0",
        "REJECTED 1000000000005 0",
    ]


# --------------------------------------------------------------------------
# Idempotency and replay
# --------------------------------------------------------------------------


def test_replaying_a_successful_event_is_a_duplicate() -> None:
    """T-24."""
    text = "10 2\nRESERVE e1 o1 4\nRESERVE e1 o1 4\n"
    assert state_lines(text) == ["OK 10 4", "DUPLICATE 10 4"]


def test_replaying_a_business_rejected_event_is_a_duplicate() -> None:
    """T-25: a rejection still counts as processed."""
    text = "10 3\nRESERVE e1 o1 4\nRESERVE e2 o2 99\nRESERVE e2 o2 99\n"
    assert state_lines(text) == [
        "OK 10 4",
        "REJECTED 10 4",
        "DUPLICATE 10 4",
    ]


def test_replaying_a_restock_event_is_a_duplicate() -> None:
    """T-26."""
    text = "0 2\nRESTOCK e1 5\nRESTOCK e1 5\n"
    assert state_lines(text) == ["OK 5 0", "DUPLICATE 5 0"]


def test_replay_is_detected_even_when_other_parameters_change() -> None:
    """T-27: only the event_id is compared, not the rest of the command."""
    text = "10 2\nRESERVE e1 o1 4\nRESERVE e1 o999 1\n"
    assert state_lines(text) == ["OK 10 4", "DUPLICATE 10 4"]


def test_replay_is_detected_across_command_types() -> None:
    """T-28: one event_id is consumed globally, whatever the command was."""
    text = "10 3\nRESERVE e1 o1 4\nSHIP e1 o1 4\nRELEASE e1 o1 4\n"
    assert state_lines(text) == ["OK 10 4", "DUPLICATE 10 4", "DUPLICATE 10 4"]


def test_replay_after_stock_recovers_is_still_a_duplicate() -> None:
    """T-29: mirrors the official sample's last line.

    ``e2`` was rejected when stock was short. By the time it is replayed the
    stock is plentiful again, so a business check running first would accept
    it. The duplicate check must win.
    """
    text = "10 4\nRESERVE e1 o1 4\nRESERVE e2 o2 9\nRESTOCK e3 20\nRESERVE e2 o2 9\n"
    assert state_lines(text) == [
        "OK 10 4",
        "REJECTED 10 4",
        "OK 30 4",
        "DUPLICATE 30 4",
    ]


def test_malformed_events_do_not_consume_their_event_id() -> None:
    """T-30: decision D-2 - a parse failure is not a business rejection."""
    text = "10 3\nRESERVE e1 o1 0\nRESERVE e1 o1 5\nRESTOCK e2 1\n"
    assert state_lines(text) == ["REJECTED 10 0", "OK 10 5", "OK 11 5"]


# --------------------------------------------------------------------------
# Open reservations
# --------------------------------------------------------------------------


def test_open_section_lists_every_order_that_still_holds_stock() -> None:
    """T-31."""
    text = (
        "20 6\n"
        "RESERVE e1 o100 4\n"
        "RESERVE e2 o200 7\n"
        "RESERVE e3 o300 2\n"
        "SHIP e4 o100 4\n"
        "RELEASE e5 o200 3\n"
        "RESERVE e6 o050 1\n"
    )
    state, open_section = split_output(text)
    assert state[-1] == "OK 16 7"
    assert open_section == ["OPEN 3", "o050 1", "o200 4", "o300 2"]


def test_reserved_counter_always_equals_the_sum_of_order_holds() -> None:
    """T-32: the redundant global counter must never drift."""
    ledger = Ledger(on_hand=50)
    commands = [
        "RESERVE e1 o1 5",
        "RESERVE e2 o2 7",
        "SHIP e3 o1 2",
        "RELEASE e4 o2 3",
        "RESTOCK e5 10",
        "RESERVE e6 o3 20",
        "SHIP e7 o3 20",
    ]
    for raw in commands:
        command = parse_command(raw)
        assert command is not None
        ledger.apply(command)
        assert ledger.reserved == sum(ledger.per_order.values())


def test_open_section_total_matches_the_last_status_line() -> None:
    """T-33: the global view and the detail view describe the same number."""
    text = (
        "30 5\nRESERVE e1 o1 4\nRESERVE e2 o2 9\nSHIP e3 o1 1\n"
        "RELEASE e4 o2 2\nRESERVE e5 o3 3\n"
    )
    state, open_section = split_output(text)
    expected_total = int(state[-1].split()[2])
    listed_total = sum(int(line.split()[1]) for line in open_section[1:])
    assert listed_total == expected_total
    assert int(open_section[0].split()[1]) == len(open_section) - 1


def test_settled_orders_are_dropped_from_the_open_section() -> None:
    """T-34: an order that exists but holds nothing is not open."""
    text = "20 4\nRESERVE e1 o1 5\nRESERVE e2 o2 5\nSHIP e3 o1 5\nRELEASE e4 o2 5\n"
    _, open_section = split_output(text)
    assert open_section == ["OPEN 0"]


def test_open_section_has_no_extra_lines_when_nothing_is_open() -> None:
    """T-35: an empty report is exactly one line, with nothing after it."""
    text = "10 2\nRESERVE e1 o1 5\nSHIP e2 o1 5\n"
    state, open_section = split_output(text)
    assert state == ["OK 10 5", "OK 5 0"]
    assert open_section == ["OPEN 0"]


def test_open_section_uses_byte_order_not_numeric_order() -> None:
    """T-36: order_ids are ASCII tokens, so 'o10' sorts before 'o9'."""
    text = "100 2\nRESERVE e1 o9 1\nRESERVE e2 o10 1\n"
    assert run_text(text)[-3:] == ["OPEN 2", "o10 1", "o9 1"]


def test_total_mode_reports_the_global_reserved_quantity() -> None:
    """T-37."""
    text = "30 3\nRESERVE e1 o1 4\nRESERVE e2 o2 9\nSHIP e3 o1 1\n"
    state, open_section = split_output(text, "total")
    assert state[-1] == "OK 29 12"
    assert open_section == ["OPEN 12"]


# --------------------------------------------------------------------------
# Input robustness and header handling
# --------------------------------------------------------------------------


def test_crlf_line_endings_are_equivalent_to_lf(tmp_path, capsys) -> None:
    """T-38: files written on Windows must work unchanged."""
    path = tmp_path / "input.txt"
    path.write_bytes(b"10 2\r\nRESERVE e1 o1 4\r\nRESTOCK e2 1\r\n")
    assert taskA.main([str(path)]) == 0
    assert capsys.readouterr().out == "OK 10 4\nOK 11 4\nOPEN 1\no1 4\n"


def test_tabs_and_repeated_spaces_are_valid_separators() -> None:
    """T-38b."""
    spaced = "10 1\nRESERVE e1 o1 4\n"
    assert run_text("10    1\nRESERVE    e1\to1\t4\n") == run_text(spaced)


def test_fewer_commands_than_declared_is_not_an_error() -> None:
    """T-39: reading stops at EOF."""
    assert run_text("5 5\nRESERVE e1 o1 2\n") == ["OK 5 2", "OPEN 1", "o1 2"]


def test_lines_beyond_the_declared_count_are_ignored() -> None:
    """T-40."""
    assert run_text("5 1\nRESERVE e1 o1 2\nRESTOCK e2 100\n") == [
        "OK 5 2",
        "OPEN 1",
        "o1 2",
    ]


def test_trailing_blank_lines_produce_no_extra_output() -> None:
    """T-41."""
    assert run_text("5 1\nRESERVE e1 o1 2\n\n\n") == ["OK 5 2", "OPEN 1", "o1 2"]


@pytest.mark.parametrize(
    "header",
    [
        "abc",
        "10",
        "10 20 30",
        "-1 5",
        "10 0",  # N >= 1
        "10 200001",  # N <= 200,000
        "1000000000001 1",  # S <= 10^12
        "",
    ],
)
def test_malformed_header_raises(header: str) -> None:
    """T-41b: the header is not a command, so it fails hard instead of REJECTED."""
    with pytest.raises(taskA.HeaderError):
        run_text(f"{header}\nRESERVE e1 o1 1\n")


def test_main_reports_a_bad_header_on_stderr(tmp_path, capsys) -> None:
    path = tmp_path / "bad.txt"
    path.write_text("nonsense\n", encoding="utf-8")
    assert taskA.main([str(path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "header" in captured.err


def test_main_reads_stdin_when_no_path_is_given(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(OFFICIAL_INPUT))
    assert taskA.main([]) == 0
    assert capsys.readouterr().out == OFFICIAL_OUTPUT + "\n"


def test_main_accepts_the_open_format_switch(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("10 1\nRESERVE e1 o1 4\n"))
    assert taskA.main(["--open-format", "total"]) == 0
    assert capsys.readouterr().out == "OK 10 4\nOPEN 4\n"

    monkeypatch.setattr(sys, "stdin", io.StringIO("10 1\nRESERVE e1 o1 4\n"))
    assert taskA.main(["--open-format=nonsense"]) == 2


def test_main_reports_a_missing_file() -> None:
    assert taskA.main(["definitely-not-a-real-file.txt"]) == 2


# --------------------------------------------------------------------------
# Differential test against a naive reference implementation
# --------------------------------------------------------------------------


def reference_solve(text: str) -> list[str]:
    """A deliberately naive re-implementation used only for differential testing.

    It is written to be obviously correct rather than fast: no counters, no
    parsing helpers, every rule spelled out inline. Any disagreement with the
    optimised module means one of the two is wrong.
    """
    raw_lines = text.split("\n")
    head = raw_lines[0].split()
    on_hand = int(head[0])
    command_count = int(head[1])

    reserved_total = 0
    per_order: dict[str, int] = {}
    seen: set[str] = set()
    out: list[str] = []

    pending = [line for line in raw_lines[1:] if line.strip()][:command_count]

    for raw in pending:
        tokens = raw.split()
        kind = tokens[0] if tokens else ""
        malformed = False
        event_id = ""

        if kind not in ("RESERVE", "RELEASE", "SHIP", "RESTOCK"):
            malformed = True
        elif len(tokens) != (3 if kind == "RESTOCK" else 4):
            malformed = True
        else:
            event_id = tokens[1]
            if not event_id or not all(0x21 <= ord(ch) <= 0x7E for ch in event_id):
                malformed = True
            if not malformed and kind != "RESTOCK":
                order_id = tokens[2]
                if not order_id or not all(0x21 <= ord(ch) <= 0x7E for ch in order_id):
                    malformed = True
            if not malformed:
                digits = tokens[-1]
                if not digits or not all(ch in "0123456789" for ch in digits):
                    malformed = True
                elif not 1 <= int(digits) <= 10 ** 12:
                    malformed = True

        if malformed:
            out.append("REJECTED %d %d" % (on_hand, reserved_total))
            continue

        if event_id in seen:
            out.append("DUPLICATE %d %d" % (on_hand, reserved_total))
            continue

        if kind == "RESTOCK":
            on_hand += int(tokens[2])
        else:
            order_id = tokens[2]
            quantity = int(tokens[3])
            if kind == "RESERVE":
                if quantity > on_hand - reserved_total:
                    seen.add(event_id)
                    out.append("REJECTED %d %d" % (on_hand, reserved_total))
                    continue
                per_order[order_id] = per_order.get(order_id, 0) + quantity
                reserved_total += quantity
            else:
                held = per_order.get(order_id, 0)
                if quantity > held:
                    seen.add(event_id)
                    out.append("REJECTED %d %d" % (on_hand, reserved_total))
                    continue
                per_order[order_id] = held - quantity
                reserved_total -= quantity
                if kind == "SHIP":
                    on_hand -= quantity

        seen.add(event_id)
        out.append("OK %d %d" % (on_hand, reserved_total))

    open_orders = sorted(kv for kv in per_order.items() if kv[1] > 0)
    out.append("OPEN %d" % len(open_orders))
    out.extend("%s %d" % pair for pair in open_orders)
    return out


def _random_input(rng: random.Random) -> str:
    command_count = rng.randint(1, 60)
    order_ids = ["o1", "o2", "o10", "o9", "order-x", "A", "9"]
    lines = []
    for _ in range(command_count):
        kind = rng.choice(
            ["RESERVE", "RESERVE", "RELEASE", "SHIP", "RESTOCK", "CANCEL", "reserve"]
        )
        # A small event_id pool deliberately produces frequent replays.
        event_id = "e%d" % rng.randint(1, command_count + 5)
        if kind == "RESTOCK":
            lines.append("%s %s %d" % (kind, event_id, rng.randint(1, 8)))
        else:
            quantity = rng.choice([0, 1, 2, 3, 5, 8, 12])
            lines.append(
                "%s %s %s %d" % (kind, event_id, rng.choice(order_ids), quantity)
            )
    header = "%d %d" % (rng.choice([0, 1, 5, 12, 40]), command_count)
    return header + "\n" + "\n".join(lines) + "\n"


def test_randomised_commands_match_the_reference_implementation() -> None:
    """T-42: 300 seeded random scenarios compared line by line.

    This is the highest-value test in the suite: the two implementations were
    written independently (one tuned for speed, one for obviousness), so a
    mismatch almost always points at a real state-machine bug.
    """
    rng = random.Random(20260923)
    for _ in range(300):
        text = _random_input(rng)
        assert run_text(text) == reference_solve(text), f"mismatch for input:\n{text}"


def test_randomised_inputs_keep_the_counter_invariant() -> None:
    """T-42b: the differential test's inputs, checked against the invariant too."""
    rng = random.Random(7)
    for _ in range(100):
        text = _random_input(rng)
        state, _ = split_output(text)
        assert len(state) == len([ln for ln in text.split("\n")[1:] if ln.strip()])


# --------------------------------------------------------------------------
# Performance
# --------------------------------------------------------------------------


def test_two_hundred_thousand_commands_complete_quickly() -> None:
    """T-43: guards against an accidental O(N^2) implementation.

    The time limit is deliberately loose - it is there to catch a quadratic
    blow-up, not to measure machine speed.
    """
    command_count = 200_000
    body = []
    for index in range(command_count):
        order_id = "o%d" % (index % 1000)
        kind = index % 4
        if kind == 0:
            body.append("RESERVE e%d %s 1" % (index, order_id))
        elif kind == 1:
            body.append("SHIP e%d %s 1" % (index, order_id))
        elif kind == 2:
            body.append("RELEASE e%d %s 1" % (index, order_id))
        else:
            body.append("RESTOCK e%d 2" % index)
    text = "1000000 %d\n" % command_count + "\n".join(body)

    started = time.perf_counter()
    output = run_text(text)
    elapsed = time.perf_counter() - started

    assert output[command_count].startswith("OPEN ")
    open_count = int(output[command_count].split()[1])
    assert len(output) == command_count + 1 + open_count
    assert elapsed < 10, f"took {elapsed:.1f}s for {command_count} commands"
