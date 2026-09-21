---
name: skill-invest-review
description: Review Korean, pension, and U.S. holdings with read-only market-data checks, current-session routing, investor-flow evidence, and conditional buy or sell bands. Use for current-price checks, portfolio revaluation, stop-loss or partial-sale analysis, averaging-down decisions, and repeatable Toss workflows.
---

# Skill Invest Review

<!-- Maintainers: keep command examples and routing rules aligned with adapter tests. -->

Use this skill for repeatable, evidence-labeled portfolio reviews. It is a read-only analysis workflow: never place, modify, or cancel an order.

## Safety and Privacy

- Never print, copy, upload, commit, or embed `.env`, tokens, client secrets, account identifiers, personal screenshots, or private holdings in this skill.
- Read credentials only through the user's existing Keychain or local `.env` mechanism. Report safe diagnostics only.
- Never hard-code or persist a device username, absolute workspace path, home-directory path, account number, or other user-specific identifier in the skill, reports, logs, or examples.
- Treat prices and flows as time-bound. Include observation time, active market window, source, and freshness.
- Never invent foreign or institutional flows. If unavailable, write `미제공` and explain why.
- Separate facts, inferences, and conditional actions. A price band is not a guaranteed forecast.
- Treat project `AGENTS.md` and `AGENTS.override.md`, including nested copies, as local-only. Before external sharing, follow [SECURITY.md](SECURITY.md); a skill update is not permission to stage, commit or push.

## Personalization Boundary

Do not hard-code Samsung Electronics, any ticker, a user's concentration target, or a personal risk priority into the default workflow. Run single-name concentration or special risk analysis only when the user explicitly asks for it, such as `삼성전자 집중도 분석` or `특정 종목을 최우선 위험으로 평가`.

The default screen is position-agnostic: quantity, loss, portfolio weight, duplicated exposure, liquidity, thesis evidence, and risk thresholds are evaluated for every holding using the user's current canonical data.

## Locate the Workspace

Find the repository before reading data. Prefer the current working directory when it contains `scripts/toss_openapi_check.py` and the canonical `data/` files. Otherwise ask for a user-approved workspace or accept it through the runtime `HCSCAT_INVEST_ROOT` environment variable. Do not scan unrelated home directories. Read the workspace's local instructions before applying this workflow; stricter local market/privacy rules take precedence. Resolve inputs relative to that root, and never persist the supplied path in source, reports, logs or saved analysis state.

Skill installation must copy the complete generic package, including `references/`, `scripts/`, `tests/` and `SECURITY.md`, not just this entrypoint. It must not require a device path, username, account identifier, credential, or personal holding value. Device-specific values are supplied at runtime from the user's local workspace and are not part of the installed skill. Do not duplicate private ledgers into the installation.

Canonical inputs normally include:

- `data/kr_portfolio_current.json`: Korean cash-equity holdings and transaction history.
- `data/pension_portfolio_current.json`: pension holdings.
- `data/us/us_portfolio_current.json`: U.S. holdings when present.
- `data/cash_current.json`: cash ledger; verify its date before using it.
- `data/kr_revaluation_latest.json` and `data/us/us_revaluation_latest.json`: latest synthesis and snapshots.
- `data/kr_trade_recommendation_score_latest.json` and the U.S. equivalent: prior action rules.

Timestamped reviews, screenshot imports, and `*_before_*` files are evidence or archives, not automatic replacements. Never infer a completed trade from a plan; update holdings only from an explicit fill or a verified source of record.

For any revaluation or balance reconciliation, read [references/data-quality.md](references/data-quality.md). It defines account-specific cost/cash handling, snapshot reconciliation, flow validation, price evidence and action-budget checks. Inspect each input's actual schema rather than assuming all accounts use the same nesting.

## Current-Session Routing

Route by the user's holdings and the current time before querying prices. Do not run live revaluation outside the relevant market window by default.

### Korean and Pension Holdings

- Use the Korea route only on Korean trading days during the combined Korean trading window **08:00-20:00 KST**, covering the currently available NXT and KRX quote windows without making them separate report sections.
- Query the currently active executable quote returned by Toss or the fallback source. Preserve the source's session metadata internally, but present one `한국장 현재 세션` price basis.
- Pension holdings are routed through Korea when they are Korean-listed securities. Do not treat the pension account as a different market clock.
- The routing window is not a promise of order availability: check NXT eligibility, trading suspensions and the instrument's actual session. Keep Korean ordinary and pension results separate. Korean-listed U.S.-index ETFs remain Korean instruments; do not research their U.S. constituents outside the allowed U.S. window.

### U.S. Holdings

- Use the U.S. route only on U.S. trading days during the exchange-local **regular session 09:30-16:00 America/New_York**, shortened by an official early close. Do not run new U.S. price, news, disclosure, or flow research during pre-market or after-market hours. Any explicit off-hours request must first be reconciled with the user's local policy; it is not an automatic exception.
- Convert the current time with `America/New_York`; do not hard-code one Korean daylight-saving schedule.
- Present one `미국장 현재 세션` price basis. Do not create separate pre-market, regular-market, and after-market sections unless the user explicitly requests a session comparison.

### Outside the Window

Confirm exchange calendars, holidays and early closes, not just the weekday or clock. If closed or time/calendar verification fails, do not call the result “current.” Use previously stored local values only when useful, date them as historical, and state the next applicable window. Do not bypass the U.S. restriction with another provider or a newly fetched “closing price.” Exclude stale U.S. holdings from a claimed current total. Calendar and general FX checks remain allowed.

## Data Collection and Fallbacks

Use Toss Invest OpenAPI first when credentials and read-only endpoints are available. Read credentials at runtime from the user's existing Keychain or local `.env` under the resolved workspace root; never ask the user to paste a token into chat:

```bash
python3 scripts/toss_openapi_check.py diagnose
python3 scripts/toss_openapi_check.py market
python3 scripts/toss_openapi_check.py price SYMBOLS
python3 scripts/toss_openapi_check.py stock SYMBOLS
python3 scripts/toss_openapi_check.py flow KR_SYMBOLS --days 5
python3 scripts/toss_openapi_check.py orderbook SYMBOL
python3 scripts/toss_openapi_check.py candles SYMBOL --count 30
```

These paths are relative to the package root, or to a workspace containing the synchronized adapter. An installed copy can also be invoked by its resolved runtime location. `price`/`stock`/`orderbook`/`candles` fail closed outside the permitted session; `flow` is KR-only historical/provisional data and does not claim executable prices. Read [references/data-quality.md](references/data-quality.md) before interpreting these outputs.

Use one sequential read-only price call for each eligible market's complete symbol set. Do not issue parallel token requests: a new Toss token invalidates the previous token. The adapter checks the whole batch's calendars before querying any symbol; omit closed markets. Do not retry authentication or rate-limit failures in a tight loop. If Toss is unavailable, unauthorized, unsupported for a field, or unavailable to the user, read [references/source-fallback.md](references/source-fallback.md) and fall back in this order:

1. Official exchange or market-operator data.
2. Official company or ETF issuer disclosures.
3. Public market pages such as Naver Finance or another transparent broker/public quote source.
4. Reliable news or research for context, never as the sole source of a live price.

Record the fallback source, URL, timestamp, delay status, and missing fields. Do not imply that a public quote page provides investor flow unless it explicitly labels that data.

Before declaring a field unsupported, check the current official API specification and read-only endpoint. A missing CLI field is not proof of missing provider data.

## API Provider Boundary

This skill and `scripts/toss_openapi_check.py` are reference implementations for the Toss Securities / Toss Invest OpenAPI. They are not provider-neutral and are not drop-in compatible with another broker or market-data API.

When using another API, update and revalidate the local adapter for authentication, base URL, endpoint paths, request parameters, response-field mapping, market calendar and session rules, rate limits, account and holdings schemas, currencies, and investor-flow semantics. Keep provider-specific adapters and credentials outside this shared skill package. If no compatible adapter exists, use the documented public-source fallback and mark unavailable fields instead of guessing.

The public package includes `scripts/toss_openapi_check.py` as the minimal Toss read-only adapter used by the example commands. It can resolve a private workspace at runtime through `HCSCAT_INVEST_ROOT`; it does not bundle credentials or personal data. `market_collection_benchmark.py` is a local experiment that reads holdings and writes a SQLite output, so it is not required for skill installation or ordinary reviews and remains outside the public package.

## Investor-Flow Rules

- Prefer the latest completed-session foreign and institutional net-buy figures from a source that explicitly identifies the investor category.
- Keep same-day provisional data separate from prior-session totals; preserve `null` versus zero.
- Use the latest completed session and a recent multi-session window (default five when enough verified data exists). Validate arithmetic, duplicates and missing sessions. The CLI aggregates available prior dates, not a certified consecutive-session series; verify its coverage flags before labeling a five-session total.
- Report units, trading date, update time, direction and coverage. For Toss stock flow, the basis is KRX+NXT shares and registered foreigners, not index-level KRW trading value.
- Do not infer investor flow from total volume, price direction, order-book imbalance, or NXT quotes.
- For ETFs, distinguish ETF-unit flow from the underlying constituent flow.

## Revaluation Workflow

1. Reconcile holdings, verified total cost, account-specific cash, and explicit recent fills from canonical state. State the holdings date separately from the quote time.
2. Confirm the relevant market window and query current-session prices once.
3. Calculate market value, P/L, weight, liquidity context, and duplicated sector or instrument exposure.
4. Add the latest confirmed investor flow and distinguish it from current-day flow.
5. Review official disclosures first, then reliable market reporting. Separate catalysts from recurring earnings and cash-flow proof.
6. Run the default position-agnostic risk screen. Run special concentration or single-name priority analysis only if explicitly requested.
7. Produce evidence-backed conditional actions with account, trigger, quantity, estimated amount, applicable session, expiry and invalidation. Derive price bands from completed bars or an explicit risk budget; invalidate pre-event bands after relevant corporate actions. Check alternative triggers for double-counted shares or cash.
8. Critique the result: stale data, thin liquidity, one-day flow overinterpretation, tracking error, currency, fees, taxes, and uncertainty.
9. Save portfolio state/reports only in the user's private workspace. Validate JSON and never overwrite canonical holdings for a recommendation alone; keep personal financial data outside the shared package even though it is not an API secret.

## Output Contract

Use Korean unless the user requests another language:

1. Observation time, market route, and current-session basis.
2. Holdings table with quantity, current price, P/L, source, and freshness.
3. Investor-flow table with latest confirmed date and coverage limits.
4. Per-position assessment with evidence and critical counterpoint.
5. Additional-buy candidates and conditional price bands.
6. Evidence-backed risk-reduction candidates, or explicitly state that none is supported; do not force a sale recommendation.
7. Action timing and price bands at the bottom.
8. Data limitations and source links.

Use `확인불가`, `미제공`, or `지연` instead of blanks. Use explicit conditional actions, not guaranteed predictions. Quantify only with known holdings and that account's available funds. In HTML reports, set both foreground and background colors for inline code and token-like text; check mobile table overflow.

## Validation

From the public package root, run the self-contained checks (standard library only, Python 3.10+):

```bash
python3 -m py_compile scripts/toss_openapi_check.py tests/test_toss_openapi_check.py
python3 -m unittest discover -s tests -v
python3 scripts/toss_openapi_check.py --help
```

Validate each JSON file actually changed in the private workspace separately. The optional local benchmark and private `data/` files are not installation prerequisites. Confirm that the report uses a consistent price basis per valuation scope, every price/flow has a date and source, and no private data enters the public package. Before a live smoke test run `diagnose`, then one narrow read-only command during the permitted session. Reconcile verified fills before calculating weights or recommendations.

## Maintenance

Keep important Python functions and non-obvious safety branches documented with
short English docstrings or comments. Explain intent, constraints and failure
behavior rather than restating the code. When behavior changes, update affected
comments, reference contracts, examples and tests in the same change; remove stale
claims. Update the canonical package first, then synchronize approved runtime
copies without copying private data.
