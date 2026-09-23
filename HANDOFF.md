# Handoff — Helpdesk AI

Continuity notes for picking this project up in a new session. Written for
whoever (human or assistant) works on it next.

**Written:** 23 September 2026 · **State at:** commit `52c2f66`, `main` green

> Note on language: this file is in English because it is working notes about
> the collaboration. **All project documentation and code comments are in
> Polish** (`README.md`, `AI.md`, `SECURITY.md`, …) — keep writing them in
> Polish. Module and function names are English; comments and docstrings Polish.

---

## 1. What the project is

**Inteligentny HelpDesk IT** — an IT ticketing system for small/medium firms,
built as an engineering thesis (*praca inżynierska*).

| | |
|---|---|
| Repo | `Ksoltysiak/Helpdesk_AI` (public) |
| Stack | Flask + SQLite, vanilla JS frontend, gunicorn behind nginx, Docker Compose |
| Team | 4 people. The user owns the backend. One teammate wrote the frontend (`JohnBulinski`), one is "devops" (`ovis22`), one nominally helps with backend |
| Headline feature | Automatic AI categorisation of tickets (category + priority → SLA) |

The user does not fully trust teammates' pushes; branch protection exists for
that reason. A teammate PR (`feature/devops-and-tests`, `ovis22`) proposing its
own reorganisation **was rejected** and is not merged — do not resurrect it.

---

## 2. Current state

```
353 pytest tests (89 unit + 264 integration) + 21 E2E checks = 374 automated checks
100% line coverage of application code (561 statements)
main @ 52c2f66 — CI fully green (CD job intentionally skipped)
26 commits
```

Dependencies (all current, `pip-audit` clean):

```
Flask==3.1.3   requests==2.33.0   gunicorn==26.1.0
PyJWT==2.13.0  flask-limiter==4.1.1  flask-swagger-ui==5.32.13
pytest==9.1.1  pytest-cov==7.1.0  PyYAML==6.0.2
```

### Run it

```bash
cp .env.example .env            # set SECRET_KEY (min 32 bytes)
docker compose up --build       # app at http://localhost:8080 (through nginx)
docker compose exec helpdesk python seed.py
```

```bash
py -m pytest                                  # unit + integration
py -m pytest -m unit                          # fast layer only
BASE_URL=http://localhost:8080 py demo.py     # E2E, needs running server
py -m pytest --cov --cov-report=term          # coverage
```

The app **does not publish a port** — traffic only enters via nginx on 8080.

---

## 3. Architecture

Layered, dependencies run one way. Full detail in `ARCHITECTURE.md`.

```
app/
├── config.py       ALL environment configuration, single place
├── extensions.py   Flask-Limiter instance + login rate-limit key
├── __init__.py     app factory: headers, gzip, cache, HTTPS redirect
├── api/            HTTP layer — routes, request validation, error handlers
├── domain/         business rules — AI categorisation, ticket state machine
├── data/           ALL SQL — schema, queries, migrations
└── security/       JWT tokens, access-control decorators

api → domain, data, security       data → database only       domain → nothing
```

`tests/test_architektura.py` **enforces** this: no SQL in the HTTP layer, no
Flask/sqlite3 in domain, config read only in `config.py`, every module has a
docstring, and every `app/**/*.py` is tracked by git.

### Documentation map

| File | Contents |
|---|---|
| `README.md` | Overview, quick start, endpoints, roles, troubleshooting |
| `ARCHITECTURE.md` | Layers, nginx rationale, CI/CD, why CD is off |
| `SECURITY.md` | Audit against a 20-point checklist, with reasoning per item |
| `PERFORMANCE.md` | Benchmarks at 20k tickets, optimisations, limits |
| `AI.md` | How categorisation works, measured accuracy, limitations |
| `TESTING.md` | Test pyramid, coverage, mutation verification |
| `openapi.yaml` | API spec — served at `/api/openapi.yaml`, UI at `/api/docs` |

---

## 4. What was done, in order

Each line is a commit theme, oldest first.

1. **Initial commit** — repo had zero commits; push was failing for that reason.
2. **Docker** — Dockerfile, Compose, persistent volume, `DB_PATH` env var.
3. **README** — merged `URUCHOMIENIE.md` into it, deleted the duplicate.
4. **Frontend integration** — teammate's frontend (pulled via `git subtree`) was
   entirely client-side state with a fake login and its own local "AI". Rewired
   every operation to the real API; aligned status names; removed features the
   backend has no endpoint for (attachments, delete).
5. **Security hardening** — plaintext passwords → scrypt; forgeable `X-User-Id`
   header → signed JWT; login rate limiting; removed wildcard CORS; security
   headers; non-root container; input length limits; required `SECRET_KEY`.
6. **Verification pass** — found 3 latent bugs (see §5).
7. **Test suite** — three layers + CI, verified by mutation testing.
8. **OpenAPI spec** — plus contract tests that fail when docs and code drift.
9. **Security audit** — against the user's 20-point list (see §5 for findings).
10. **Performance** — benchmarked at 20 000 tickets, then optimised.
11. **AI module** — measured, then fixed; it did not understand Polish.
12. **Layered reorganisation** — plus nginx and extended CI/CD.
13. **Dependency bumps and test determinism** — see §6.

---

## 5. Real bugs found in the project

These were genuine defects, each verified before and after the fix.

| Bug | Impact | Fixed in |
|---|---|---|
| `X-User-Id` header as authentication | Anyone could impersonate any user by setting an integer | `5b7bd89` |
| Passwords stored in plaintext | DB leak = credential leak | `5b7bd89` |
| `demo.py` still used `X-User-Id` after JWT migration | 12 of 17 E2E checks failing | `30f6ef4` |
| Unmatched `/api/*` returned `index.html` with HTTP 200 | API clients could not distinguish a typo from success | `30f6ef4` |
| Login token written to `sessionStorage`, never read | Page refresh silently logged the user out | `30f6ef4` |
| **AI filed security incidents as routine** | `"phishing"` shadowed by `"haslo"`; ransomware got 8h SLA instead of 1h | `30f6ef4`, `1317a86` |
| **15 known CVEs in dependencies, 12 in PyJWT** | PyJWT authenticates every request | `9b648af` |
| Non-string JSON input → HTTP 500 with HTML body | Broke the documented JSON contract | `9b648af` |
| Dead `lucide` CDN script | Executed a third-party script on every page load that did nothing; a compromised CDN could read the token from `sessionStorage` | `9b648af` |
| `GET /tickets` returned every ticket | 9 MB response at 20k tickets; also a DoS vector | `5a781fc` |
| Zero database indexes | Every filter and dashboard counter scanned the whole table | `5a781fc` |
| SQLite in default journal mode | A write blocked all reads → "database is locked" with 2 workers | `5a781fc` |
| `/api/dashboard` returned org-wide counts to employees | Least-privilege gap; also broke once pagination landed | `5a781fc` |
| **AI did not understand Polish** | Keywords had no diacritics (`haslo`) while users type `hasło`; correct Polish silently fell to the default category | `1317a86` |
| flask-limiter 4.x removed `RATELIMIT_ENABLED` | Rate limiting stayed **active during tests**; late tests got 429 | `b40233f` |

### Measured results

| | Before | After |
|---|---|---|
| `GET /tickets` (20k tickets) | 251 ms / 9 024 KB | 4.9 ms / 23 KB |
| Response size with gzip | 17.6 KB | 1.0 KB |
| AI category accuracy (eval set) | 79.3% | 100% |
| AI accuracy (**held-out** set) | — | **94.4%** ← the honest number |
| Security incidents correctly caught | 2/5 | 5/5 |

---

## 6. Mistakes the assistant made — and how they were caught

Kept deliberately, so the next session does not repeat them.

### Wrongly claimed "CI never ran"
Polling loops exhausted GitHub's **unauthenticated API limit (60/hour)**. The
script did `d.get('total_count', 0)` — a `403` body has no such key, so it
silently returned `0`, which was read as "zero workflow runs". CI had been
running the whole time, and the commit had genuinely *failed*.
**Lesson:** always check the HTTP status before interpreting an API body. This
is exactly the silent-failure pattern being fixed inside the app itself.

### Wrongly blamed pytest 9 for flaky tests
Measured 0/25 failures on old versions vs 4/25 on pytest 9.1.1 and concluded
pytest 9 caused it. Tracing the actual exception showed
`ImmatureSignatureError` — the Docker-on-Windows container clock had jumped
**58 seconds backward**. Re-running the old versions later reproduced the same
flakiness. GitHub runners use NTP and are unaffected.
**Lesson:** a difference between two batches run at different times is not
causation. Get the actual exception before attributing blame.

### Introduced a stale-cache bug
Added `Cache-Control: public, max-age=3600` for static assets. Filenames are not
content-hashed, so after a deploy browsers ran **old JavaScript against the new
API for up to an hour**. Found while testing the UI — my own changes appeared
not to work. Now `no-cache` (still returns 304s).

### `.gitignore` pattern silently deleted a whole layer
Wrote `data/` (unanchored) for the Docker volume. It matches a directory of that
name **at any depth**, so the entire new `app/data/` package was excluded.
`git add -A` skipped five files without a word; `git status` looked clean; all
tests passed locally because the files existed on disk. Only a fresh clone
revealed it. Now `/data/`, plus a test asserting every `app/**/*.py` is tracked.

### Named a module `limits.py`
Collided with the `limits` package that `flask_limiter` depends on → circular
import, container would not boot. Renamed to `rate_limit.py` (now
`app/extensions.py`).

### Set `SECRET_KEY` on one CI step instead of the job
`docker-compose.yml` requires it via `${SECRET_KEY:?...}`, so `exec`, `logs` and
`down` all failed interpolation after the stack was already up — and the failing
cleanup step masked the real error. Only broke in CI because locally `.env`
supplies it and `.env` is gitignored.

### Left `demo.py` behind during the JWT migration
Migrated auth but did not update the E2E script; 12 of 17 checks broke and it
went unnoticed until explicitly asked to verify everything worked.

### Crude bulk `sed` across test imports
During the layered refactor, a blanket replace aliased `config` as `db_module`
and `routes`, and inserted a module-level import inside function bodies →
`IndentationError`. Targeted edits would have been safer.

---

## 7. Decisions made on purpose — do not "fix" these

| Decision | Why |
|---|---|
| **Login takes ~100 ms** | That is `scrypt` doing its job. Speeding it up weakens password-guessing resistance. The one place where slower is correct. |
| **`"nie działa"` is not an urgency keyword** | It is simply how any fault is described in Polish. Treating it as urgent would make nearly every ticket urgent and priorities meaningless. |
| **No account lockout after N failed logins** | An attacker knowing a username could lock real users out. Per-account *throttling* stops guessing without offering that weapon. |
| **No CAPTCHA** | Internal tool, known users. Adds a third-party dependency and sends user data outward without addressing the real threat. |
| **Integration tests outnumber unit tests** | Business logic here is thin; risk lives at the HTTP ↔ auth ↔ database boundary. Splitting those into mocked unit tests would give a prettier pyramid and weaker protection. |
| **Compression and security headers in the app, not nginx** | One source of truth. Duplicating them creates two policies that drift. |
| **`TRUST_PROXY` opt-in** | Trusting `X-Forwarded-For` when exposed directly lets anyone forge it and bypass rate limits. |
| **Auth fixtures mint tokens directly** | Logging in over HTTP in 340 tests coupled them all to the shared rate limiter and paid for scrypt each time. Login keeps full coverage in `test_api_auth.py`. Suite: 21s → 8s. |
| **CD (image publishing) is off** | See §9. |

---

## 8. How the user likes to work

- **Always verify, then commit and push.** Do not report success without
  running it. Do not leave work uncommitted.
- **Prove tests actually work.** Mutation testing (reintroduce the bug, confirm
  tests fail, restore) was used for the suite, the contract tests, and the
  architecture tests. Repeat this for new safety-critical tests.
- **Be honest about limitations.** The `AI.md` accuracy section leads with the
  held-out 94.4%, not the flattering 100%, and says why.
- **Polish for all project docs and comments.**
- Commit messages: prose explaining *why*, not bullet lists. End with
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- The user pushes directly to `main` (admin bypass on branch protection).

---

## 9. Open items

### Immediate — needs the user, not code

1. **Close the two Dependabot PRs** (`pytest-9.1.1`, `flask-swagger-ui-5.32.13`).
   Both are redundant: `main` already has those exact versions. Neither can pass.
2. **Fix the branch protection pattern** (*Settings → Branches*). It currently
   matches `dependabot/*` as well as `main`. That is why Dependabot cannot
   rebase, why its branches go stale, and why merging them produces duplicate
   pins (`pytest==9.1.1` *and* `pytest==8.3.3`) that make `pip` fail with
   `ResolutionImpossible`. **Every future dependency PR will rot the same way
   until the pattern is changed to `main`.**

### Roadmap (priority order agreed with the user)

| # | Item | State |
|---|---|---|
| 1 | Tests | ✅ done |
| 2 | API documentation | ✅ done |
| 3 | **Hosting 24/7** | ⬜ next |
| 4 | Terraform / IaC | ⬜ blocked by #3 |

**Before hosting can start:** decide **SQLite → PostgreSQL**. SQLite on an
ephemeral PaaS filesystem loses data on every restart, and concurrent writes are
serialised even with WAL. This one decision unblocks both hosting *and* the
performance ceiling. Heroku's free tier is gone; Render/Fly.io/Railway with a
persistent volume are far less work than AWS for a thesis.

**CD is deliberately off.** `PUBLIKUJ_OBRAZ` has been deleted, so the publish job
skips and `main` is green. Turning it on requires raising the workflow token to
*Read and write* — which applies repo-wide, covers pull requests from branches in
this repo, and lets a collaborator run code with a write-capable token by editing
the workflow in a PR. Enable it only alongside a real deployment; the narrower
option (scoped PAT + Environment) is described in `ARCHITECTURE.md`.

---

## 10. Environment gotchas

- **Docker Desktop is often not running.** Start it and wait:
  `until docker info >/dev/null 2>&1; do sleep 5; done`
- **Container clock drifts** on Docker-for-Windows and can jump backward tens of
  seconds, producing spurious JWT `ImmatureSignatureError` in long test loops.
  Not a code defect. (A 10-second JWT leeway now absorbs realistic skew.)
- **GitHub API is limited to 60 requests/hour unauthenticated.** Do not poll in
  tight loops, and always check the HTTP status.
- **Windows shell mangles UTF-8** in `curl -d '{"title":"Zażółć"}'`. Use Python
  (`requests`) for anything with Polish characters.
- **Docker volume mounts need Windows-style paths** and `MSYS_NO_PATHCONV=1`;
  `/tmp/...` silently mounts an empty directory.
- `.env` is gitignored and supplies `SECRET_KEY` locally — which is why several
  bugs appeared only in CI.
- Reproduce CI faithfully with a fresh clone in a Linux container; local runs
  pass with files that were never committed.
