---
name: hcscat-invest-review
description: Review Korean, pension, and U.S. holdings with read-only market-data checks, current-session routing, investor-flow evidence, and conditional buy or sell bands. Use for current-price checks, portfolio revaluation, stop-loss or partial-sale analysis, averaging-down decisions, and repeatable Toss workflows.
---

# HCSCAT Invest Review

Use this skill for repeatable, evidence-labeled portfolio reviews. It is a read-only analysis workflow: never place, modify, or cancel an order.

## Safety and Privacy

- Never print, copy, upload, commit, or embed `.env`, tokens, client secrets, account identifiers, personal screenshots, or private holdings in this skill.
- Read credentials only through the user's existing Keychain or local `.env` mechanism. Report safe diagnostics only.
- Never hard-code or persist a device username, absolute workspace path, home-directory path, account number, or other user-specific identifier in the skill, reports, logs, or examples.
- Treat prices and flows as time-bound. Include observation time, active market window, source, and freshness.
- Never invent foreign or institutional flows. If unavailable, write `미제공` and explain why.
- Separate facts, inferences, and conditional actions. A price band is not a guaranteed forecast.

## Personalization Boundary

Do not hard-code Samsung Electronics, any ticker, a user's concentration target, or a personal risk priority into the default workflow. Run single-name concentration or special risk analysis only when the user explicitly asks for it, such as `삼성전자 집중도 분석` or `특정 종목을 최우선 위험으로 평가`.

The default screen is position-agnostic: quantity, loss, portfolio weight, duplicated exposure, liquidity, thesis evidence, and risk thresholds are evaluated for every holding using the user's current canonical data.

## Locate the Workspace

Find the repository before reading data. Prefer the current working directory when it contains `scripts/toss_openapi_check.py` and the canonical `data/` files. Otherwise locate a user-approved directory containing those markers. If discovery finds zero or multiple candidates, ask the user for the local workspace path or accept it through the ephemeral `HCSCAT_INVEST_ROOT` environment variable. Resolve all inputs relative to that root, and never write the supplied path into source, reports, logs, screenshots, or saved analysis state.

Skill installation must copy only this generic skill package. It must not require a device path, username, account identifier, credential, or personal holding value. Device-specific values are supplied at runtime from the user's local workspace and are not part of the installed skill.

Canonical inputs normally include:

- `data/kr_portfolio_current.json`: Korean cash-equity holdings and transaction history.
- `data/pension_portfolio_current.json`: pension holdings.
- `data/us/us_portfolio_current.json`: U.S. holdings when present.
- `data/cash_current.json`: cash ledger; verify its date before using it.
- `data/kr_revaluation_latest.json` and `data/us/us_revaluation_latest.json`: latest synthesis and snapshots.
- `data/kr_trade_recommendation_score_latest.json` and the U.S. equivalent: prior action rules.

Timestamped reviews, screenshot imports, and `*_before_*` files are evidence or archives, not automatic replacements. Never infer a completed trade from a plan; update holdings only from an explicit fill or a verified source of record.

## Current-Session Routing

Route by the user's holdings and the current time before querying prices. Do not run live revaluation outside the relevant market window by default.

### Korean and Pension Holdings

- Use the Korea route only on Korean trading days during the combined Korean trading window **08:00-20:00 KST**, covering the currently available NXT and KRX quote windows without making them separate report sections.
- Query the currently active executable quote returned by Toss or the fallback source. Preserve the source's session metadata internally, but present one `한국장 현재 세션` price basis.
- Pension holdings are routed through Korea when they are Korean-listed securities. Do not treat the pension account as a different market clock.

### U.S. Holdings

- Use the U.S. route only on U.S. trading days during the exchange-local **regular session 09:30-16:00 America/New_York**. Do not run live U.S. price, news, disclosure, or flow research during pre-market or after-market hours unless the user explicitly requests an indication-only session comparison.
- Convert the current time with `America/New_York`; do not hard-code one Korean daylight-saving schedule.
- Present one `미국장 현재 세션` price basis. Do not create separate pre-market, regular-market, and after-market sections unless the user explicitly requests a session comparison.

### Outside the Window

If the relevant market is closed or the current time cannot be established, do not call a live revaluation “current.” Return the latest completed close only when useful, label it as historical, and state the next applicable window. If the user explicitly asks for an off-hours review, perform a clearly labeled historical or indication-only analysis.

## Data Collection and Fallbacks

Use Toss Invest OpenAPI first when credentials and read-only endpoints are available. Read credentials at runtime from the user's existing Keychain or local `.env` under the resolved workspace root; never ask the user to paste a token into chat:

```bash
python3 scripts/toss_openapi_check.py diagnose
python3 scripts/toss_openapi_check.py price SYMBOLS
python3 scripts/toss_openapi_check.py stock SYMBOLS
```

Use one sequential read-only price call for the complete symbol set. Do not issue parallel token requests. If Toss is unavailable, unauthorized, unsupported for a field, or unavailable to the user, fall back in this order:

1. Official exchange or market-operator data.
2. Official company or ETF issuer disclosures.
3. Public market pages such as Naver Finance or another transparent broker/public quote source.
4. Reliable news or research for context, never as the sole source of a live price.

Record the fallback source, URL, timestamp, delay status, and missing fields. Do not imply that a public quote page provides investor flow unless it explicitly labels that data.

## Investor-Flow Rules

- Prefer the latest completed-session foreign and institutional net-buy figures from a source that explicitly identifies the investor category.
- Same-day flow is provisional or unavailable unless the source explicitly supplies intraday investor data.
- Report units, date, and direction, for example `기관 +36,604주, 외국인 -1,737,367주 (확정일 2026-08-07)`.
- Do not infer investor flow from total volume, price direction, order-book imbalance, or NXT quotes.
- For ETFs, distinguish ETF-unit flow from the underlying constituent flow.

## Revaluation Workflow

1. Reconcile holdings, average cost, cash, and explicit recent fills from canonical state.
2. Confirm the relevant market window and query current-session prices once.
3. Calculate market value, P/L, weight, liquidity context, and duplicated sector or instrument exposure.
4. Add the latest confirmed investor flow and distinguish it from current-day flow.
5. Review official disclosures first, then reliable market reporting. Separate catalysts from recurring earnings and cash-flow proof.
6. Run the default position-agnostic risk screen. Run special concentration or single-name priority analysis only if explicitly requested.
7. Produce conditional buy, hold, partial-sale, and stop bands with action timing, rationale, invalidation condition, and order-type caution.
8. Critique the result: stale data, thin liquidity, one-day flow overinterpretation, tracking error, currency, fees, taxes, and uncertainty.
9. Save only non-secret structured state or a report. Validate JSON and never overwrite canonical holdings for a recommendation alone.

## Output Contract

Use Korean unless the user requests another language:

1. Observation time, market route, and current-session basis.
2. Holdings table with quantity, current price, P/L, source, and freshness.
3. Investor-flow table with latest confirmed date and coverage limits.
4. Per-position assessment with evidence and critical counterpoint.
5. Additional-buy candidates and conditional price bands.
6. Mandatory stop or partial-sale candidates.
7. Action timing and price bands at the bottom.
8. Data limitations and source links.

Use `확인불가`, `미제공`, or `지연` instead of blanks. Use explicit actions such as `추가매수 보류`, `20주 분할매도 검토`, or `종가 이탈 시 추가 축소 검토`.

## Validation

Before delivery:

```bash
python3 -m py_compile scripts/toss_openapi_check.py scripts/market_collection_benchmark.py
python3 -m json.tool data/kr_revaluation_latest.json >/dev/null
```

Confirm that no output contains secrets, that the report uses one current-session basis for the routed market, and that every price and flow has an observation date. If a new fill is reported, reconcile it before calculating weights or recommendations.
