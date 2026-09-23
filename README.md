# Take-home Test

## Repository layout

```
/A     Python solution + tests
/B     Python solution + tests
/C     Written answers (README.md or answers.md)
/app   FastAPI backend + React/TypeScript frontend
README.md
```

> The block above is **what is committed to the repository**. The development-time `Code/` (working
> copy), `DEVELOPMENT_SPEC.md` and `DESIGN_*.md` stay in the author's local working directory and are
> not committed.

| Path   | Contents                                                                    |
| ------ | --------------------------------------------------------------------------- |
| `A/`   | Python solution + automated tests                                           |
| `B/`   | Python solution + automated tests                                           |
| `C/`   | Written answers (`C/README.md` or `C/answers.md`)                           |
| `app/` | `app/backend` — FastAPI service; `app/frontend` — React + TypeScript client |

## Installation

### Prerequisites

- Python 3.11+ — required by `A/`, `B/` and `app/backend`
- Node.js 20.19+ or 22.12+ — required by `app/frontend` only (the engine range Vite 8 declares)
- [uv](https://docs.astral.sh/uv/) — **optional**. With it, one command installs the backend
  dependencies; without it, use the `venv` + `pip` fallback below

### Install steps

Backend and frontend are independent of each other; run each in its own directory.

```bash
# Backend — pick one

# Option 1: uv (recommended; reproduces the exact versions verified during development, via uv.lock)
cd app/backend && uv sync

# Option 2: without uv
cd app/backend
python -m venv .venv
.venv/bin/pip install -e . --group dev    # Windows: .venv\Scripts\pip install -e . --group dev
```

> `--group dev` installs the test stack (`pytest` / `httpx` / `pytest-asyncio`), **which is what
> `uv sync` installs by default** — both paths should give the same environment, otherwise "the
> pip-installed copy cannot run the tests" only surfaces on the very last step. If you only run the
> service and never the tests, dropping `--group dev` is enough; pip < 25.1 does not understand
> `--group`, so use
> `.venv/bin/pip install -e . && .venv/bin/pip install pytest httpx pytest-asyncio` instead.

```bash
# Frontend
cd app/frontend && npm install
```

> `A/` and `B/` are dependency-free programs that use only the standard library; but **running
> their tests needs pytest**: `python -m pip install pytest` (install it into any usable Python
> environment — the two directories share one copy).

You can also hand all of this to the one-command launcher: it checks the dependencies first, reports
whichever half is missing, and installs them when given `--install`:

```bash
cd app && python dev.py --install
```

> **PyPI mirror**: `app/backend/pyproject.toml` sets the Alibaba Cloud mirror as the default index
> (the development machine's network needs it). If you can reach PyPI directly, there is no need to
> edit the file — just override the index: `uv sync --default-index https://pypi.org/simple`, or set
> the `UV_DEFAULT_INDEX` environment variable.

## Commands

```bash
# A — inventory reservation ledger
cd A && python -m pytest -q

# B — fulfilment split optimiser
cd B && python -m pytest -q

# app backend — tests
cd app/backend && uv run pytest -q          # without uv: .venv/bin/python -m pytest -q

# app backend — service (http://localhost:8000, API docs at /docs)
cd app/backend && uv run uvicorn backend.main:app --reload --port 8000

# app frontend — dev server (http://localhost:5173)
cd app/frontend && npm run dev

# app — one command to bring up both
cd app && python dev.py
```

## Task A — inventory reservation ledger

`A/taskA.py` is a deterministic command processor for a single SKU. It reads an `S N` header and the
N commands that follow (`RESERVE` / `RELEASE` / `SHIP` / `RESTOCK`), prints one line per command —
`<status> <on_hand> <reserved>` — and finally prints the list of orders still holding stock. No
third-party dependencies.

```bash
cd A
python taskA.py sample_input.txt                    # or: python taskA.py < sample_input.txt
python taskA.py sample_input.txt --open-format total
```

### Tests

`A/test_taskA.py` is exactly the **edge-case and replay tests** the brief calls for: the first kind
targets the boundaries of the input, the second targets the same `event_id` delivered twice. Every
case calls `run()` directly (a pure function) and depends on no external fixture file, so it runs
unchanged after being moved from the development directory into `A/`.

```bash
cd A
python -m pytest -q
```

**48 test functions, 70 cases after parametrisation**:

| Group                            | Functions / cases | Coverage                                                                                                                     |
| -------------------------------- | ----------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Official sample (regression base) | 2 / 2             | Reproduces the sample output line by line; both closing formats (`list` and `total`) agree on the sample                        |
| Malformed input                  | 10 / 25           | Unknown command, command-name case, too few/many fields, invalid quantity, out-of-range quantity, non-ASCII token, blank line; asserts zero state change |
| Quantity boundaries              | 9 / 9             | `S = 0`, exactly exhausting available stock, exactly exhausting an order's reservation, one unit over, `10^12` magnitudes, `RELEASE`/`SHIP` on an unknown order |
| **Idempotency & replay**         | 7 / 7             | Successful / business-rejected / `RESTOCK` event replays all return `DUPLICATE`; changing parameters does not affect the verdict; works across command types |
| Open reservations                | 7 / 7             | List completeness, settled orders dropped, byte order rather than numeric order, closing total agrees with the last status line  |
| Input robustness                 | 10 / 17           | CRLF, tabs and repeated spaces, fewer/more lines than N, trailing blank line, 8 kinds of malformed header, both stdin and file entry points |
| Differential testing & performance | 3 / 3           | Line-by-line comparison against an independently written naive reference; counter invariants; wall time for 200,000 commands     |

A few notes:

- The **quantity boundaries** group is all about "off by one": equal to the available stock /
  order reservation succeeds, one unit more is rejected immediately. It also covers the semantics
  that are easy to get backwards — `on_hand` untouched by `RELEASE`, `SHIP` decrementing both
  `on_hand` and the global `reserved`, and `RESTOCK` having no business failure state.
- The point of the **idempotency & replay** group is one counter-intuitive case: replay an event
  that was rejected at the time while the stock is now sufficient — the correct answer is still
  `DUPLICATE`, not `OK`. That case nails down "deduplication must happen before business
  evaluation".
- The reference implementation in **differential testing & performance** aims only at semantic
  correctness, not speed, and was written independently of the main implementation, so it is there
  to catch a state machine that drifted. The performance case uses a loose upper bound: the goal is
  to catch an accidental O(N²), not to assert exact timings, which would produce false alarms on a
  noisy machine.

### Complexity analysis

**Time — the main loop is O(N).**

| Stage             | Implementation                                        | Cost per command |
| ----------------- | ----------------------------------------------------- | ---------------- |
| Parse             | `parse_command`: `split()` plus 2–3 regex `fullmatch` | amortised O(1)   |
| Idempotency check | `event_id in processed` (a `set`)                     | amortised O(1)   |
| Business verdict  | `_is_allowed`: integer comparisons and `dict.get`     | amortised O(1)   |
| State change      | `_commit`: writes to a `dict` and an `int`            | amortised O(1)   |
| Output            | `list.append`, written out in one go at the end       | amortised O(1)   |

Every stage is constant work, so processing N commands is **O(N)**. There is no `sum()`, no
`sorted()` and no scan over orders inside the loop: recomputing the global `reserved` total from
`per_order` on every command would degrade a single command to O(number of orders) and break that
bound — which is exactly why `reserved` is kept as a redundant field and written in only one place
(`Ledger._commit`).

**Time — the closing section is O(K log K).**

`format_open` first filters out the orders whose reservation is positive, then sorts by `order_id`.
Filtering is O(K), sorting is O(K log K), where K is the number of orders still holding stock,
K ≤ N. `order_id` is an ASCII token, so this is a **byte-wise comparison**: `"o10"` sorts before
`"o9"`.

**Total: O(N + K log K)** — worst case O(N log N) when K grows with N; in practice close to O(N),
because K counts **open orders**, not commands.

**Space: O(N).** `processed` holds at most N event ids, `per_order` at most K entries, and `output`
has N + 1 + K lines. This part cannot be compressed — to print N lines, the program must first hold
those N lines.

**Measured.** The input is generated by a fixed script: a five-command cycle
`SHIP / RESERVE / RESERVE / RESERVE / RESTOCK`, one unique `event_id` per command, `order_id =
o(i//10)`, initial `S = 10^9`. The figures below are the best of three runs of `run()` (parse +
process + format, excluding file reads and stdout writes), on Python 3.12.14.

| N       | Total time | Closing section | K      | Status breakdown             |
| ------- | ---------- | --------------- | ------ | ---------------------------- |
| 10,000  | 0.032 s    | 0.0003 s        | 1,000  | OK 9,000 / REJECTED 1,000    |
| 50,000  | 0.169 s    | 0.0046 s        | 5,000  | OK 45,000 / REJECTED 5,000   |
| 200,000 | 0.700 s    | 0.0362 s        | 20,000 | OK 180,000 / REJECTED 20,000 |

Time grows linearly with N — a fivefold input takes about five times as long. At N = 200,000 the
closing section is roughly 5% of the total, so the loop, not the sort, is what would be worth
optimising. The closing-section column is a residual (the difference between the `list` and `total`
output formats); it is there to indicate magnitude only, and no growth curve is claimed from it.

**Two premises this analysis rests on.**

1. "Amortised O(1) per command" assumes bounded token length. `qty` is indeed bounded (≤ 10^12),
   but the spec only says `event_id` and `order_id` are non-empty ASCII tokens — it gives **no
   upper bound**. The more rigorous statement is therefore **O(total input bytes)**, where N is the
   number of commands, not the number of bytes. The program has no defence against an
   over-long token.
2. `set` and `dict` lookup is amortised O(1) but O(n) worst case under hash collisions. The input
   here is a trusted batch file, not an adversarial data stream, so no collision hardening was
   added.

**Trade-off: the sort stays.** As long as the output must be ordered, the closing section cannot be
cheaper than Ω(K log K). Switching to counting sort or radix sort would just make a readable
function several times longer in exchange for a different asymptotic symbol, and K is normally much
smaller than N. The brief explicitly prefers clarity over unnecessary complexity, so `sorted()`
stays and the cost is recorded here.

## Task B — fulfilment split optimiser

`B/taskB.py` reads a `W Q` header followed by W warehouse lines
(`warehouse_id stock fixed_cost unit_cost`) and, among all legal plans that allocate **exactly** Q
units, picks the optimum under a three-level objective:

1. fewest **warehouses used**;
2. then lowest **total shipping cost** — each used warehouse contributes
   `fixed_cost + allocated_qty × unit_cost`;
3. then, in the allocation list sorted by `warehouse_id`, the **lexicographically smallest** one.

No third-party dependencies.

### Input and output contract

|                        | Format                                                                                                                   |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| First input line       | `W Q` — `1 ≤ W ≤ 30`, `1 ≤ Q ≤ 2000`                                                                                     |
| Remaining input        | `W` lines of `warehouse_id stock fixed_cost unit_cost` — `0 ≤ stock ≤ 2000`, `0 ≤ fixed_cost, unit_cost ≤ 10^6`          |
| Output (feasible)      | First line `<warehouse count> <total cost>`; then one line per used warehouse, `<warehouse_id> <allocated_qty>`, ascending by `(warehouse_id, allocated_qty)` |
| Output (no plan exists) | A single line `-1`, exit code always 0, **stderr empty**                                                                |

"Cannot produce a plan" covers stock summing to less than Q, invalid input, too few lines, and a
missing file — the original wording defines `-1` as the only failure exit, and the reasons for and
costs of reusing it for every failure are in "Assumptions" and "Known limitations".

```bash
cd B
python taskB.py sample_b_input.txt                  # read from a file
python taskB.py < sample_b_input.txt                # read from stdin
```

> **With no argument it reads stdin** (consistent with `A/taskA.py`). Running `python taskB.py`
> directly therefore waits for standard input and produces no output until you end it with Ctrl+D;
> when running from an IDE, point the run configuration's input at `sample_b_input.txt`.

### Sample

`sample_b_input.txt`:

```
3 7
AU 5 8 2
CN 7 20 1
US 4 3 4
```

Expected output, `sample_b_output.txt`:

```
1 27
CN 7
```

```bash
cd B
python taskB.py sample_b_input.txt | diff - sample_b_output.txt && echo OK
```

AU holds 5 and US holds 4, neither enough for 7 units; only CN can, so the minimum warehouse count
is 1 and the cost is `20 + 7×1 = 27`. Note that this sample **cannot verify "warehouse count before
cost"** — CN is the only single-warehouse candidate, and the plan with fewer warehouses also happens
to be cheaper, so both objectives point at the same answer. What guards that rule is the
"warehouse count before cost" group in the tests.

### Tests

`B/test_taskB.py` covers the four categories the brief names — **unfulfillable orders, zero-stock
warehouses, cost ties, large quantities** — plus official-sample regression, the input contract and
performance. Every case calls `solve()` directly (a pure function) and depends on no external
fixture file.

```bash
cd B
python -m pytest -q
```

**44 test functions, 68 cases after parametrisation**:

| Group                             | Functions / cases | Coverage                                                                                              |
| --------------------------------- | ----------------- | ----------------------------------------------------------------------------------------------------- |
| Official sample (regression base)  | 2 / 2             | Reproduces the sample line by line; CLI output byte-equal to `sample_b_output.txt`                      |
| Unfulfillable orders              | 5 / 5             | Total stock short, all-zero stock, single warehouse short, exactly equal, and both sides of the `-1` boundary |
| Zero-stock warehouses             | 4 / 4             | Zero-stock entries never appear in the result; "free" does not make them usable; the lowest-id zero-stock entry does not take part in ties |
| Warehouse count before cost       | 4 / 4             | **A single, more expensive warehouse still wins**; `k* = 2`; several cheap small warehouses lose to one big one; `k*` is decided by stock, not by cost |
| Cost minimisation                 | 5 / 5             | Unit-price choice, fixed cost vs unit price, exact allocation (asserts `Σ qty == Q`), cross-warehouse combinations, all-zero cost |
| Cost ties → lexicographic order   | 5 / 5             | Prefers the smaller id, then the smaller quantity at the same id, an all-zero-cost extreme tie, **multi-digit ids compared numerically**, and ties that do not increase the warehouse count |
| Large quantities                  | 4 / 4             | `Q = 2000` upper bound, cost upper bound (`10^6`) without overflow, the `W = 30` / `k* = 30` worst case |
| Input contract & failure exit     | 12 / 36           | CRLF, tabs, blank lines skipped, extra lines ignored, 11 kinds of malformed header, 10 kinds of malformed warehouse line, empty input, missing file |
| Differential testing & performance | 3 / 3            | 1,080 exhaustive cross-checks; 900 random cross-checks; a loose time limit on the worst case          |

Three notes:

- **Warehouse count before cost** is the core group. The test builds a case where only warehouse A
  can cover the demand on its own (cost 150), while B and C together cover it for 5 — the correct
  answer is still `1 150`. That case is what guards the **order of application** of the three
  objectives.
- The **cross-check** reference implementation lives in the test file and was **written
  independently from the problem statement** (enumerate every allocation → sort by the three-level
  objective); it does not reuse the main implementation's structure. The direction of the
  comparisons in the three-level objective is the easiest thing to get backwards, and brute force
  is the best judge. During development I also ran full enumeration for `W=2` and `W=3`
  (16,686 cases in total) with zero deviation.
- The **performance case** uses a loose limit (10 seconds); the goal is to catch an accidental
  quadratic implementation rather than to assert exact timings, which would produce false alarms on
  a noisy machine.

### Complexity analysis

The algorithm runs in three stages, each solving one objective.

| Stage                        | Approach                                                        | Time                    | Space             |
| ---------------------------- | --------------------------------------------------------------- | ----------------------- | ----------------- |
| 1 — fewest warehouses        | Sort stock descending + one prefix-sum pass                     | O(W log W)              | O(W)              |
| 2 — lowest cost              | Suffix DP, transitions via a monotonic queue for a **sliding-window minimum** | **O(W · k* · Q)**       | **O(W · k* · Q)** |
| 3 — tie reconstruction       | Forward greedy in ascending id order, using the suffix table for an **exact-cost** test | O(W · Q)                | O(1) extra        |
| **Total**                    |                                                                 | **O(W log W + W·k*·Q)** | **O(W·k*·Q)**     |


**Why stage 1 needs no search.** Covering demand with k warehouses is equivalent to "the sum of the
k largest stocks ≥ Q" — because stock is the only thing limiting how much a warehouse ships; cost
plays no part. One sort and one prefix-sum pass give the minimum k, independently of cost.

**The optimisation in stage 2 is the heart of this task.** The state is `cost[i][s][r]`: the minimum
cost using only the warehouses after the i-th, exactly s of them, allocating exactly r units. The
transition enumerates how much this warehouse ships:

```
cost[i][s][r] = min( cost[i+1][s][r],  fixed + x·unit + cost[i+1][s-1][r-x] )   x ∈ [1, min(stock, r)]
```

In the naive form that inner enumeration is O(Q), making the whole table **O(W·Q²)** — about **120
million** inner operations on the largest case, which Python cannot get through. Substituting
`x` with `b = r − x` (the units left for the following warehouses):

```
fixed + r·unit + ( cost[i+1][s-1][b] − b·unit ),   b ∈ [r − stock, r − 1]
```

The bracketed term depends only on `b`, and the window is **fixed-length and moves one position
right with r** — a sliding-window minimum. A single monotonic queue makes each step amortised O(1),
bringing the table down to **O(W · k* · Q)**, about **1.8 million** operations on the largest case.

**The direction of the greedy in stage 3.** The warehouse list is kept in ascending id order, so
"lexicographically smallest" reduces to two mechanical rules: **take the current warehouse if you
can** (taking it puts `(current id, x)` at that position, skipping it puts a later id there, and the
former is smaller); and **at a warehouse you do take, take the smallest feasible quantity** (for the
same id, the smaller quantity comes first). Every step is validated with
`cost[i+1][s-1][r-x] == budget` (equality, not ≤) to stay on a path that is still inside the optimal
set.

**Why a DP is required rather than a greedy.** "Fill up in ascending unit cost" does not work here:
every warehouse that is switched on carries a one-off fixed cost, so the exchange argument fails.
`2 10` / `A 10 0 5` / `B 10 100 1` is a counter-example — B has the lower unit price (1 against 5),
but with the fixed cost it comes to `100 + 10×1 = 110`, while A costs only `0 + 10×5 = 50`, and the
correct answer is `1 50` with `A 10`. The fixed charge also makes this problem NP-hard at general
scale (the transportation problem with fixed charges), so what buys an **exact optimum** here is the
size bound `W ≤ 30`, `Q ≤ 2000` making a pseudo-polynomial DP fast enough — not any gentleness in
the problem's structure. The brief explicitly forbids external solvers, and none is needed here.

**The space is O(W·k*·Q), not O(k·Q).** Stage 3 reconstructs **forward** in id order and needs
random access to every suffix layer, so every layer has to be kept. That is the price paid for the
third objective — reconstructing in reverse would cut memory to O(k·Q), but then the
lexicographically smallest solution could not be recovered.

**Measured.** On Python 3.12.14, timing `solve()` (parse + solve + format, excluding file reads and
stdout writes). Peak memory measured with `tracemalloc`.

| Case                                              | Time        | Result         | Peak memory |
| ------------------------------------------------- | ----------- | -------------- | ----------- |
| `W=30, Q=2000, stock=67` → `k* = 30` (worst count) | **0.234 s** | `30 10300`     | 17.4 MiB    |
| `W=30, Q=2000, stock=100` → `k* = 20`             | 0.228 s     | `20 26000`     | —           |
| `W=30, Q=2000, stock=2000` → `k* = 1`             | 0.017 s     | `1 19000`      | —           |
| Cost at the upper bound (`fixed = unit = 10^6`)    | 0.018 s     | `1 2001000000` | —           |

The worst case (`k* = W = 30`) finishes in 0.234 seconds. On that same case the naive transition is
120 million inner operations and this implementation is 1.8 million — that is the whole gap.

## Task C — Xero integration review

The deliverable is **`C/README.md`** — a purely written answer to the six questions C1–C6, with no
executable code. The brief asks for *"Answer concisely in Markdown"* on this part, so there are no
runnable tests here — automated tests are a global item in the submission instructions and do not
apply to a written answer.

### Versions this answer is based on (`C/README.md`, section 0)

| Item                          | Value                              |
| ----------------------------- | ---------------------------------- |
| Accounting API base URL       | `https://api.xero.com/api.xro/2.0` |
| Official OpenAPI specification | `xero_accounting.yaml` **v19.0.0** |
| Official SDK                  | `xero-python` **15.2.0**           |
| Date the platform policies were checked | 2026-09-24                |

**No real Xero tenant was connected.** The brief asks for an integration review, not a working
integration: connecting a real tenant means registering an app, going through OAuth, and leaving
data in a real organisation's books — a cost and risk out of proportion to this task. The limits,
response headers and error codes in the answer therefore all come from the official documentation
and the official OpenAPI specification, with sources linked at the end of `C/README.md`.

> `developer.xero.com` is a JS-rendered site behind a cookie wall, so its body text cannot be
> fetched. The limits and fields in the document were obtained by parsing `xero_accounting.yaml`
> from the official repository `XeroAPI/Xero-OpenAPI`; the repository is linked in the references
> section.

## app — variant PDP

`app/backend` is a FastAPI service (Python 3.11+) and `app/frontend` is a React + TypeScript
single-page application; `app/dev.py` is a launcher that brings both up with one command (standard
library only, no extra dependencies). Install and run commands are in the "Installation" and
"Commands" sections above.

The data is **in-process seed data**: one product (`aurora-tee`) × two option dimensions (colour 3 ×
size 3) = 9 theoretical combinations, of which **7 are real SKUs**. The stock numbers were chosen
deliberately, not filled in at random:

| Combination             | State              | Purpose                                                        |
| ----------------------- | ------------------ | -------------------------------------------------------------- |
| `black / l`, `sage / s` | **does not exist** | An "impossible combination" — it will never be in stock         |
| `sand / s`              | exists, stock 0    | "Temporarily out of stock" — a legal combination, just sold out |
| `sage / m`              | stock exactly 1    | Makes "two requests racing for the last unit" reproducible by hand |

The last two categories must be handled separately: the former is permanently disabled, the latter
can be selected with an explicit out-of-stock notice. Different criteria, different UI.

### API contract

Four endpoints, all under `/api`. **This section is the authoritative statement of the contract.**
The OpenAPI page at `/docs` is generated from the code and complements it, but it cannot express
the semantics below — replay in particular.

| Method | Path                         | Success | Failure                                                                                            |
| ------ | ---------------------------- | ------- | -------------------------------------------------------------------------------------------------- |
| GET    | `/api/health`                | 200     | —                                                                                                  |
| GET    | `/api/products/{product_id}` | 200     | 404 `PRODUCT_NOT_FOUND`                                                                            |
| GET    | `/api/cart`                  | 200     | —                                                                                                  |
| POST   | `/api/cart/items`            | 201     | 400 `VALIDATION_ERROR`, 404 `SKU_NOT_FOUND`, 409 `INSUFFICIENT_STOCK`, 409 `IDEMPOTENCY_KEY_CONFLICT` |

#### Unified error envelope

**Every** failure response shares one envelope, including the framework's own 404 and the 500 from
an uncaught exception. That is deliberate: letting FastAPI's default `422` envelope, the
`HTTPException` envelope and a hand-written `JSONResponse` coexist would make the contract
impossible to state in one place.

```json
{
  "error": {
    "code": "INSUFFICIENT_STOCK",
    "message": "Only 1 unit(s) of TEE-SGE-M are available.",
    "details": { "sku_id": "TEE-SGE-M", "requested": 5, "available": 1 },
    "request_id": "c0a37e28"
  }
}
```

| Field        | Notes                                                                                                                       |
| ------------ | --------------------------------------------------------------------------------------------------------------------------- |
| `code`       | **The value a client should branch on**; the values are listed below and are stable                                          |
| `message`    | Human-readable text; the wording may change, so do not decide anything from it                                                |
| `details`    | Structured extras. `INSUFFICIENT_STOCK` includes `available`, so a client can correct its stale stock figure without another request |
| `request_id` | Correlation id for this request; the `X-Request-ID` response header carries the same value, use it to line up with server logs when reporting a problem |

| `code`                     | HTTP | Trigger                                                        |
| -------------------------- | ---- | -------------------------------------------------------------- |
| `VALIDATION_ERROR`         | 400  | Invalid body, missing `Idempotency-Key`, or a malformed key     |
| `PRODUCT_NOT_FOUND`        | 404  | The product does not exist                                     |
| `SKU_NOT_FOUND`            | 404  | The SKU does not belong to that product                        |
| `INSUFFICIENT_STOCK`       | 409  | The requested quantity exceeds what is available                |
| `IDEMPOTENCY_KEY_CONFLICT` | 409  | The same `Idempotency-Key` was used with a different body       |
| `NOT_FOUND`                | 404  | No such route (thrown by the framework, normalised into the same envelope) |
| `INTERNAL_ERROR`           | 500  | Uncaught exception. Details go to the log only, never to the client |

**`422` never occurs.** FastAPI attaches a 422 response to any endpoint with a body, which
conflicts with the principle above that "validation failures are uniformly 400", so `app.openapi()`
is overridden to remove that response, which can never happen, from the contract.

#### `GET /api/products/{product_id}` → 200

One round trip returns everything the PDP needs: the product, the two option dimensions, and **each
SKU's price, stock and image**. The client resolves variants locally from that and never has to send
another request per selection — which is the structural guarantee that there is no stale UI.

```json
{
  "id": "aurora-tee",
  "name": "Aurora Classic Tee",
  "description": "Midweight organic cotton tee with a relaxed shoulder and a straight hem. ...",
  "currency": "USD",
  "hero_image_url": "/images/aurora-tee-hero.svg",
  "option_dimensions": [
    { "key": "colour", "label": "Colour",
      "values": [
        { "value": "black", "label": "Black", "swatch": "#1C1C1E" },
        { "value": "sand",  "label": "Sand",  "swatch": "#D8C3A5" },
        { "value": "sage",  "label": "Sage",  "swatch": "#8A9A7B" }
      ] },
    { "key": "size", "label": "Size",
      "values": [
        { "value": "s", "label": "S", "swatch": null },
        { "value": "m", "label": "M", "swatch": null },
        { "value": "l", "label": "L", "swatch": null }
      ] }
  ],
  "skus": [
    { "id": "TEE-SND-M", "options": { "colour": "sand", "size": "m" },
      "price_minor": 5300, "currency": "USD",
      "available_quantity": 6, "in_stock": true,
      "image_url": "/images/tee-sand-m.svg" }
  ]
}
```

`skus` is sorted by id, guaranteeing that the same catalogue is byte-identical across two calls.
`swatch` only carries a value on the colour dimension — sizes have no visual identity, and a text
label beats a colour chip there. `in_stock` is computed server-side so that no client has to
reimplement the rule "`available == 0` means out of stock" — and get it wrong.

#### `POST /api/cart/items` → 201

**Request headers**

| Header            | Required | Notes                                                       |
| ----------------- | -------- | ----------------------------------------------------------- |
| `Idempotency-Key` | **yes**  | ≤ 128 visible ASCII characters (0x21–0x7E). Missing → 400    |
| `Content-Type`    | yes      | `application/json`                                          |

**Request body**

```json
{ "sku_id": "TEE-SND-M", "quantity": 2 }
```

| Field      | Constraint            |
| ---------- | --------------------- |
| `sku_id`   | 1–64 characters       |
| `quantity` | `1 ≤ quantity ≤ 100`  |

**Only these two fields are accepted.** A client that also sends `price_minor` or `stock` gets a
400, rather than having it silently ignored:

```json
{"error":{"code":"VALIDATION_ERROR","message":"Invalid request: price_minor -- Extra inputs are not permitted.","details":{"fields":[{"field":"price_minor","reason":"Extra inputs are not permitted"}]},"request_id":"ef1eef2e"}}
```

Rejecting is stronger than ignoring: ignoring only says "we did not read it", rejecting says "that
path does not exist at all".

**Response 201**

```json
{
  "cart": {
    "id": "cart-1",
    "currency": "USD",
    "items": [
      { "sku_id": "TEE-SND-M", "quantity": 2,
        "unit_price_minor": 5300, "line_total_minor": 10600,
        "name": "Aurora Classic Tee — Sand / M",
        "image_url": "/images/tee-sand-m.svg",
        "options": { "colour": "sand", "size": "m" } }
    ],
    "total_item_count": 2,
    "subtotal_minor": 10600
  },
  "sku_availability": { "sku_id": "TEE-SND-M", "available_quantity": 4 }
}
```

The response carries **the whole cart** back, so the frontend does not need a follow-up
`GET /api/cart`. `sku_availability` is inlined — it lets the client refresh its own stock figure
straight from this response, with no guessing and no extra round trip.

**Idempotency semantics.** The same `Idempotency-Key` with the same body **must** produce the same
status code and response body as the first attempt, byte for byte, and the cart must not be
incremented twice. The only in-band signal is a response header:

```
HTTP/1.1 201 Created
idempotency-replayed: true
```

A replay **reuses the original status code** (201 stays 201, 409 stays 409) rather than using 200
to mark it — "a replay is still a successful add-to-cart" is the more accurate semantics, and the
client does not need an extra branch for it.

The same key with a **different body** is a client bug and returns 409
`IDEMPOTENCY_KEY_CONFLICT` rather than handing back the original response: hiding it would only
make something unexplained appear in the cart later.

**A rejected attempt still counts as processed.** After an initial 409 for insufficient stock,
retrying with the same key returns that same 409 and never gets a second chance to succeed. This
matches Task A's stance (a business-rejected event still counts as processed).

#### `GET /api/cart` → 200

Returns the `cart` object shown above. `total_item_count` is the sum of **units**, not of lines.

```json
{"id":"cart-1","currency":"USD","items":[{"sku_id":"TEE-SND-M","quantity":2,"unit_price_minor":5300,"line_total_minor":10600,"name":"Aurora Classic Tee — Sand / M","image_url":"/images/tee-sand-m.svg","options":{"colour":"sand","size":"m"}}],"total_item_count":2,"subtotal_minor":10600}
```

#### CORS

The allowed origins default to `http://localhost:5173` and `http://127.0.0.1:5173`, overridable via
the `CORS_ALLOW_ORIGINS` environment variable. **Never `*`** — this service has no authentication,
and the origin allow-list is the only thing standing between it and "any page on the internet".

`Idempotency-Key` is a custom header and **must** be listed explicitly in `allow_headers`,
otherwise the browser preflight fails; `curl` does not do preflight, so this failure only shows up
in a browser.

### Tests

| Suite                  | Command                                | Result                       |
| ---------------------- | -------------------------------------- | ---------------------------- |
| app backend            | `cd app/backend && uv run pytest -q`   | **36 cases**                 |
| app frontend           | `cd app/frontend && npm test`          | **29 cases / 4 files**       |
| frontend type check    | `cd app/frontend && npm run typecheck` | 0 errors                     |

The backend has 4 test files (plus `conftest.py`, which resets the store per case) covering four
categories: the success path, validation failures, idempotency-key repetition and conflict, and
stock races (two requests chasing the last unit). Of the 6 integration cases in the frontend's
`ProductPage.test.tsx`, two are the ones the brief names: **changing an option updates the SKU /
price / image / stock together**, and **repeated clicks while a request is in flight send only one
request**; the other four cover illegal combinations being disabled, the quantity converging after
a variant switch, the client adopting an updated stock figure from the server, and retrying after a
failure. The remaining 3 files are unit tests for the pure functions in `domain/` (23 cases).

## Assumptions

Points the brief does not settle but that an implementation has to decide. Each entry states "what
was chosen" and "why", so that a misreading of the brief can be spotted.

### Task A — inventory reservation ledger

**Input shape and output format**

1. **The closing section uses `OPEN <number of open reservations>` plus one detail line per
   order**, rather than a single total. The original wording is "print open reservations"
   (plural); a bare total makes it impossible to verify *which* orders are open, and that total
   would then duplicate the third column of the last status line exactly.
   `--open-format total` switches to the total-only mode.
2. **A pure blank line is skipped**, not counted towards N and producing no output line. Treated as
   malformed instead, a single extra trailing newline would add an extra output line and break the
   line-by-line comparison with the sample.
3. **When the number of input lines does not match `N`**: stop after N commands and ignore any extra
   lines entirely; if there are fewer than N, finish normally at EOF without raising.
4. **The field count must match exactly**: `RESERVE` / `RELEASE` / `SHIP` take exactly 4 tokens and
   `RESTOCK` exactly 3; one too many or too few is malformed.
5. **Line endings and encoding**: input accepts LF and CRLF and is read as UTF-8 text; **output is
   forced to LF** and does not follow the platform default. On Windows `sys.stdout` turns `\n` into
   `\r\n`: the bytes still parse and the content is still right, but the byte count no longer
   matches the expected sample file.
6. **The header is the only hard failure**: the `S N` header must be present with
   `0 ≤ S ≤ 10^12` and `1 ≤ N ≤ 200000`, otherwise the program writes to stderr and returns exit
   code 2, with nothing on stdout. The header is not a command, so there is no "current state" to
   print and it does not go through the `REJECTED` path.

**Validation stance**

1. **`qty` is validated as strictly numeric** (`^[0-9]+$`), so `+5`, `1_000`, `1.5`, `-3`, `0` and
   non-ASCII digits (e.g. the Arabic-Indic `٥`) are all malformed. This is a deliberate
   tightening: Python's `int()` accepts `+5`, `1_000` and `٥`, and none of them should be taken.
2. **Command names are case-sensitive**: `reserve` is an unknown command → malformed.
3. **Tokens are split on any whitespace** (spaces, tabs, runs of both), not with `split(" ")`, so
   that repeated spaces are not misread as an empty token.
4. **`event_id` / `order_id` are read as "non-empty ASCII tokens"**: characters in the printable
   ASCII range (0x21–0x7E); no further character-set restriction and no length limit beyond
   non-emptiness (see "Known limitations").
5. **The `event_id` of a malformed line is not recorded in the idempotency set.** The original
   states the two rules separately, and the second one is explicitly limited to events rejected
   "**by business rules**". Therefore: a business rejection (insufficient stock) → recorded, and a
   replay returns `DUPLICATE`; a parse failure (malformed) → not recorded, and a replay still
   returns `REJECTED`. Supporting reason: a malformed line may not even have a legal `event_id`,
   and recording it would mean inventing a rule with no source. The behaviour is controlled by the
   module constant `MALFORMED_EVENTS_OCCUPY_EVENT_ID` (currently `False`; set it to `True` to flip
   the stance).

**Environment**

1. **Python 3.11+, standard library only** (`re` / `sys` / `dataclasses`), no third-party
   dependencies.
2. **The input is a trusted batch file**, not an adversarial data stream — hence no hash-collision
   hardening (see "Known limitations").

### Task B — fulfilment split optimiser

**There is exactly one failure exit**

1. **Every "cannot produce a plan" case outputs `-1`**, the exit code is always 0 and **stderr is
   empty**. The original says **nothing at all** about invalid input for Task B (unlike Task A,
   which states *Reject malformed input without partial state changes*); it defines a single failure
   output: *Print -1 when the order cannot be fulfilled*. Since the original offers only that one
   exit, infeasibility, invalid input, too few lines and a missing file all go through it — the
   fewest rules. The cost is that "not enough stock" and "the input is malformed" cannot be told
   apart from outside; recorded under "Known limitations".
2. **Writing nothing to stderr is not merely a matter of taste**: some evaluation setups capture
   output with `2>&1`, so any stderr content would pollute the line-by-line comparison.
3. **A missing input file also outputs `-1`**, likewise filed under "cannot produce a plan".

**Input shape**

1. **A pure blank line is skipped** and does not consume one of the W slots (the same stance as
   Task A). Treated as invalid instead, one extra trailing newline would turn the output from an
   answer into `-1`.
2. **When the number of lines does not match `W`**: stop after W lines and ignore any extra lines
   entirely; fewer than W lines outputs `-1`.
3. **The field count must match exactly**: the header takes exactly 2 tokens and a warehouse line
   exactly 4.
4. **`stock = 0` and `fixed_cost = unit_cost = 0` are both valid input** (the constraints say
   `0 ≤`), not invalid. Zero stock means the warehouse has nothing, which is "unusable" rather than
   "an input error".
5. **Line endings and encoding**: input accepts LF and CRLF; **output is forced to LF** (as in Task
   A, for the reason given above).
6. **`warehouse_id` is read as a "non-empty ASCII token"** and sorted byte-wise. **Ids are assumed
   unique** — the brief treats it as a warehouse identifier, and "sort by `warehouse_id`" is
   **undefined** when ids repeat (which of two entries with the same id comes first? The original
   does not say). Measured: with duplicate ids the solver still gets the warehouse count and total
   cost right; only the tie-break of "how much each of the two rows with the same id takes" differs
   from a "sort by the whole `(id, qty)` pair" reading.

**The comparison unit for the third objective**

1. **Compare numeric tuples `(warehouse_id, allocated_qty)`, not the rendered strings.** The two
   give opposite answers on a tie: `(A,2),(B,10)` and `(A,10),(B,2)` cost the same, and the numeric
   comparison prefers the former (`2 < 10`) while the string comparison prefers the latter
   (`"A 10" < "A 2"`). The original says the allocation **list**, whose elements are the pair
   "warehouse + quantity", and `qty` is a number; a string comparison would also put `qty = 9`
   after `qty = 10`, contradicting the direction of "minimise". The sample has a single allocation
   and cannot settle it.
2. **Output lines are ascending by `(warehouse_id, allocated_qty)`**, consistent with the
   comparison above; with unique ids this is exactly equivalent to "sorted by id".

**Environment**

1. **Python 3.11+, standard library only** (`sys` / `re` / `dataclasses` / `collections.deque`),
   with **no external solver** — the brief forbids one explicitly.
2. **The constraints themselves guarantee valid input** (phrasings such as `1 <= W <= 30`,
   `0 <= stock <= 2,000`), so defending against invalid input is, on the original's own terms,
   **optional**; the implementation does only enough to "not crash and emit `-1`".

### Task C — Xero integration review

**Versions and basis**

1. **The answer is written against specific versions, not against "roughly how it is".** The API
   base URL is v2.0, the specification is the official `xero_accounting.yaml` v19.0.0 and the SDK is
   `xero-python` 15.2.0. Xero's limits and endpoints change, and an answer not anchored to a
   version cannot be checked a few months later.
2. **Response headers are the authority on limits; the numbers in the docs are only a reference.**
   The official docs give current general values, while the actual quota floats with the tenant and
   the load; the answer therefore treats "read the response headers" as the only authoritative
   source and uses the documented values only to set the initial backoff rhythm.
3. **No real tenant is connected** (reason above, in the Task C section). The answer therefore
   contains mechanisms and ordering, with no demo data.

### app — variant PDP

**Stock and cart semantics**

1. **Adding to the cart is a reservation, `available = stock − reserved`.** There is no checkout
   and no payment, and the brief does not ask for them, so "add to cart" is the only way this
   application can express holding stock. Stock is held as two counters rather than one decrementing
   number, so that the fact "there were 4, and 3 of them are in the cart" stays queryable (see
   "Design notes").
2. **The cart is a global singleton, with no session and no user.** The brief explicitly does not do
   authentication, and inventing a session id for a user model that does not exist would only add
   another thing to maintain.
3. **Each SKU appears at most once in the cart; adding again accumulates rather than appending a
   line.** Two lines with the same SKU would turn "how many of this product" into a summation, and
   the frontend already has to display that number.
4. **The 100-unit and 50-line caps are my own choice**, not something the brief asks for. Their
   purpose is to stop a single request from reserving an absurd amount of stock, which would
   otherwise distort how the stock race behaves.

**Data and money**

1. **Amounts are always integers in minor units (`price_minor`), never floats.** Decimal fractions
   cannot be represented exactly in binary floating point, and the cart subtotal is displayed.
2. **The currency is USD.** The brief does not specify one and the choice does not affect the
   structure. The `*_minor` field names are kept, so switching currency means changing the
   `currency` field and the formatting rules only.
3. **The product images are script-generated placeholder SVGs** (one per SKU plus one hero), not
   real product photography. The brief supplies no assets, and "the image changes with the SKU" is a
   behaviour that has to be visible.
4. **`in_stock` and `available_quantity` are both supplied by the server**, not left for clients to
   derive — the rule "`available == 0` means out of stock" should exist in exactly one place.

**Frontend trade-offs**

1. **Variants are resolved locally; no request per selection.** The catalogue endpoint returns every
   SKU at once; querying per selection would force the UI to keep showing the previous variant's
   price and stock while the request is in flight, which is precisely how stale UI happens.
2. **"Impossible combination" and "out of stock" are two states, not one.** The former is
   permanently disabled, the latter selectable but flagged as out of stock — different criteria, so
   the option state is tri-state (`available` / `out-of-stock` / `impossible`) rather than a
   boolean.
3. **When the server rejects an add-to-cart for insufficient stock, its `available` value is
   adopted and the quantity converges to a legal value.** The brief mentions the reviewer will
   "return a more up-to-date stock figure than the initial product response"; refusing to update
   locally would leave the quantity cap frozen at the moment of first load for ever.
4. **No optimistic UI.** Add-to-cart is "submit → wait for server confirmation → update the UI",
   rolling back to the unsubmitted state on failure. Optimistic updates are an optional bonus that
   needs extra tests and documentation (see "Known limitations").

## Design notes

### Task A — inventory reservation ledger

**State model — three mutable parts.**

| Field       | Meaning                             | Changes on                       |
| ----------- | ----------------------------------- | -------------------------------- |
| `on_hand`   | physical stock                      | `SHIP` / `RESTOCK` only          |
| `reserved`  | **global** reserved total           | `RESERVE` / `RELEASE` / `SHIP`   |
| `per_order` | `order_id → that order's reservation` | `RESERVE` / `RELEASE` / `SHIP` |
| `processed` | set of processed `event_id`s        | every event judged to be processed |

`available = on_hand - reserved` is a **computed property with no stored field** — storing it would
mean keeping it consistent, and a computed value cannot be wrong.

`reserved` and the sum of `per_order` are **deliberately redundant**: querying
`sum(per_order.values())` on every command would degrade a single command to O(number of orders) and
break the O(N) bound outright. The price of the redundancy is that the two could drift, so all state
changes are allowed to happen in exactly one place, `Ledger.apply()`, and the tests back it up with
the invariant `reserved == sum(per_order.values())`.

**Validation and idempotency — the four steps cannot be reordered.**

```
parse → deduplicate → business verdict → state change
```

The order is itself the design:

- **Parsing is separated from execution**, making "malformed input has zero side effects" a
  **structural property** rather than a rule to remember — `parse_command()` only checks syntax and
  value ranges and never touches state.
- **Deduplication must precede the business verdict, and compares only `event_id`** — not the
  command type or the other parameters. Item 6 of the official sample exists to verify exactly this:
  when `e2` is replayed the order id and quantity have both changed and the stock is now
  sufficient, and the correct answer is still `DUPLICATE` rather than `OK`. Reverse the order and
  it breaks.
- **A business-rejected event is still recorded in the idempotency set** (the original: rejected by
  business rules still counts as processed), so replaying it returns `DUPLICATE`, not `REJECTED`
  again.

**Interface layering.** `run()` is a pure function (sequence of input lines → list of output lines)
that neither reads files nor writes to stdout, and every test calls it directly; `main()` is
nothing but argument parsing and I/O glue. Tests therefore need no subprocess or stream redirection,
and the logic density sits in a few functions.

**I/O strategy.** Input is streamed line by line (the whole file is never `read()`); output
accumulates into a list and is written in one `write`, avoiding the syscall cost of flushing line by
line at N = 200,000.

**Trade-offs deliberately accepted.**

1. **The closing section keeps `sorted()`**, so the worst-case complexity is O(N log N) rather than a
   pure O(N). As long as the output must be ordered, Ω(K log K) is unavoidable. Counting sort or
   radix sort would make the readable code several times longer for a different asymptotic symbol,
   and K (open orders) is in practice far smaller than N. The brief explicitly prefers clarity over
   unnecessary complexity, so readability won over the symbol here — the cost is recorded under
   "Known limitations".
2. **Output buffering costs O(N) memory** in exchange for writing everything in one go. Printing N
   lines means holding those N lines first, and that cannot be compressed.
3. **`reserved` is stored redundantly** in exchange for O(1) status-line output.
4. **A malformed header produces no degraded output**: stderr plus exit code 2, rather than forcing
   out N lines of `REJECTED`. With no valid header there is no trustworthy state to print.

### Task B — fulfilment split optimiser

**State representation — one structure per stage.**

| Structure                     | Contents                                                                                          | Size                   |
| ----------------------------- | ------------------------------------------------------------------------------------------------- | ---------------------- |
| `warehouses`                  | `(id, stock, fixed_cost, unit_cost)`, **ascending by id, byte-wise**                               | W ≤ 30                 |
| `cost[i][s][r]`               | suffix DP: minimum cost using warehouses after the i-th, exactly s of them, exactly r units        | (W+1) × (k*+1) × (Q+1) |
| `best_cap` / monotonic queue  | one queue per `(i, s)`, keeping the sliding-window minimum of `cost[i+1][s-1][b] − b·unit`         | ≤ stock + 1            |

`warehouses` is sorted once and **every index afterwards refers to that order** — the greedy
direction in stage 3, the output line order and the lexicographic comparison all share the one
order, so there is no mismatch between "decide by one order, print by another".

**Each layer allocates only the rows it can use.** In `cost[i][s]`, s cannot exceed the number of
warehouses left at layer i, `W - i`, and the allocation follows that bound. On the worst case
(`W = k* = 30`) the row count therefore drops from `W × k* = 900` to 465, nearly half.

**Why "rejection" is a return value and not an exception.** Task A expresses a hard failure with
`HeaderError` + stderr + exit 2; Task B has no hard failure, and every failure collapses to `["-1"]`
inside `solve()`, with no exception raised and nothing on stderr. The reason: Task B has one
external exit, a return value is enough to express it, and introducing an exception hierarchy would
add a mechanism to maintain. This is **deliberately** inconsistent with Task A — the two originals
impose different constraints (Task A says `Reject malformed input` in so many words, Task B does
not).

**Interface layering.** `solve()` is a pure function (sequence of input lines → list of output
lines) that every test calls directly; `main()` is only argument parsing, file reading and buffered
writing.

**Trade-offs deliberately accepted.**

1. **Space is O(W·k\*·Q), not O(k\*·Q)**: stage 3 reconstructs forward in id order and needs random
   access to every suffix layer. Reverse reconstruction would cut memory to O(k*·Q), but then the
   lexicographically smallest solution could not be recovered — the price of the third objective.
2. **A single failure exit**: giving up the ability to distinguish "invalid input" from
   "insufficient stock" in exchange for consistency with the original's semantics and fewer rules
   (see "Assumptions").
3. **No extra input-validation defence**: the constraints themselves guarantee valid input, and
   writing a validation and diagnostics layer for it would be writing code for a problem that does
   not exist, while the brief explicitly prefers avoiding unnecessary complexity. The current
   defence only guarantees "does not crash, emits `-1`".
4. **Duplicate `warehouse_id`s are not special-cased**: the brief treats the id as an identifier,
   and a duplicate id makes "sort by id" undefined — a problem in the input domain rather than
   complexity the solver should absorb.

### Task C — Xero integration review

**Structure.** `C/README.md` is organised as "section 0 version assumptions → C1–C6 → three
correspondences with the scenario". Putting section 0 first is deliberate: limits, fields and
endpoints change with the version, and declaring the basis before answering is what makes every
later reference checkable.

**Every question is written the same way: conclusion first, then the basis, then the boundaries.**

| Question                     | Shape of the answer                                                                       |
| ---------------------------- | ----------------------------------------------------------------------------------------- |
| C1 connection validation     | which endpoint, what the criterion is, and which response headers to look at too           |
| C2 failure diagnosis         | layered by **which layer the failure happened at**, not flattened by error code             |
| C3 incremental sync          | the cursor is `(app_id, tenant_id)` and the watermark only advances after a fully successful round; **the window blind spot must be stated** |
| C4 rate limiting             | read the response headers first, then talk backoff and jitter; the concurrency cap is independent of request rate |
| C5 data integrity            | five layers: official idempotency key → external business key → ordering of timeouts → batch partial success → local state machine |
| C6 observability & security  | logs / metrics / alerts written separately, plus the fields that must **never** be logged   |

**"Reconcile first, then decide whether to retry" is the core of C5.** A timed-out write request
means "we do not know whether it landed", and at that point both retrying and giving up can be
wrong — the only correct action is to look first, rather than pick one of two guesses.

### app — variant PDP

**Three layers, dependencies in one direction.**

```
api/      →  fetch wrapper, error normalisation, idempotency-key generation (knows about HTTP)
domain/   →  pure functions: variant resolution, quantity clamping, money formatting (knows neither React nor the network)
ui/       →  components and orchestration (takes conclusions from domain only)
hooks/    →  feed api results into ui
```

`domain/` contains no React and no `fetch`, so it can be tested directly under `node` and reused
elsewhere. `ui/` **does not compute prices, stock or quantity caps itself** — they are all derived
in one place, `resolveSku(selection)`. That is the structural guarantee that stale UI cannot happen:
as long as every value on screen comes from the same resolution, there is no half-new state where
"the price updated but the stock is still the old one".

**Duplicate add-to-cart prevention is three lines of defence, not one.**

| Defence                  | The case it stops                                          |
| ------------------------ | ----------------------------------------------------------- |
| Button `disabled`        | A normal user sees "in progress" and does not click again    |
| **`useRef` synchronous guard** | Two clicks within the same frame — `state` has not updated yet |
| `Idempotency-Key`        | A repeat after the request has already gone out              |

The second is not redundant. Measured: replacing it with a `pending` state makes two clicks within
one frame send **two** requests — both clicks read `isPending === false`. The repeated-click case in
the frontend tests guards this.

**The backend's concurrency control does read-verdict-write inside one critical section.**
"Look up the idempotency key → validate stock → commit → store the response" holds the
`asyncio.Lock` throughout. Splitting it would let two requests with the same key both miss the
record and both commit — exactly what the header exists to prevent. The `await asyncio.sleep(0)` in
`_reserve()` is not decoration: it stands in for the database round trip this will eventually
become, and it sits deliberately **after reading `available` and before judging from it**, which is
the window a real round trip would open. Put it before the read and the race disappears, and the
tests would pass just as well with the lock deleted — proving nothing.

**A replay returns the original response rather than building a new one.** The idempotency record
stores the first `status_code` and the complete `body`, and a replay hands them back unchanged with
an added `Idempotency-Replayed: true`. A replay is therefore byte-for-byte a first attempt, and the
client needs no second branch for it.

**Error handling has a single exit.** Four kinds of exception — the custom `ApiError`, FastAPI's
`RequestValidationError`, the framework's `HTTPException` and the catch-all `Exception` — all
converge on the same envelope (see "Unified error envelope" above). Rewriting validation failures
from 422 to 400 and keeping 500 details in the log only are both aimed at leaving the client a
single shape to recognise. The price of that single exit: **internal errors are completely
invisible to the client**, and diagnosis depends on lining up `request_id` with the server log —
a deliberate trade-off, not an oversight.

**Trade-offs deliberately accepted.**

1. **All state lives in process memory**: bought "clone it and it works" and zero external
   dependencies. The cost is under "Known limitations".
2. **No optimistic UI in the frontend**: add-to-cart is a low-frequency write, and the rollback
   state machine an optimistic update brings is more expensive than the wait it saves.
3. **No state-management library**: the whole page is a single shallow state tree, and `useState`
   plus two custom hooks are enough; pulling in something like Redux would be exactly the
   over-building the brief discourages.

## Known limitations

### Task A — inventory reservation ledger

- **The worst-case complexity is O(N log N), not strictly O(N).** The lower bound of the closing
  sort is Ω(K log K), and that section dominates when K grows with N. The processing loop itself is
  strictly O(N). No non-comparison sort was introduced; the reasoning is under "Design notes".
- **"Amortised O(1)" depends on bounded token length.** `qty` is bounded (≤ 10^12), but the spec
  only says `event_id` / `order_id` are non-empty ASCII tokens, with **no upper bound**. The more
  rigorous statement is therefore **O(total input bytes)**, with N the number of commands rather
  than bytes. The program has no defence against an over-long token.
- **No hash-collision hardening.** `set` / `dict` lookup is amortised O(1), O(n) worst case. The
  input here is not an adversarial data stream, so no hardening was added; as an internet-facing
  service it would need a length cap or randomised hashing.
- **Single SKU only.** The brief asks for that. Extending to multiple SKUs means turning the three
  counters into per-SKU maps and additionally defining the atomicity of cross-SKU operations — not
  simply adding a dictionary layer.
- **No persistence and no concurrency control.** The intended role is a single-process batch
  program, not a concurrent service; state disappears when the process ends, and there is no
  cross-process stock consistency guarantee.
- **Malformed input only prints `REJECTED`, with no diagnostic.** The brief does not ask for one,
  and an error reason would pollute the line-by-line stdout format. When diagnosing, all you can
  tell is "this line was rejected", not whether the field count was wrong or the quantity invalid.
- **The closing section's format is inferred.** The sample happens to have 0 open reservations, and
  both candidate formats (count / total) print identically, so nothing can be deduced from it. Both
  are therefore implemented, defaulting to the more informative `list`; the reasoning is
  assumption 1 above.

### Task B — fulfilment split optimiser

- **"Invalid input" and "insufficient stock" are indistinguishable from outside.** Both output `-1`
  (the original defines only that one failure exit). A misspelled filename or a line with one field
  missing both produce `-1` rather than a diagnostic, so troubleshooting means checking the input by
  hand. This is a deliberately accepted cost; the reasoning is under "Assumptions".
- **`warehouse_id`s are assumed unique.** "Sort by `warehouse_id`" is **undefined** when ids repeat.
  Measured: with duplicate ids the warehouse count and total cost are still correct, but the
  tie-break of "how much each of the two rows with the same id takes" differs from a "sort by the
  whole `(id, qty)` pair" reading. Faced with such input in practice, the merge rule has to be
  confirmed first.
- **The space is O(W·k*·Q).** Forward reconstruction requires keeping every suffix layer, about
  17 MiB on the worst case; giving up the lexicographically-smallest objective would bring it down
  to O(k*·Q).
- **The stage-3 greedy depends on the "sort by `(id, qty)`" reading.** If the third objective was
  meant to compare rendered strings, tie cases would produce different output (see "The comparison
  unit for the third objective" under "Assumptions").
- **`Q = 0` is not supported** (the constraint is `1 <= Q`). If zero were allowed, the minimum
  warehouse count would be 0 and the cost 0, and the output would need defining separately; it is
  currently treated as invalid input and outputs `-1`.
- **No streaming output and no incremental solving.** Everything is read once and solved once,
  which fits the role of a batch program.
- **No code is shared with Task A.** The two programs are independent, including their own parsing
  and failure-handling stances — deliberately: extracting an abstraction neither of them needs, in
  the name of "consistency", would not pay for itself.

### Task C — Xero integration review

- **No real tenant was connected.** The limits, response headers and error codes in the answer come
  from the official documentation and the official OpenAPI specification rather than from
  measurement. A tenant's actual quota may differ from the documented values, and the response
  headers should be treated as authoritative when integrating (which is what the answer itself
  says).
- **The written English in this repository is uniform, with one deliberate exception.**
  `C/README.md`, this root `README.md` and all code comments and docstrings are in **English**,
  matching the brief. The only non-ASCII text anywhere in the deliverable is two test inputs in
  `A/test_taskA.py` — `"RESERVE e1 订单 1"` and `"RESERVE 事件 o1 1"` — which exist precisely to
  prove that a non-ASCII `order_id` / `event_id` is rejected as malformed. Translating them into
  ASCII would defeat their purpose, so they stay.
- **It contains no runnable integration code.** The brief asks for a review, not an implementation;
  there is no OAuth callback and no retry implementation under `C/`, only mechanisms, ordering and
  sources.

### app — variant PDP

- **All state is in process memory, lost on restart, and multiple workers are not supported.** That
  is the price of "clone it and it works". The stock-race protection is an `asyncio.Lock`, valid
  **within a single process** only; moving to multiple workers or instances means replacing the
  critical section with a database row lock or optimistic concurrency control, otherwise it will
  oversell.
- **There is no authentication and the cart is a global singleton.** The brief explicitly does not
  do authentication, so every visitor shares one cart. That is not an oversight but the boundary of
  the scope — and the first thing to add if this ever faces outward.
- **The frontend was never clicked through by hand in a real browser.** Verification was a walk
  through the complete HTTP call sequence the frontend issues (including replay, conflict,
  insufficient stock, and a client-supplied price being rejected), plus 29 component-level tests.
  The contract layer is complete; the render timing and the real click path have not been confirmed
  by eye.
- **`TEE-SGE-M` has only 1 unit, and the cart never releases stock.** Repeatedly demoing
  add-to-cart will consume the demo stock; restarting the backend restores it.
- **Two optional bonus items were not done.** Optimistic UI + rollback (`FE-17`) and analytics
  instrumentation (`FE-18`). The one-command launcher (`FE-19`, `app/dev.py`) is implemented.
- **The images are placeholder SVGs.** The brief supplies no assets; the 8 images are
  script-generated, purely so that "the image changes with the SKU" is visible.

## Third-party dependencies

Listed explicitly as the brief requires. **`A/` and `B/` have no third-party dependencies at all and
use only the standard library.**

### `app/backend` — see `app/backend/pyproject.toml`

| Dependency          | Kind      | Purpose                                                                  |
| ------------------- | --------- | ------------------------------------------------------------------------ |
| `fastapi`           | runtime   | HTTP framework (the brief names FastAPI for the Python backend)           |
| `pydantic`          | runtime   | Request / response models. `extra="forbid"` is where "refuse a client-supplied price" is implemented |
| `uvicorn[standard]` | runtime   | ASGI server                                                              |
| `httpx`             | test      | the transport backing `TestClient`                                        |
| `pytest`            | test      | test framework                                                           |
| `pytest-asyncio`    | test      | the service is fully async, and `auto` mode saves a `@pytest.mark.asyncio` on every case |
| `uv_build`          | build     | uv's build backend, installing `src/backend` as an editable package        |

Runtime and test dependencies are kept apart: the test stack lives in `[dependency-groups] dev`, so
`uv sync --no-dev` will not drag pytest and httpx into a deployment image.

### `app/frontend` — see `app/frontend/package.json`

| Dependency                          | Kind      | Purpose                                                        |
| ----------------------------------- | --------- | -------------------------------------------------------------- |
| `react` / `react-dom`               | runtime   | UI (the brief names React + TypeScript)                          |
| `typescript`                        | dev       | type checking (required by the brief); `tsc --noEmit` is its own command |
| `vite`                              | dev       | dev server and bundling                                          |
| `@vitejs/plugin-react`              | dev       | JSX transform and Fast Refresh                                    |
| `@types/react` / `@types/react-dom` | dev       | React type declarations                                          |
| `vitest`                            | test      | test runner                                                      |
| `jsdom`                             | test      | browser environment simulation                                    |
| `@testing-library/react`            | test      | assert on user-visible behaviour rather than implementation detail |
| `@testing-library/user-event`       | test      | real event semantics (clicks and keyboard included)               |
| `@testing-library/jest-dom`         | test      | readable DOM assertions                                          |

Both lock files (`uv.lock`, `package-lock.json`) are **committed on purpose**: the `^` ranges above
are constraints only, the exact versions are pinned by the lock files, so that `uv sync` and
`npm ci` reproduce the set of versions verified during development.

## AI tool usage disclosure

Disclosed as the brief requires, with the scope and the locations.

**Scope.** The requirements analysis, code, tests and first drafts of the documentation in this
repository were produced by an AI coding assistant (WorkBuddy) in interaction with the author.

**Where it was used.**

| Location                      | Scope                                                                 |
| ----------------------------- | --------------------------------------------------------------------- |
| Requirements analysis         | extracting numbered requirements, data contracts and an ambiguity list from the brief's screenshots |
| `A/`, `B/`                    | algorithm implementations, test cases, first draft of the complexity analysis |
| `C/README.md`                 | first draft of the six answers; it looked up and verified the version numbers and official links |
| `app/backend`, `app/frontend` | all code and tests                                                    |
| root `README.md`              | organising the results, trade-offs and limitations                     |

**What the author owns.** Every decision that was committed was reviewed by the author, who is
accountable for the content:

- **Ambiguities in the brief were settled by the author**, not chosen by the AI. For example the
  Task A closing-line format (`OPEN <count>` plus details) and Task B's single failure exit (always
  `-1`, nothing on stderr) are stances the author selected explicitly.
- **The repository layout and the delivery shape were decided by the author**: **the committed
  content is only `A/ B/ C/ app/ README.md`**, with no additional top-level directories; the
  development-time working copy and intermediate artefacts (`Code/`, `DEVELOPMENT_SPEC.md`,
  `DESIGN_*.md`) stay on the author's machine and are not committed.
- **Key conclusions rest on machine-checkable experiments**, not on the AI's assertions.
  Byte-for-byte comparison against the official samples, Task B's exhaustive cross-checks, and two
  "remove a line of defence and see whether the tests fail" experiments — deleting the
  `asyncio.Lock` made all 4 concurrency cases fail; replacing the `useRef` synchronous guard with a
  `pending` state made two clicks within one frame send two requests. The tests really are pressing
  on those defences, rather than passing by coincidence.
- **Dependency and tooling choices, and the documentation's stance and language, were confirmed by
  the author.**

**Limitations.** AI-generated code can contain details the author has not fully internalised. The
way this repository handles that is to write the "why it was chosen this way" and the cost of every
key decision into this README, and to back every rule with a test; all tests were run on the
author's machine before submission (A 70, B 68, backend 36, frontend 29).
