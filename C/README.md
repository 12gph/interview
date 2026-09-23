# Task C — Xero Integration Review

A multi-tenant service synchronises invoices between an internal order system and Xero; the
synchronisation runs in a background worker. Tokens, tenant IDs and sync cursors are stored
per connected organisation.

---

## 0. Version assumptions and basis

| Item | Assumption |
| ---- | ----------------------------------------------------------------------- |
| API | Xero **Accounting API**, base URL `https://api.xero.com/api.xro/2.0` |
| Identity service | `https://identity.xero.com` (token / revocation endpoints) |
| Spec version | Xero's official OpenAPI spec `xero_accounting.yaml` **v19.0.0** |
| Official SDK | `xero-python` **15.2.0** (released 2026-09-04). Everything below is described in HTTP terms and does not depend on any SDK abstraction |
| Platform policy | Granular scopes and the new pricing tiers took effect **2026-03-02**. This document was checked on **2026-09-24** |
| Not covered | No real Xero organisation was connected and no sandbox was run. The conclusions below come from checking the official documentation item by item |

**One inconsistency found while checking, stated up front**: the official OpenAPI spec v19.0.0
still lists **only broad scopes** (`accounting.transactions` / `accounting.transactions.read`)
under `security` for `/Invoices`, and **not a single granular scope appears anywhere in the
spec**. Yet an app created after 2026-03-02 can only request granular scopes. Therefore:
**do not infer the scopes you actually need from the spec's `security` field** — use the Scopes
page and the dev blog's mapping table. Generating a client automatically from that spec runs
straight into this.

---

## C1 — Connection verification

Before reading any invoice, four steps prove "OAuth works and the right tenant was selected".

| # | Call | Passing **proves** | Failure points at |
| - | ---------------------------------------------------------------------------------- | ------------------------------------- | ------------------------------------------------ |
| 1 | `POST https://identity.xero.com/connect/token`, `grant_type=refresh_token`, Basic auth | The refresh token is still valid and client_id/secret are correct | `invalid_grant` → the user must re-authorise; `invalid_client` → wrong credentials |
| 2 | `GET https://api.xero.com/connections` with `Authorization: Bearer <access_token>` | The access token works; returns **every** connection this user has authorised | 401 → token invalid or expired |
| 3 | Match the target organisation by **`tenantId`** in the returned array | The target organisation really **is inside this authorisation's scope** | No such `tenantId` in the array → not connected, or already disconnected; stop immediately |
| 4 | `GET https://api.xero.com/api.xro/2.0/Organisation` with `xero-tenant-id` | The tenant header is accepted, org-level scopes are sufficient, and the tenant **is currently usable** | 403 → see C2 |

**Why step 4 cannot be skipped.** Steps 2 and 3 only prove that "a connection record exists";
they do not prove that "this token may right now read business data for this tenant". The
official documentation lumps "the user revoked access", "the user's permissions changed" and
"the tenant became invalid (organisation deleted, **free trial ended**, demo org reset)" all
under 403 — and in all of those cases `/connections` may still return that tenant. Step 4
flushes them out early with one lightweight business read, at a cost of one call.

### Details that must be got exactly right

- **Match on `tenantId`, not `tenantName`.** In the official examples the `tenantName` of a
  `PRACTICEMANAGER` tenant is `null`.
- **`tenantType` must be `ORGANISATION`.** A user may also have authorised Practice Manager
  tenants, which are a different API. Xero states plainly: **a single authorisation can only
  request scopes for one tenant type**, and mixing them fails outright.
- **Store `authEventId`.** The documentation says "the `authEventId` of the last-connected
  tenant equals the `authentication_event_id` decoded from the access token" — that is the only
  way to answer "which authorisation produced the token I am holding?" `GET /connections` also
  takes an optional `authEventId` query parameter for filtering.
- **`createdDateUtc != updatedDateUtc`** means the user once disconnected and reconnected that
  organisation.
- The `id` returned by `/connections` is a **connectionId**, which differs from `tenantId`.
  Disconnecting a single organisation requires `DELETE /connections/{connectionId}` (passing
  `tenantId` fails); it returns 204 on success.

### Observability checkpoints

Model connection health as four **non-collapsible** terminal states, rather than a vague
"synchronisation failed":

| State | Trigger | Handling |
| ----------------- | -------------------------------- | ------------- |
| `ok` | All four steps pass | Sync normally |
| `needs_reauth` | Token endpoint returns `invalid_grant` | Tell the user to re-authorise |
| `not_connected` | `tenantId` absent from the `/connections` array | Mark disconnected locally; do not retry |
| `tenant_unusable` | Step 4 returns 403 | See the 403 branch of C2 |

---

## C2 — Failure diagnosis

Scenario: `/connections` succeeds, but `/Invoices` returns 401, 403 and 404 in different
environments.

**Prerequisite: on Xero these three codes are not a simple ladder of
authentication → authorisation → not found.** The documentation assigns both "token valid but
tenant unusable" and "connection revoked by the user" to **403**; and an invalid token sometimes
manifests as **400 `invalid_grant` (from the token endpoint)** rather than 401. So locate which
layer failed first, then eliminate within that layer.

### Layer 0: which endpoint failed

- **The token endpoint returns 400 `invalid_grant`** → nothing to do with 401/403. The
  documented causes: the authorisation code is wrong, expired, or already used; or the
  `grant_type` is wrong. **The only fix is to have the user re-authorise**; retrying is useless.
- **`GET /connections` itself fails** → the problem is in the token or the client configuration,
  not the tenant.
- **Only `/Invoices` fails** → continue into the tree below.

### 401 Unauthorized

1. Check that the `Authorization` header is present, that it carries the `Bearer ` prefix, and
   that the token has not passed its **30-minute** lifetime.
2. **Separate "token problem" from "scope problem" — both show up as 401.** The documented
   wording for insufficient scope is: if the app **does not have the correct scopes set** when
   it calls an endpoint, Xero returns **401 Unauthorized** (see the official Payroll API
   integration guide; the Accounting API behaves the same). So a 401 must not be treated
   automatically as "the token expired". Where to look:
   - Which scope the endpoint needs — look it up in the Scopes page mapping table, **not** in
     the OpenAPI spec's `security` field (it still lists only broad scopes; see section 0).
   - After the 2026-03-02 granular-scope change, **scopes do not propagate to existing tokens
     automatically**: the authorisation link must be updated and every already-connected user
     must re-authorise. There is no silent migration path.
   - An app created after 2026-03-02 has **no** broad scope available; calling any endpoint with
     a broad scope fails.
   Some third-party integration write-ups say this error carries an `insufficient_scope` marker.
   **The official Scopes page does not give that exact field name, so it should be confirmed
   against a sandbox before relying on it.** Whatever the field name turns out to be, the
   judgement is the same: **401 + "this user really did authorise the target organisation" +
   "the token is not expired" means suspect the scope first, not the token.**

### 403 Forbidden

Read the response body's `detail` first — one word separates the causes. The documented shape:

```json
{ "title": "Forbidden", "status": 403, "detail": "AuthenticationUnsuccessful", "instance": "..." }
```

Seeing `AuthenticationUnsuccessful` → three documented causes, eliminated one by one:

1. **The user revoked the connection inside your app** (disconnected it under Xero's
   Settings → Connected Apps).
2. **The authorising user's permissions changed**: removed from the organisation, or a role
   change that no longer permits authorising API connections.
3. **The tenant is no longer valid**: the organisation was deleted, a **free trial ended**, or a
   demo organisation was reset.

Three further 403 branches:

- **The body is HTML and contains `Access Denied`** → not a permissions problem but a **TLS
  version below 1.2**. Xero states plainly: OAuth 2.0 requires TLS 1.2+, and lower versions
  return 403 with an HTML fragment. This is the easiest one to misread as "insufficient
  permissions", because the body format alone distinguishes it (HTML vs JSON).
- **Premium endpoints** (such as `Journals`) are refused on lower tiers → check against the
  pricing tiers.
- An expired organisation subscription can also produce 403. The `Class` field on
  `/Organisation` lets you spot Trial / Demo Company **ahead of time**, instead of waiting for
  the 403.

### 404 Not Found

1. **Check the base URL**: whether `api.xero.com/api.xro/2.0` has been mixed with another
   environment. Mixing test and prod base URLs is a classic cause.
2. **Check whether the tenant context has been crossed**: using organisation A's
   `xero-tenant-id` (valid for the current token, so no 403) to fetch an identifier belonging to
   organisation B — that resource does not exist in A, so it surfaces as **404 rather than
   403**. A 404 therefore does **not** mean the configuration is wrong; it can also be a crossed
   tenant context, which is the more serious problem.
3. Check the resource identifier itself (is the InvoiceID GUID complete, does it come from
   another environment).

### The principle behind this ordering

**First see which layer the status code lands in, then order the checks within that layer by
"most likely and cheapest to rule out".**

- 401 → verify the token first (its 30-minute lifetime is the most common cause), then the
  scope.
- 403 → read the `detail` field first (one word separates revocation / permission change /
  tenant invalidity), then TLS (it shows as HTML, unmistakable next to a JSON error body).
- 404 → check the base-URL configuration first, then the tenant context, then the resource
  identifier.

---

## C3 — Incremental synchronisation

Goal: resumable, safely replayable, and not an infinite loop on a large organisation.

### Cursor key: `(app_id, tenant_id)`

The documentation notes that "several users can connect your app to the same organisation, but
only one connection counts towards the connection count". So using `connection_id` as the cursor
key would **synchronise the same organisation once per user**; `tenant_id` is what guarantees
one organisation has exactly one cursor and one worker advancing it at a time.

### Main loop

```pseudo
window_start = cursor.last_success_at        # the water level confirmed successful
overlap      = 5 minutes                     # a deliberate step back, absorbing second-level
                                             # precision and write-visibility skew
since        = window_start - overlap

page, max_modified, rows = 1, window_start, []
while True:
    resp = GET /Invoices
             headers: Authorization: Bearer <token>
                      xero-tenant-id: <tenant_id>
                      If-Modified-Since: <since, UTC, second precision>
             query:   page=page, pageSize=100

    if   resp.status == 429:          backoff_and_retry()            # see C4
    elif resp.status >= 500:          retry_within_budget()
    elif resp.status in (401, 403):   mark_connection_broken()       # see C2, never retry
    elif resp.status == 404:          alert_tenant_context_mismatch()# see C2

    rows += resp.Invoices
    max_modified = max(max_modified, max of each row's UpdatedDateUTC)

    if resp.pagination.page >= resp.pagination.pageCount: break
    page += 1

# the water level advances only when an entire pass succeeded
upsert(rows)                                 # idempotency key = (tenant_id, InvoiceID)
cursor.last_success_at = max_modified        # from the data's UpdatedDateUTC, not now()
cursor.save_atomic()                         # committed in the same transaction as upsert
```

### Six points

1. **Pagination**: `?page=N`. Xero specifies that **pageSize defaults to 100, is capped at 1000
   and floors at 1**; out-of-range values are **snapped to the nearest supported value**
   (`pageSize=5000` returns 1000). So **do not assume "fewer rows than pageSize means the last
   page"**. Use `pagination.page / pageCount / itemCount` from the body — that is the only
   reliable stop signal.
2. **Change window**: `If-Modified-Since` is an **HTTP header**, not a query parameter; a UTC
   timestamp with **second precision**. Xero recommends it for every endpoint returning large
   result sets.
3. **Take the water level from the data's maximum `UpdatedDateUTC`, not from `now()`.** Using
   `now()` **permanently skips** records modified while this very call was in flight (their
   `UpdatedDateUTC` is later than the timestamp used for the query). Using the data's own
   maximum timestamp makes the next run resume from wherever the last one reached.
4. **Overlap window**: query again from a water level stepped back by a fixed `overlap` (say 5
   minutes), because timestamps have second precision and server-side writes and visibility can
   drift slightly. The cost is a few duplicate reads, absorbed by point 5.
5. **Duplicates**: use `(tenant_id, InvoiceID)` as the upsert idempotency key. A failure on any
   page **does not advance the water level**; the next run replays from the same water level and
   already-processed rows are absorbed idempotently. **The read path is idempotent, so replay is
   free** — that is the premise which lets the whole design say "skip fine-grained per-page
   compensation and just redo the pass".
6. **Partial failure**: a Xero response can report errors for **individual elements under HTTP
   200** — every object carries `StatusAttributeString` (`OK` / `ERROR` / `WARNING`) and
   `ValidationErrors[].Message`. Therefore:
   - an HTTP status code alone does not prove that the whole batch succeeded;
   - check element by element and process only the `ERROR` ones; do not replay the entire batch
     because one element failed (even though it is idempotent, it still burns quota for
     nothing).

### The window blind spot that must be stated (or data is lost silently)

Xero states plainly that `If-Modified-Since` is based on `UpdatedDateUTC`, and **some changes do
not update that field**:

- certain field changes on part-paid transactions (such as `DueDate`, `SentToContact`), because
  they do not produce a journal;
- Contact fields derived elsewhere (`Balances`, `IsSupplier`, `IsCustomer`);
- after merging two contacts, the resulting contact's `UpdatedDateUTC` does not change.

**Conclusion: incremental sync cannot be the sole source of truth.** A full reconciliation must
run at a lower frequency (daily or weekly) to compensate for these blind spots. That is a
mandatory part of the design, not an optional extra.

### Multi-tenant isolation

Tokens, `tenant_id` and the cursor are all stored per connection; a worker picks up a task and
carries its `tenant_id`, **using the same tenant header throughout**. A worker that processes
several tenants serially while reusing one cursor variable is the easiest mistake to make in
this scenario. The concurrency cap must also be computed **per tenant** (see C4), not as one
global number.

---

## C4 — Rate limits

What a worker should do after receiving HTTP 429.

### Read the response headers first — they are the only authoritative source

| Header | Meaning |
| ------------------------- | -------------------------- |
| `Retry-After` | Seconds still to wait |
| `X-Rate-Limit-Problem` | Which limit was hit, e.g. `minute` / `day` |
| `X-MinLimit-Remaining` | Remaining for this tenant this minute |
| `X-DayLimit-Remaining` | Remaining for this tenant in the current 24 hours |
| `X-AppMinLimit-Remaining` | Remaining this minute across all tenants, for the whole app |

### Current limits (official values)

| Dimension | Limit | Scope |
| ------ | ----------------------------------- | --------- |
| Concurrency | **5** requests in flight | Per tenant, per app |
| Minute | **60** | Per tenant, per app |
| Day | **1,000 (Starter) / 5,000 (Core and above)** | Per tenant, per app |
| App-minute | **10,000** | Across all tenants |

The windows are **fixed, and each tenant resets at a different moment**, so computing "how much
is left this minute" locally is unreliable.

The three easiest mistakes:

1. **`Retry-After` is a number of seconds, not an HTTP date.** The documented example is
   `Retry-After: "24"`. Still accept HTTP-date when parsing (it is a legal value), but do not
   assume it is always a date.
2. **A concurrency-limit 429 may carry no `Retry-After`.** The documentation's wording is that
   if you exceed the **minute or day** limit you **also** get a `Retry-After` header.
   Conversely: a 429 without that header is itself the signal that the **concurrency limit** was
   hit. Do not retry immediately with a zero wait.
3. **Do not retry within the same pass when the day limit is hit.** The window is 24 hours and
   `Retry-After` may be thousands of seconds. The right move is to reschedule the task for the
   next window, not to park a worker sleeping and holding resources.

### Backoff and jitter

```pseudo
def call_with_retry(req, tenant):
    attempt = 0
    while True:
        resp = send(req)

        if resp.status == 429 or resp.status >= 500:
            attempt += 1
            if attempt > budget(tenant):                 # retry budget
                requeue(req, at=schedule_next_window(tenant))
                raise RetryBudgetExhausted
        elif resp.status in (400, 401, 403, 404, 422):   # do not retry, see the table below
            raise NonRetryable(resp)
        else:
            return resp

        retry_after = parse_retry_after(resp.headers)    # seconds or HTTP-date
        if retry_after is None:                          # concurrency limit: no header given
            base = min(2 ** attempt, 60)
        else:
            base = retry_after
        # jitter: wait 50%-100% of base, spreading out workers' retry moments
        sleep(base * (0.5 + random() * 0.5))
```

- **Use jitter, and do not wait exactly `Retry-After`.** When several workers are 429ed at the
  same moment and all wait exactly `Retry-After`, they all hit the line together again. Waiting
  `[0.5, 1.0] × base` keeps the lower bound on pacing while de-synchronising the moments.
- **Fall back to exponential backoff when there is no `Retry-After`** (capped at 60 seconds) —
  the typical concurrency-limit case.

### Concurrency caps

- Set per-tenant concurrency to **3–4**, not 5 — leaving headroom for token refresh and
  connection health checks.
- There must also be an app-level governor: the total must satisfy "requests per minute across
  all tenants < 10,000".
- Use a **per-tenant** semaphore or token bucket, **not one global connection pool**; otherwise
  one unusually busy tenant eats the other tenants' quota, even though the limits are isolated
  per tenant in the first place.

### Retry budget and task scheduling

- Each sync task carries a retry budget (say 10 attempts / 15 minutes); when it is exhausted the
  task is requeued and marked "incomplete" — **no unbounded retrying**.
- N consecutive failed passes → circuit-break that tenant's sync and alert (see C6).
- **Stagger the schedule**: hash on `tenant_id` to spread each tenant's sync moment across
  different minutes of the day, so every tenant does not start on the hour together.
- **Do not wait for a 429 to slow down**: read `X-DayLimit-Remaining` on every response and
  proactively defer non-critical work when it drops below a threshold.

### Errors that must not be retried

| Status | Cause | Correct handling |
| --- | -------------------------------------------- | ---------------------------- |
| 400 | Malformed request or parameters; or `invalid_grant` from the token endpoint | Fix the code / have the user re-authorise |
| 401 | Invalid or expired token; or insufficient scope (`insufficient_scope`) | Refresh the token, or re-authorise |
| 403 | Connection revoked, tenant unusable, subscription expired, TLS < 1.2 | Mark the connection broken and notify the user (see C2) |
| 404 | The resource does not exist, or the tenant context is crossed | Fix the configuration or the data; do not retry |
| 422 | Semantic validation failure (illegal field combination, etc.) | Fix the data; parse `ValidationErrors` element by element |

**Only 429, 5xx and network-level timeouts/connection resets are worth retrying.** Of those, 5xx
needs more care: **read** requests may be retried freely; **write** requests must carry an
idempotency key (see C5), otherwise a retry is just manufacturing duplicate data.

---

## C5 — Data integrity

Creating an invoice from an internal order can be retried after a timeout. How do you prevent
duplicate invoices, and how do you handle "the request succeeded but the response was lost"?

### Layer 1: Xero's own idempotency key

Xero's write endpoints support the **`Idempotency-Key` request header** (defined in the official
OpenAPI spec, **128 characters max**):

> This allows you to safely retry requests without the risk of duplicate processing. 128 character max.

The key must be **client-generated, stable and derivable**:

```
idempotency_key = sha256(f"{internal_order_id}:{sync_scope}")[:32]
```

The critical part: **it must be persisted on the order row**. Generating a fresh random UUID on
every retry means having no idempotency key at all — the most common mistake on this question.

### Layer 2: an external business key

- Write the internal order number into the Xero invoice's **`Reference`** field (the dedicated
  external reference), as the basis for reconciliation.
- On **`InvoiceNumber`**: Xero recommends **omitting it** and letting Xero number automatically
  (`INV-001`, `INV-002`, …). If the business genuinely requires its own numbering, make it
  globally unique, and **do not let a changing quantity such as the retry count participate in
  the number**.
- The two can be used together, but **reconciliation must always use the same field** — not
  `Reference` in one place and `InvoiceNumber` in another.

### Layer 3: the order of operations after a timeout — reconcile first, then decide whether to retry

This is the core of the question. Even with an idempotency key, blind retrying is wrong: the
key's guarantee depends on whether Xero has recorded that key, while an active reconciliation
additionally covers "the request never arrived at all".

```pseudo
def ensure_invoice(order):
    if order.xero_invoice_id:                      # already known to have succeeded
        return order.xero_invoice_id

    # 1) look first: reconcile requests that were sent but whose outcome is unknown
    existing = GET /Invoices?InvoiceNumbers={order.expected_number}
    # or an OData-style where filter on the external reference:
    #   GET /Invoices?where=Reference=="ORDER-123"
    if existing:
        order.xero_invoice_id = existing[0].InvoiceID
        return order.xero_invoice_id               # it did succeed; the response was lost

    # 2) not found -> send again, reusing the same idempotency key
    resp = POST /Invoices
             headers: Idempotency-Key: order.invoice_idempotency_key
             body:    Reference = order.internal_order_id
    check_each_element(resp)                       # HTTP 200 can still contain ERROR elements
    order.xero_invoice_id = resp.Invoices[0].InvoiceID
```

Key points:

- **"Not found" does not quite mean "did not succeed".** With read-after-write visibility lag, a
  query may miss a record that was just written. The idempotency key and the reconciliation
  together are what is actually robust: reconciliation covers the ordinary case, the idempotency
  key covers "the query found nothing but it exists anyway".
- **Reconcile with a filtered query, not by pulling whole pages and comparing locally.**
  `GET /Invoices?InvoiceNumbers=...` is a documented filter, and `where` can filter on
  `Reference`. Pulling whole pages is both slow and wasteful of the daily quota.
- **`If-Modified-Since` cannot be used here**: it filters on `UpdatedDateUTC`, while the question
  is whether an invoice with a given external key exists — unrelated to modification time.

### Layer 4: partial success in batch creates

- One POST may carry several invoices (Xero recommends about **no more than 50 elements**, with
  a body under **3.5MB**).
- The HTTP status may be **200** while each element carries its own `StatusAttributeString`
  (`OK` / `ERROR` / `WARNING`) and `ValidationErrors[].Message`.
- → **Decide element by element and retry only the `ERROR` ones**; do not resend the whole batch
  because one element failed.

### Layer 5: the local state machine

The invoice-sync state on an order needs at least: `pending` → `request_sent` →
`confirmed` / `failed`.

**Entering `confirmed` is allowed only after an `InvoiceID` is in hand.** On timeout, **stay in
`request_sent`** and let a separate reconciliation task scan these "dangling" records
periodically — rather than having the failed worker retry immediately. That way the records are
still covered even if the worker process crashes.

---

## C6 — Observability and security

### Logging

One structured log line per API call:

| Field | Meaning |
| -------------------------------------- | ------------------------------ |
| `correlation_id` | The correlation ID from the response (see below) |
| `tenant_id` | Which organisation |
| `endpoint` / `method` | e.g. `GET /Invoices` |
| `status` / `duration_ms` | Status code and duration |
| `attempt` | Which attempt this was |
| `rate_limit_problem` | `X-Rate-Limit-Problem` when a limit is hit |
| `remaining_minute` / `remaining_day` | Remaining quota, for trend analysis |
| `internal_order_id` / `xero_entity_id` | Ties the call to the internal business entity and the Xero object |
| `auth_event_id` | Answers "which authorisation produced this token" |

**One practical detail about the correlation ID**: the official Troubleshooting page's prose says
`X-Correlation-Id`, while the sample response headers and the rate-limits page examples show
`Xero-Correlation-Id`. **Handle both names** (HTTP header names are case-insensitive, so look
them up case-insensitively). This ID is the only evidence for locating a **single call** when
raising a Xero support ticket, so it must reach logs or the database — not stay only in process
output.

### Metrics

- **Sync success rate**, broken down by tenant and by endpoint.
- **429 count and share**, classified by the value of `X-Rate-Limit-Problem` — minute / day /
  concurrency are handled completely differently, so collapsing them into one number destroys
  its usefulness.
- **Remaining quota**: min / median of `X-DayLimit-Remaining`. That is the only basis for
  **proactively slowing down**.
- **Queue depth** and task wait time.
- **Water-level lag** = now − `cursor.last_success_at`, as a distribution per tenant rather than
  just an average.
- **Count of dangling `request_sent` orders** (C5 layer 5) — this metric maps directly onto the
  risk of duplicate invoices.
- Token refresh failure rate.

### Alerts

- One tenant failing N consecutive passes.
- **Stalled water level**: not advancing beyond the expected period. Judging by "consecutive
  successful passes" is more reliable than judging by time, because it separates "there really
  were no changes" from "the task is stuck".
- **Order-of-magnitude jumps**: the number of rows fetched in one pass deviating sharply from the
  historical baseline — either the business changed, or the water level was reset by mistake and
  a full re-pull is happening.
- 429 share above threshold, day quota below threshold.
- A rising count of connections in `needs_reauth` / 403 states.

### What must never be logged

| Never log | Why |
| --------------------------------------- | -------------------------- |
| access token / refresh token / id_token | They can be used to impersonate the user against the API |
| client secret, Basic auth header contents | App identity credentials |
| The `Authorization` request header | Contains a token |
| Full invoice / contact response bodies | Contain customer personal data, bank account numbers, etc.; debugging needs IDs and status codes only |
| Personal data in request bodies (contact name, address, tax number) | As above; if it truly must be logged, redact first |
| Request and response bodies of `/connect/token` | Contain tokens |

**In practice, log with an allow-list**: record only the explicitly listed fields, rather than
"log everything and strip sensitive fields with filter rules". The latter is one missing rule
away from a credential leak.

### Storing and rotating secrets and tokens

**Storage**

- **Encrypt refresh tokens before persisting**: application-level encryption (e.g. AES-GCM) with
  the key held in a KMS / key-management service; database permissions isolated per tenant.
- Compute and store `refresh_token_expires_at = last refresh time + 60 days` locally. Xero
  states plainly that it **does not provide** an expiry for refresh tokens, so you must derive it
  yourself.
- Key rows by `(app, tenant_id)`, storing `connection_id` (for disconnecting a single
  organisation) and `auth_event_id` (for debugging) alongside.
- Never in version control, never in client code, never in logs or error reporting.

**Rotation — the easiest trap in a Xero integration**

- Every refresh returns **a new access token and a new refresh token, and the old refresh token
  becomes invalid immediately**.
- Getting the new token and replacing the stored one must be **one atomic operation**. If the
  process crashes before saving, all you hold is an already-invalid old token.
- **Recovery window**: Xero states that if no refresh response was received, the old refresh
  token can be retried within **30 minutes**; past 30 minutes it is dead and the user must
  re-authorise.
- Hence two things are mandatory:
  1. **Refresh must be single-flight** (only one refresh in flight per connection at a time).
     Two workers refreshing concurrently means one of the new tokens is overwritten by the other
     and invalidated.
  2. **Log before replacing** (record intent and outcome), so that after a crash it is possible
     to tell which phase you are in.
- **An access token lives only 30 minutes.** Refresh on demand (2–3 minutes before expiry), not
  on every request.

---

## Appendix — the three correspondences with the scenario

The scenario stresses that "tokens, tenant IDs and sync cursors are stored per connected
organisation". Mapped onto the design:

| Stored object | Key | Points |
| --------- | ---------------------- | ------------------------------------------ |
| Token | `(app_id, tenant_id)` | Encrypted; single-flight refresh; atomic replacement; `refresh_token_expires_at` stored alongside |
| Tenant ID | Returned by `/connections` | **Never from user input**; every request carries `xero-tenant-id` |
| Sync cursor | `(app_id, tenant_id)` | Committed in the **same transaction** as the data processing; advanced by the data's `UpdatedDateUTC` |

The three collapse into one sentence: **one organisation = one set of credentials + one tenant
context + one water level, and only one worker may hold all three at a time.**

---

## References

Checked on **2026-09-24**.

**OAuth 2.0 and tenants**

- OAuth 2.0 authorisation flow / token lifecycle / refresh and revocation —  
  <https://developer.xero.com/documentation/oauth2/auth-flow>
- Xero Tenants (`/connections` response fields, disconnecting a single organisation) —  
  <https://developer.xero.com/documentation/guides/oauth2/tenants>
- Managing Tokens and Ids (which IDs to store, the token permission model) —  
  <https://developer.xero.com/documentation/best-practices/data-integrity/managing-tokens>
- OAuth 2.0 FAQ (refresh token 60 days, the 30-minute recovery window) —  
  <https://developer.xero.com/faq/oauth2>

**Troubleshooting**

- Troubleshooting (the three causes of a 403 `AuthenticationUnsuccessful`, `invalid_grant`,  
  `invalid_client`, the HTML 403 for TLS < 1.2, the correlation-ID response header) —  
  <https://developer.xero.com/documentation/guides/oauth2/troubleshooting>
- Identifying inactive connections (403 and `invalid_grant` as connection-invalidity signals) —  
  <https://developer.xero.com/documentation/best-practices/managing-connections/identifying-inactive-connections>
- Managing Connections (tenant types, how connections and limits are counted, multi-tenancy) —  
  <https://developer.xero.com/documentation/best-practices/managing-connections/connections>

**Pagination, incremental sync and error responses**

- Accounting API HTTP Requests and Responses (pagination defaults, bounds and snapping,  
  `If-Modified-Since` and its blind spots, per-element errors) —  
  <https://developer.xero.com/documentation/api/accounting/requests-and-responses>
- Accounting API Invoices (`If-Modified-Since`, `page` / `pageSize`, `summaryOnly`) —  
  <https://developer.xero.com/documentation/api/accounting/invoices>

**Rate limits**

- OAuth 2.0 API limits (concurrency 5 / minute 60 / day 1000-5000 / app-minute 10000) —  
  <https://developer.xero.com/documentation/guides/oauth2/limits>
- Rate Limits (sample response headers, when `Retry-After` applies, batching and pagination as  
  efficiency levers) —  
  <https://developer.xero.com/documentation/best-practices/api-call-efficiencies/rate-limits>
- Xero Developer Pricing and Policies (tiers and per-tier daily limits) —  
  <https://developer.xero.com/pricing>

**Versions and specs**

- Xero OpenAPI spec repository (`xero_accounting.yaml` v19.0.0, the `Idempotency-Key` header  
  definition) —  
  <https://github.com/XeroAPI/Xero-OpenAPI>
- Official Python SDK (`xero-python` 15.2.0) —  
  <https://github.com/XeroAPI/xero-python>
- Upcoming changes to Xero Accounting API scopes (the timeline for broad scopes being replaced  
  by granular scopes from 2026-03-02) —  
  <https://devblog.xero.com/upcoming-changes-to-xero-accounting-api-scopes-705c5a9621a0>
- Insider tips for better Xero integrations (recommendation to omit `InvoiceNumber` and let Xero  
  number invoices; the note that `UpdatedDateUTC` does not update for certain changes) —  
  <https://devblog.xero.com/insider-tips-for-better-xero-integrations-351f3d421ef0>
