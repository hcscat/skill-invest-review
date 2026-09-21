# Source Fallback

Use this reference when Toss Invest OpenAPI cannot supply a required field.

Check the current official endpoint before declaring a field unavailable. An
older CLI not exposing investor flow is not evidence of provider non-support.
Apply the same market-time policy to every fallback: do not obtain new U.S.
prices, news, disclosures or flow outside the allowed regular session, even under
the label "closing price." Existing local historical values must be dated and
kept separate from a current portfolio total. Calendars and general FX are allowed.

The bundled adapter targets the Toss Securities / Toss Invest OpenAPI. A different
broker or market-data API requires a separate adapter and validation of its
authentication, endpoint schema, market sessions, field meanings, rate limits,
and investor-flow definitions before it can be used with this skill.

## Priority

<!-- A new fallback must preserve session restrictions and explicit missing-field labels. -->

1. Toss Invest OpenAPI read-only endpoint.
2. Official exchange or market-operator quote and investor-flow data.
3. Official issuer or ETF-provider disclosure.
4. Public quote pages such as Naver Finance or another transparent broker source.
5. Reputable news or research for context only.

Every fallback record must include source name, URL, observed time, market phase, delay status, and fields not provided. Never treat a search snippet or a news headline as a live quote. Never infer foreign or institutional flow from price, volume, or an order book.

## User Without Toss Access

Ask for or discover only public ticker and market information. Do not request the user's API token in chat. Build a read-only report from public sources and mark account-specific quantities, average costs, cash, and P/L as unavailable unless the user supplies them in a non-secret form.

## Current-Session Label

The report should show one routed basis, such as `한국장 현재 세션` or `미국장 현재 세션`. Preserve the source's session metadata for audit, but do not split the normal report into NXT, regular, and after-market sections unless the user explicitly asks for a comparison.

Confirm the instrument's own session and suspension/NXT flags; a Korean routing
window does not make an NXT-ineligible ETF tradable outside KRX regular hours.
Record unavailable intraday investor flow as `미제공`, never as inferred zero.
