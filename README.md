# skill-invest-review

A reusable, read-only skill for reviewing Korean, pension and U.S. investment
holdings with dated market evidence and conditional action plans.

This repository contains generic instructions, a Toss-specific market-data
adapter and offline tests. It does not contain a personal portfolio, credentials
or a trading bot. It never places, changes or cancels orders.

## What it does

- Reviews ordinary Korean holdings and pension holdings separately.
- Routes research by exchange calendars, time zones and permitted sessions.
- Checks prices, investor share volumes, order books and daily candles.
- Separates provisional flow from prior dates and excludes today's daily bar.
- Guides account-specific cost, cash, risk and conditional buy/sell analysis.
- Uses documented public-source fallbacks when Toss access is unavailable.

The Python adapter collects evidence; it does not automatically calculate a full
portfolio report or decide trades. The agent follows [SKILL.md](SKILL.md) to
interpret that evidence with the user's private, verified holdings.

## Package contents

| File | Purpose |
| --- | --- |
| [SKILL.md](SKILL.md) | Agent workflow, safety constraints and output contract |
| [agents/openai.yaml](agents/openai.yaml) | Skill discovery and invocation metadata |
| [scripts/toss_openapi_check.py](scripts/toss_openapi_check.py) | Read-only Toss CLI |
| [tests/test_toss_openapi_check.py](tests/test_toss_openapi_check.py) | Synthetic, offline regression tests |
| [references/data-quality.md](references/data-quality.md) | Data interpretation and validation rules |
| [references/source-fallback.md](references/source-fallback.md) | Alternative sources and their limits |
| [SECURITY.md](SECURITY.md) | Privacy rules and the public file allowlist |
| [.gitignore](.gitignore), [.gitattributes](.gitattributes) | Git tracking and archive exclusions |

## Setup and offline checks

Requirements: Python 3.10 or newer and an available IANA time-zone database.
The bundled adapter and tests use Python's standard library. macOS Keychain is
optional; environment credentials can be used without it.

Install the complete package with your agent's supported skill-installation
workflow, not just SKILL.md. Keep the instructions, references, scripts and tests
together. Installation must not copy personal data or filled-in configuration.

From this repository's root, run these credential-free checks:

```bash
python3 scripts/toss_openapi_check.py --help
python3 -m py_compile scripts/toss_openapi_check.py tests/test_toss_openapi_check.py
python3 -m unittest discover -s tests -v
```

After installation, an example request is:

```text
Use $skill-invest-review to review my verified holdings. Separate ordinary
Korean and pension accounts, respect the allowed market sessions, and provide
evidence-backed conditions rather than guaranteed price predictions.
```

## Private runtime configuration

Keep portfolio ledgers, screenshots, reports and backups in a separate private
workspace. The expected ledger roles and precedence are documented in
[SKILL.md](SKILL.md#locate-the-workspace); no personal ledger is required to run
the offline tests.

For authenticated Toss reads, configure TOSS_INVEST_CLIENT_ID and
TOSS_INVEST_CLIENT_SECRET through the local environment or macOS Keychain.
The adapter can also load a local .env file from the resolved workspace. Never
paste credentials into a prompt or commit that file.

HCSCAT_INVEST_ROOT is an optional runtime workspace override. Its directory must
contain scripts/toss_openapi_check.py. Without it, the adapter prefers the current
directory when it contains that script and a data directory; otherwise it uses
its own package root. It does not search unrelated directories. Supply device
paths at runtime, never in shared source or documentation.

Optional configuration keys are TOSS_INVEST_BASE_URL (an HTTPS origin) and
TOSS_INVEST_KEYCHAIN_SERVICE. Changing the base URL alone does not make a
different provider compatible.

## Read-only commands

<!-- Keep command names and arguments aligned with the adapter's parse_args function. -->

Run authenticated commands sequentially: issuing another Toss token invalidates
the previous one. Replace SYMBOL with one symbol and SYMBOLS or KR_SYMBOLS with
a comma-separated list appropriate to that market.

```bash
python3 scripts/toss_openapi_check.py diagnose
python3 scripts/toss_openapi_check.py market
python3 scripts/toss_openapi_check.py price SYMBOLS
python3 scripts/toss_openapi_check.py stock SYMBOLS
python3 scripts/toss_openapi_check.py flow KR_SYMBOLS --days 5
python3 scripts/toss_openapi_check.py orderbook SYMBOL
python3 scripts/toss_openapi_check.py candles SYMBOL --count 30
```

- Korean research uses the permitted 08:00-20:00 KST trading-day window, but
  instrument eligibility, suspensions and NXT support determine actual tradability.
- Direct U.S. research is restricted to regular exchange sessions, normally
  09:30-16:00 America/New_York, including holiday and early-close checks.
- Price, reference, order-book and candle commands fail closed outside permitted
  sessions. A mixed-market batch is rejected if either market is closed.
- KR flow can be read as historical/provisional evidence outside trading hours;
  this does not establish a current executable price. Calendar and general FX
  checks are also permitted outside symbol-research windows.

See [data-quality.md](references/data-quality.md) for output semantics. In
particular, the flow command's available prior dates are not automatically a
verified consecutive-session series, and best quotes do not guarantee a fill.

## Other APIs and limitations

The adapter targets Toss Securities / Toss Invest OpenAPI. Another broker or data
provider requires a separately adapted and validated authentication flow,
endpoints, response mapping, calendars, rate limits and investor-flow definitions.
Use the [fallback guide](references/source-fallback.md) when no compatible adapter
exists; do not substitute inferred values for missing data.

Offline tests verify local behavior, not every live market, device or provider.
This package does not include the private portfolio/SQLite collection benchmark.
Analysis remains conditional and may be limited by stale holdings, delayed data,
fees, taxes, currency changes and corporate actions.

## Maintenance and privacy

Keep important functions and safety decisions documented in concise English.
Update affected comments, examples, references and tests whenever behavior changes.
Synchronize approved installed copies from the canonical package.

Before sharing, inspect file contents, staged changes, outgoing history and actual
package contents against [SECURITY.md](SECURITY.md). Personal ledgers, credentials,
device paths and project AGENTS.md / AGENTS.override.md files are excluded.
Ignore rules do not protect already tracked files, and archive exclusions do not
control other packaging tools.
