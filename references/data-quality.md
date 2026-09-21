# Review data and validation contract

Read for portfolio valuation, balance reconciliation, investor-flow interpretation,
quote/candle validation and conditional action plans. No personal data is bundled.

## Ledger and cash

- Inspect each account's JSON shape. Canonical holdings override old analysis files,
  dated imports and proposed trades. Show holdings-as-of and quote-observed-at
  separately; old holdings require an explicit no-subsequent-changes assumption.
- Prefer verified displayed total cost (`cost_display` or `cost_display_krw`, when
  present) over rounded average price times quantity. Keep row/summary rounding
  deltas. Unrealized P/L without dividends, fees and realized gains is not total return.
- General KRW cash, USD cash and pension orderable funds are separate budgets.
  Do not move money across accounts implicitly, count FX-equivalent cash twice,
  or treat an unexplained account residual as spendable cash. Orderable funds are
  not automatically the same as settled cash or withdrawable funds.
- If U.S. USD cost is absent, never back-solve it using current FX. A timestamped
  FX rate may convert current value against a known KRW cost; label that basis.
  If cost is unknown, P/L is unknown. Do not mix skipped/stale U.S. prices into a
  current whole-portfolio total.
- A user-designated verified screenshot can reconcile balances without proving
  individual fills. Back up affected canonical files, record a snapshot
  reconciliation event and rounding deltas, not invented trade prices, realized
  P/L, fees or taxes. Never save account numbers, attachment IDs or image paths.
  Balance reconciliation alone does not refresh a stale revaluation.

## Toss data contract and CLI interpretation

<!-- Maintainers: update this contract with adapter behavior; refresh verification dates only after rechecking the API. -->

Verified against [official REST OpenAPI](https://openapi.tossinvest.com/openapi-docs/latest/openapi.json)
version 1.2.17 on 2026-09-21. Recheck the live specification when fields or behavior
change; these are Toss-specific semantics, not assumptions for another API.

| Command / endpoint | Interpretation and boundary |
| --- | --- |
| `market` / `/api/v1/market-calendar/KR` and `/US` | Returns calendar and routing status, plus general FX. Day labels are exchange-local; timestamp offsets must be parsed. Check holidays, early closes, stale calendars and the next open. |
| `price` / `/api/v1/prices` | One batch per allowed market; output retains quote timestamp and reference metadata. Last trade is not an executable quote guarantee. |
| `stock` / `/api/v1/stocks` | Includes `koreanMarketDetail` for NXT eligibility and venue suspensions. Reference status alone does not prove live order availability. |
| `flow` / `/api/v1/stocks/{symbol}/investor-trading` | KR-only, share counts across KRX+NXT. `foreigner` means registered foreigners. Index investor-trading amounts use a different unit/population. |
| `orderbook` / `/api/v1/orderbook` | Best bid is the largest valid bid, best ask the smallest valid ask; do not assume array order. Empty/zero-size levels do not make a usable quote. |
| `candles` / `/api/v1/candles` | CLI requests adjusted daily bars. A midnight timestamp labels the trading day, not completion. Today's/future bars are excluded conservatively; `nextBefore` remains available for pagination. |

The CLI's symbol routing recognizes digit-leading six-character KR codes,
including alphanumeric codes. Other symbols take the stricter U.S. route; verify
new or ambiguous code formats before adapting this rule. Calendar permission is
market-level only: verify instrument eligibility before giving an actionable plan.

`price`, `stock`, `orderbook` and `candles` refuse a closed or unverified market
before symbol requests. A mixed KR/US batch fails entirely if either market is
closed. The CLI has no off-hours bypass. The `flow` command can read historical
KR data outside KR hours but never treats it as a current executable quote.
One invocation issues one token; invoke commands sequentially. The adapter's
low-level Python helpers are not a sandbox for arbitrary caller-written code.

### Flow checks

<!-- Keep coverage claims consistent with flow_summary and its regression tests. -->

- Preserve trading `date` and record-wide `updatedAt`: holdings/CFD updates can
  occur later than the underlying trades. A newer update does not change trade date.
- The CLI excludes all current-date records from prior-date totals, even after
  the close. This conservative policy avoids guessing when data is finalized.
  Later confirmed same-day figures may be described separately with evidence.
- For each category require integer, nonnegative buy/sell volume and
  `buyVolume - sellVolume == netBuyVolume`. Negative net volume is valid selling.
  Missing categories are `null`, not zero. A provisional ETF zero is not evidence
  of no activity. Invalid category data makes that category's total unavailable.
- Duplicate, malformed or future dates invalidate totals. `included_dates` defines
  the actual summed window. Fewer requested dates, a missing latest completed date,
  or invalid volumes appear in `issues`; do not label that result a full window.
- The three-day calendar cannot prove continuity across all five historical
  sessions. `consecutive_sessions_verified` is deliberately false. Check a full
  exchange calendar, missing records and `nextUntil` before claiming five
  consecutive sessions. Do not guess holidays from gaps between weekdays.
- ETF-unit flow does not describe constituent flow. One-day net buying does not
  establish a durable reversal. Net volumes times a daily average price are a
  proxy, not actual trade-cost inventory; label any distribution estimate accordingly.

### Quote and candle checks

- Check currency, timestamps, exchange tick size, spread, venue and suspension.
  An anomalous `lastPrice` should not silently become an executable price.
- If using a quote-derived valuation, apply one clearly stated basis throughout
  the comparable valuation scope. Preserve the raw value, quote time and reason.
  Best-bid valuation is a conservative sale reference, not a guaranteed fill;
  buys use asks/limits and available size. Do not automatically replace trades
  with quotes without these checks.
- Check duplicate/missing sessions, OHLC consistency, adjusted status and source
  session scope before moving averages or support/resistance. The CLI separates
  prior dates but does not certify every candle, calculate fair value or verify
  corporate-action adjustments. Do not count an in-progress daily bar as a close.

## Conditional actions

Provide account, symbol, trigger, quantity, estimated cash amount, actual applicable
session, expiry, rationale, counter-evidence and invalidation. Derive price bands
from observed completed bars, disclosed valuation assumptions or an explicit risk
budget. Unknown inputs mean a deferred decision, not invented precise prices.

Keep alternatives mutually exclusive where necessary; total sales cannot exceed
holdings and purchases cannot exceed that account's budget after buffers. A
one-share whole-share position cannot support partial sales. Do not force a
stop-loss simply because unrealized P/L is negative.

Check latest amended disclosures for rights offerings, ex-rights, subscription
rights, splits and mergers. Distinguish planned and confirmed terms. Recalculate
price conditions across the event; never automatically book rights, subscriptions
or cash without verified quantities and execution evidence.

## Private output and public verification

Keep portfolio reports, raw snapshots, backups and runtime configuration in the
private workspace. Validate changed JSON and calculation totals there. A report
may be non-secret yet still contain private financial information.

Public tests use synthetic fixtures and mock the network. They establish local
behavior, not live U.S. regular-session or another-provider compatibility. Do
not run credentialed or off-hours U.S. research merely to make a test pass.
