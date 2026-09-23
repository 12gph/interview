# Variant PDP API (backend)

FastAPI service behind the product detail page: catalog lookup, idempotent
add-to-cart, and a cart read endpoint.

## Requirements

- Python 3.11+ (developed and tested on 3.12)
- [uv](https://docs.astral.sh/uv/) -- recommended, but not required; a plain
  `venv` + `pip` route is given below

## Setup and run

```bash
# with uv (uses uv.lock, so you get the exact versions this was tested against)
uv sync
uv run uvicorn backend.main:app --reload --port 8000
```

```bash
# without uv
python -m venv .venv
.venv/bin/pip install -e . --group dev    # Windows: .venv\Scripts\pip install -e . --group dev
.venv/bin/uvicorn backend.main:app --reload --port 8000
```

`--group dev` installs what `uv sync` installs by default (pytest, httpx and
pytest-asyncio), so both routes end up with the same environment. Drop it if you
only need to serve; pip older than 25.1 does not understand `--group`, so install
those three packages by name instead.

The API then listens on `http://localhost:8000`, with interactive docs at
`http://localhost:8000/docs`.

> `pyproject.toml` declares an Aliyun PyPI mirror as the default index because the
> development machine needs it. If your network reaches pypi.org directly, override it:
> `uv sync --default-index https://pypi.org/simple`.

## Tests

```bash
uv run pytest                       # or: .venv/bin/python -m pytest
```

The `venv` form needs the dev dependencies from the setup section above;
`uv run` does not care because `uv sync` installs them anyway.

## Layout

```
backend/
├── pyproject.toml       # the only config file: deps, build, pytest options
├── uv.lock              # exact resolved versions, committed for reproducibility
├── src/backend/         # the application package
│   ├── main.py          # app factory + ASGI entry point
│   ├── routers/         # HTTP layer: products, cart
│   ├── store.py         # in-memory state, write lock, idempotency ledger
│   ├── seed.py          # catalog fixture
│   ├── models.py        # request/response schemas
│   ├── errors.py        # error envelope + exception handlers
│   ├── middleware.py    # request-id correlation
│   └── config.py        # settings
└── tests/               # pytest suite
```

## Endpoints

| Method | Path                        | Notes                                           |
| ------ | --------------------------- | ----------------------------------------------- |
| `GET`  | `/api/products/{product_id}` | Product with its variant dimensions and SKUs    |
| `POST` | `/api/cart/items`           | Add a SKU to the cart; requires `Idempotency-Key` |
| `GET`  | `/api/cart`                 | Current cart contents                           |
| `GET`  | `/api/health`               | Liveness probe                                  |

Request and response payloads, status codes, error envelope, and the assumptions
behind them are documented in the repository root `README.md`.
