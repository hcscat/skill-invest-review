#!/usr/bin/env python3
"""Read-only Toss Invest OpenAPI checks.

Commands:
  diagnose  Run safe local diagnostics without printing secrets.
  token     Issue an access token and print only metadata.
  market    Issue a token and call read-only market/info endpoints.
  accounts  Issue a token and list account metadata.
  price     Issue a token and fetch current prices for symbols.
  stock     Issue a token and fetch stock reference data for symbols.
  flow      Fetch KR investor volume, separating prior dates and provisional data.
  orderbook Fetch quotes without assuming the levels are sorted.
  candles   Fetch adjusted daily candles; exclude today's bar from completed data.

This script intentionally does not create, modify, or cancel orders.

Set HCSCAT_INVEST_ROOT at runtime when this script is invoked outside the
workspace that contains it. The value is never printed or persisted.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from urllib import error, parse, request
from zoneinfo import ZoneInfo


WORKSPACE_ENV = "HCSCAT_INVEST_ROOT"
KEYCHAIN_SERVICE = "toss-invest-openapi"
SYMBOLS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]*$")
# Unknown code formats take the stricter US route; extend only with verified codes.
KR_SYMBOL_RE = re.compile(r"^[0-9][A-Z0-9]{5}$")
FLOW_GROUPS = ("individual", "foreigner", "institution", "otherCorporation")
FLOW_FIELDS = ("buyVolume", "sellVolume", "netBuyVolume")


class CheckError(RuntimeError):
    """An intentionally non-sensitive CLI error message."""


def resolve_workspace_root() -> Path:
    """Prefer an explicit root, then the marked CWD; never search parent folders."""
    configured = os.getenv(WORKSPACE_ENV, "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if not candidate.is_dir() or not (candidate / "scripts/toss_openapi_check.py").is_file():
            raise CheckError(f"{WORKSPACE_ENV} is not a valid Toss Invest workspace.")
        return candidate.resolve()
    candidate = Path.cwd()
    if (candidate / "scripts/toss_openapi_check.py").is_file() and (candidate / "data").is_dir():
        return candidate.resolve()
    return Path(__file__).resolve().parents[1]


# Compatibility for existing importers; CLI workspace discovery happens after --help.
ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


class KeychainReadError(RuntimeError):
    """Distinguish an unreadable credential from an absent Keychain item."""

    def __init__(self, account: str, returncode: int) -> None:
        self.account = account
        self.returncode = returncode
        detail = f"Keychain item exists for {account}, but its secret value could not be read."
        hint = (
            "This usually means the login keychain is locked, the current process is non-interactive, "
            "or Keychain access control requires a GUI approval prompt."
        )
        message = f"{detail} security_rc={returncode}. {hint}"
        super().__init__(message)


def load_dotenv(path: Path) -> None:
    """Load simple key/value entries without overriding the caller's environment."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def keychain_service() -> str:
    """Resolve the runtime Keychain namespace without persisting it."""
    return os.getenv("TOSS_INVEST_KEYCHAIN_SERVICE", KEYCHAIN_SERVICE).strip() or KEYCHAIN_SERVICE


def keychain_value(account: str) -> str | None:
    """Return a secret privately, or None when the item or Keychain is absent."""
    if not shutil.which("security"):
        return None
    result = subprocess.run(
        [
            "security",
            "find-generic-password",
            "-a",
            account,
            "-s",
            keychain_service(),
            "-w",
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        # Metadata lookup separates missing items from locked or denied access.
        metadata = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-a",
                account,
                "-s",
                keychain_service(),
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        if metadata.returncode == 0:
            raise KeychainReadError(account, result.returncode)
        return None
    value = result.stdout.strip()
    return value or None


def secret_value(name: str) -> str | None:
    """Prefer environment credentials; consult Keychain only when necessary."""
    value = os.getenv(name, "").strip()
    if value:
        return value
    try:
        return keychain_value(name)
    except KeychainReadError as exc:
        raise CheckError(str(exc)) from None


def require_secret(name: str) -> str:
    """Require a credential while exposing only its configuration key on failure."""
    value = secret_value(name)
    if not value:
        raise CheckError(
            "Missing required credential: "
            f"{name}. Set it in the approved workspace .env or macOS Keychain."
        )
    return value


def base_url() -> str:
    """Accept an HTTPS origin, not embedded credentials or an endpoint URL."""
    url = os.getenv("TOSS_INVEST_BASE_URL", "https://openapi.tossinvest.com").rstrip("/")
    parsed = parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
        raise CheckError("Base URL must be an HTTPS origin without user info, path or query.")
    return url


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward a bearer token or credential-bearing POST to another URL.
        return None


def http_json(method: str, url: str, *, headers: dict[str, str] | None = None, body: bytes | None = None) -> tuple[int, dict]:
    """Allow reads and token issuance; return HTTP status without raw error bodies."""
    if method != "GET" and not (method == "POST" and parse.urlsplit(url).path == "/oauth2/token"):
        raise CheckError("Only GET and OAuth token issuance are supported; trading writes are disabled.")
    req = request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with request.build_opener(NoRedirect).open(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            payload = json.loads(raw) if raw else {}
            if not isinstance(payload, dict):
                raise CheckError("Unexpected response shape; raw response omitted.")
            return resp.status, payload
    except error.HTTPError as exc:
        # Error bodies can echo request details. Never return them to a caller.
        return exc.code, {}
    except (error.URLError, OSError, UnicodeError, ValueError):
        raise CheckError("Network or JSON response failure; sensitive details omitted.") from None


def issue_token(*, print_metadata: bool = False) -> str:
    """Issue one in-memory token; optional output excludes its secret value."""
    # Reissuing a Toss token invalidates the old one; callers must serialize issuance.
    client_id = require_secret("TOSS_INVEST_CLIENT_ID")
    client_secret = require_secret("TOSS_INVEST_CLIENT_SECRET")
    body = parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode("utf-8")
    status, payload = http_json(
        "POST",
        f"{base_url()}/oauth2/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=body,
    )
    if status != 200:
        raise CheckError(f"Token request failed (HTTP {status}); response omitted.")
    token = payload.get("access_token")
    if not token:
        raise CheckError("Token response did not include access_token.")
    if print_metadata:
        print(
            json.dumps(
                {
                    "token_ok": True,
                    "token_type": payload.get("token_type"),
                    "expires_in": payload.get("expires_in"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return token


def bearer(token: str) -> dict[str, str]:
    """Build private request headers; callers must not log this mapping."""
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def get(path: str, token: str) -> tuple[int, dict]:
    """Perform an authenticated read; market-session checks belong to the caller."""
    return http_json("GET", f"{base_url()}{path}", headers=bearer(token))


def command_token(_args: argparse.Namespace) -> None:
    """Verify token issuance using non-secret metadata only."""
    issue_token(print_metadata=True)


def command_diagnose(_args: argparse.Namespace) -> None:
    """Report credential availability and connectivity, never values or paths."""
    credentials = {}
    for account in ["TOSS_INVEST_CLIENT_ID", "TOSS_INVEST_CLIENT_SECRET"]:
        env_value = os.getenv(account, "").strip()
        # Avoid unnecessary Keychain access prompts when the environment suffices.
        if env_value or not shutil.which("security"):
            credentials[account] = {
                "env_present": bool(env_value), "keychain_checked": False,
                "keychain_available": bool(shutil.which("security")),
            }
            continue
        metadata = subprocess.run(
            ["security", "find-generic-password", "-a", account, "-s", keychain_service()],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        value = subprocess.run(
            ["security", "find-generic-password", "-a", account, "-s", keychain_service(), "-w"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        credentials[account] = {
            "env_present": bool(env_value),
            "keychain_metadata_found": metadata.returncode == 0,
            "keychain_value_readable": value.returncode == 0 and bool(value.stdout.strip()),
            "keychain_value_rc": value.returncode,
        }

    root_status, _payload = http_json("GET", f"{base_url()}/")
    print(
        json.dumps(
            {
                "base_url_configured": bool(os.getenv("TOSS_INVEST_BASE_URL", "").strip()),
                "workspace_root_configured": bool(os.getenv(WORKSPACE_ENV, "").strip()),
                "env_file_present": (resolve_workspace_root() / ".env").exists(),
                "keychain_service_configured": bool(os.getenv("TOSS_INVEST_KEYCHAIN_SERVICE", "").strip()),
                "credentials": credentials,
                "network_root_status": root_status,
                "secret_values_printed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def command_market(_args: argparse.Namespace) -> None:
    """Read calendars and general FX, which do not require an open symbol session."""
    token = issue_token()
    checks = [
        "/api/v1/exchange-rate?baseCurrency=USD&quoteCurrency=KRW",
        "/api/v1/market-calendar/KR",
        "/api/v1/market-calendar/US",
    ]
    results = []
    for path in checks:
        result = read_result(path, token)
        item = {"path": path, "result": result}
        if "/market-calendar/" in path:
            item["routing"] = session_state(result, path.rsplit("/", 1)[1], utc_now())
        results.append(item)
    emit({"observed_at": utc_now().isoformat(), "market_checks": results})


def command_accounts(_args: argparse.Namespace) -> None:
    """Expose account count only; keep account identifiers out of CLI output."""
    token = issue_token()
    status, payload = get("/api/v1/accounts", token)
    require_ok(status)
    accounts = payload.get("result", []) if isinstance(payload, dict) else []
    print(
        json.dumps(
            {
                "accounts_ok": 200 <= status < 300,
                "status": status,
                "account_count": len([item for item in accounts if isinstance(item, dict)]),
                "account_identifiers_printed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def command_price(args: argparse.Namespace) -> None:
    """Join complete quote/reference batches without implying executable prices."""
    symbols = ",".join(validate_symbols(args.symbols))
    token = issue_token()
    routing = guard_symbols(symbols, token)
    query = parse.urlencode({"symbols": symbols})
    require_active_routes(routing)
    prices_status, prices_payload = get(f"/api/v1/prices?{query}", token)
    require_ok(prices_status)
    # The quote request may finish after closing; recheck before reference lookup.
    require_active_routes(routing)
    stocks_status, stocks_payload = get(f"/api/v1/stocks?{query}", token)
    require_ok(stocks_status)
    prices = checked_items(prices_payload, symbols)
    stocks_by_symbol = {item["symbol"]: item for item in checked_items(stocks_payload, symbols)}
    enriched_prices = []
    for price in prices:
        if not isinstance(price, dict):
            continue
        stock = stocks_by_symbol.get(price.get("symbol"), {})
        enriched_prices.append(
            {
                "symbol": price.get("symbol"),
                "name": stock.get("name"),
                "englishName": stock.get("englishName"),
                "market": stock.get("market"),
                "securityType": stock.get("securityType"),
                "status": stock.get("status"),
                "lastPrice": price.get("lastPrice"),
                "currency": price.get("currency"),
                "timestamp": price.get("timestamp"),
                "koreanMarketDetail": stock.get("koreanMarketDetail"),
            }
        )
    print(
        json.dumps(
            {
                "observed_at": utc_now().isoformat(),
                "routing": routing,
                "execution_guaranteed": False,
                "prices_ok": 200 <= prices_status < 300,
                "prices_status": prices_status,
                "stock_info_ok": 200 <= stocks_status < 300,
                "stock_info_status": stocks_status,
                "result": enriched_prices,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def command_stock(args: argparse.Namespace) -> None:
    """Return selected reference fields, including venue eligibility and suspensions."""
    symbols = ",".join(validate_symbols(args.symbols))
    token = issue_token()
    routing = guard_symbols(symbols, token)
    query = parse.urlencode({"symbols": symbols})
    require_active_routes(routing)
    status, payload = get(f"/api/v1/stocks?{query}", token)
    require_ok(status)
    items = []
    for item in checked_items(payload, symbols):
        if not isinstance(item, dict):
            continue
        items.append(
            {
                "symbol": item.get("symbol"),
                "name": item.get("name"),
                "englishName": item.get("englishName"),
                "market": item.get("market"),
                "securityType": item.get("securityType"),
                "status": item.get("status"),
                "currency": item.get("currency"),
                "isinCode": item.get("isinCode"),
                "koreanMarketDetail": item.get("koreanMarketDetail"),
            }
        )
    emit({"stock_info_ok": True, "status": status, "routing": routing, "result": items})


def emit(value: dict) -> None:
    """Serialize pre-sanitized output; this helper does not redact its input."""
    print(json.dumps(value, ensure_ascii=False, indent=2))


def utc_now() -> datetime:
    """Use an aware UTC instant for cross-market comparisons and audit times."""
    return datetime.now(timezone.utc)


def require_ok(status: int) -> None:
    """Turn HTTP failures into nonzero CLI exits without echoing response details."""
    if not 200 <= status < 300:
        raise CheckError(f"Read-only API request failed (HTTP {status}); response omitted.")


def read_result(path: str, token: str) -> dict:
    """Require an object-shaped result rather than silently accepting schema drift."""
    status, payload = get(path, token)
    require_ok(status)
    result = payload.get("result")
    if not isinstance(result, dict):
        raise CheckError("Expected an object result; response omitted.")
    return result


def validate_symbols(value: str) -> list[str]:
    """Normalize a bounded, unique symbol batch before token or network work."""
    symbols = [symbol.strip().upper() for symbol in value.split(",")]
    if not 1 <= len(symbols) <= 200 or any(not SYMBOLS_RE.fullmatch(s) for s in symbols):
        raise CheckError("Provide 1-200 non-empty comma-separated symbols.")
    if len(set(symbols)) != len(symbols):
        raise CheckError("Duplicate symbols are not allowed.")
    return symbols


def aware_time(value: str) -> datetime:
    """Reject timestamps whose missing offset would make session routing ambiguous."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timezone is required")
    return parsed


def session_state(calendar: dict, market: str, now: datetime) -> dict:
    """Fail closed using dated calendar windows, not a fixed KST U.S. schedule."""
    if market not in ("KR", "US") or now.tzinfo is None:
        raise CheckError("A supported market and timezone-aware observation time are required.")
    result = {"market": market, "open": False, "reason": "outside_allowed_session", "next_open": None}
    try:
        # Day labels are exchange-local; session timestamps may use KST for US too.
        zone = ZoneInfo("Asia/Seoul" if market == "KR" else "America/New_York")
        if calendar["today"]["date"] != now.astimezone(zone).date().isoformat():
            return {**result, "reason": "stale_calendar"}
        windows = []
        for key in ("previousBusinessDay", "today", "nextBusinessDay"):
            day = calendar[key]
            sessions = (day.get("integrated") or {}) if market == "KR" else day
            names = ("preMarket", "regularMarket", "afterMarket") if market == "KR" else ("regularMarket",)
            for name in names:
                session = sessions.get(name)
                if session is None:
                    continue
                start, end = aware_time(session["startTime"]), aware_time(session["endTime"])
                if start >= end:
                    raise ValueError("Invalid interval")
                windows.append((start, end, name))
        for start, end, name in sorted(windows):
            # The end is exclusive: a request at the exact close is already blocked.
            if start <= now < end:
                local = now.astimezone(ZoneInfo("America/New_York" if market == "US" else "Asia/Seoul"))
                minute = local.hour * 60 + local.minute
                # Local policy narrows provider windows; early closes remain binding.
                allowed = (570 <= minute < 960) if market == "US" else (480 <= minute < 1200)
                if allowed and local.weekday() < 5:
                    return {**result, "open": True, "reason": "allowed_session", "session": name,
                            "start": start.isoformat(), "end": end.isoformat()}
            if start > now and result["next_open"] is None:
                result["next_open"] = start.isoformat()
        today = calendar["today"]
        if (market == "KR" and today.get("integrated") is None) or (market == "US" and today.get("regularMarket") is None):
            result["reason"] = "calendar_closed"
        return result
    except (KeyError, TypeError, ValueError, AttributeError):
        return {**result, "reason": "invalid_calendar"}


def guard_symbols(symbols: str, token: str) -> list[dict]:
    """Validate every market in a batch before allowing any symbol-specific read."""
    markets = {"KR" if KR_SYMBOL_RE.fullmatch(s) else "US" for s in validate_symbols(symbols)}
    states = []
    for market in sorted(markets):
        calendar = read_result(f"/api/v1/market-calendar/{market}", token)
        state = session_state(calendar, market, utc_now())
        if not state["open"]:
            # Block the entire batch before any symbol-specific request.
            raise CheckError(f"{market} research blocked: {state['reason']}; inspect market for the next window.")
        states.append(state)
    return states


def require_active_routes(states: list[dict]) -> None:
    """Recheck the cached interval immediately before each symbol request."""
    now = utc_now()
    if not states or any(not aware_time(state["start"]) <= now < aware_time(state["end"]) for state in states):
        raise CheckError("Allowed session ended before the next request; research stopped.")


def flow_summary(records: list, *, as_of: date, days: int, expected_latest: str | None) -> dict:
    """Never zero-fill null volumes or silently aggregate inconsistent records."""
    if not 1 <= days <= 99:
        raise CheckError("Flow days must be between 1 and 99.")
    prior, provisional, issues, seen = [], [], [], set()
    date_error = False
    for raw in records:
        try:
            record_date = date.fromisoformat(raw["date"])
            if record_date in seen or record_date > as_of:
                raise ValueError("Duplicate or future date")
            seen.add(record_date)
        except (KeyError, TypeError, ValueError):
            issues.append("invalid_duplicate_or_future_date")
            # Dropping suspect dates alone would leave a misleading aggregate.
            date_error = True
            continue
        row = {key: raw.get(key) for key in ("date", "updatedAt", *FLOW_GROUPS)}
        # Keep today's record provisional even after close; finalization is unproven.
        (provisional if record_date == as_of else prior).append(row)
    prior.sort(key=lambda row: row["date"], reverse=True)
    selected = prior[:days]
    # Available dates are not necessarily consecutive exchange sessions.
    if len(selected) < days:
        issues.append("insufficient_prior_dates")
    latest_matches = bool(selected and expected_latest and selected[0]["date"] == expected_latest)
    if not latest_matches:
        issues.append("latest_completed_date_missing_or_unverified")
    totals = {}
    for group in FLOW_GROUPS:
        sums = dict.fromkeys(FLOW_FIELDS, 0)
        valid = bool(selected) and not date_error
        for row in selected:
            value = row.get(group)
            try:
                if not isinstance(value, dict):
                    raise ValueError("Missing group")
                if any(not re.fullmatch(r"-?\d+", str(value.get(field))) for field in FLOW_FIELDS):
                    raise ValueError("Invalid integer")
                numbers = {field: int(value[field]) for field in FLOW_FIELDS}
                if numbers["buyVolume"] < 0 or numbers["sellVolume"] < 0 or numbers["buyVolume"] - numbers["sellVolume"] != numbers["netBuyVolume"]:
                    raise ValueError("Invalid net volume")
                for field in FLOW_FIELDS:
                    sums[field] += numbers[field]
            except (KeyError, TypeError, ValueError):
                issues.append(f"{row['date']}:{group}:missing_or_inconsistent_volume")
                valid = False
        # A partial category sum must not masquerade as a valid full-window total.
        totals[group] = sums if valid else None
    return {"basis": "latest_available_prior_dates", "units": "shares", "venue_scope": "KRX+NXT",
            "foreigner_scope": "registered_foreigners", "requested_days": days,
            "included_dates": [row["date"] for row in selected], "prior_date_records": selected,
            "provisional_records": provisional, "totals": totals,
            "latest_date_verified": latest_matches, "consecutive_sessions_verified": False,
            "coverage_note": "Three-day calendar cannot certify every historical session; verify gaps separately.",
            "issues": issues}


def command_flow(args: argparse.Namespace) -> None:
    """Read KR historical/provisional flow sequentially under one shared token."""
    symbols = validate_symbols(args.symbols)
    if any(not KR_SYMBOL_RE.fullmatch(s) for s in symbols):
        raise CheckError("Investor flow supports KR six-character stock codes only.")
    if not 1 <= args.days <= 99:
        raise CheckError("Flow days must be between 1 and 99.")
    token = issue_token()
    calendar = read_result("/api/v1/market-calendar/KR", token)
    now = utc_now()
    today = now.astimezone(ZoneInfo("Asia/Seoul")).date()
    expected = (calendar.get("previousBusinessDay") or {}).get("date")
    if (calendar.get("today") or {}).get("date") != today.isoformat():
        expected = None
    results = []
    for symbol in symbols:
        # Reserve one response row for today's provisional record within the API cap.
        path = f"/api/v1/stocks/{symbol}/investor-trading?count={args.days + 1}"
        result = read_result(path, token)
        if not isinstance(result.get("records"), list):
            raise CheckError("Expected investor records; response omitted.")
        summary = flow_summary(result["records"], as_of=today, days=args.days, expected_latest=expected)
        results.append({"symbol": symbol, "source_path": path, "nextUntil": result.get("nextUntil"), **summary})
    emit({"observed_at": now.isoformat(), "result": results})


def best_quote(levels: list, *, side: str) -> dict | None:
    """Select a positive-size best level with decimal precision, or None."""
    if side not in ("bids", "asks"):
        raise CheckError("Unsupported quote side.")
    valid = []
    for level in levels:
        try:
            price, volume = Decimal(str(level["price"])), Decimal(str(level["volume"]))
            if price.is_finite() and volume.is_finite() and price > 0 and volume > 0:
                valid.append({"price": str(price), "volume": str(volume)})
        except (KeyError, TypeError, InvalidOperation):
            continue
    if not valid:
        return None
    # Provider ordering is not assumed; highest bid and lowest ask define the best.
    return sorted(valid, key=lambda level: Decimal(level["price"]), reverse=side == "bids")[0]


def split_daily_candles(candles: list, today: date, market: str) -> dict:
    """Separate prior market dates without certifying OHLC values or session gaps."""
    prior, excluded, seen = [], [], set()
    zone = ZoneInfo("Asia/Seoul" if market == "KR" else "America/New_York")
    for row in candles:
        try:
            stamp = aware_time(row["timestamp"])
            day = stamp.astimezone(zone).date()
            if day in seen:
                raise ValueError("Duplicate day")
            seen.add(day)
        except (KeyError, TypeError, ValueError, AttributeError):
            raise CheckError("Invalid or duplicate daily candle timestamp; no completed-bar calculation.") from None
        # A daily midnight timestamp labels the trading date, not a finished bar.
        (prior if day < today else excluded).append(row)
    return {"prior_date_candles": prior, "excluded_today_or_future": excluded,
            "completion_policy": "Exclude current market-local date conservatively, including after close."}


def command_detail(args: argparse.Namespace) -> None:
    """Preserve raw quote/bar evidence alongside conservative derived fields."""
    symbols = validate_symbols(args.symbol)
    if len(symbols) != 1:
        raise CheckError("This command accepts one symbol.")
    symbol = symbols[0]
    if args.command == "candles" and not 1 <= args.count <= 200:
        raise CheckError("Candle count must be between 1 and 200.")
    token = issue_token()
    routing = guard_symbols(symbol, token)
    query = {"symbol": symbol}
    if args.command == "candles":
        query.update(interval="1d", count=args.count, adjusted="true")
    path = f"/api/v1/{args.command}?{parse.urlencode(query)}"
    require_active_routes(routing)
    result = read_result(path, token)
    now = utc_now()
    if args.command == "orderbook":
        if not all(isinstance(result.get(side), list) for side in ("bids", "asks")):
            raise CheckError("Expected bid and ask arrays; response omitted.")
        derived = {"best_bid": best_quote(result["bids"], side="bids"),
                   "best_ask": best_quote(result["asks"], side="asks"), "execution_guaranteed": False}
    else:
        if not isinstance(result.get("candles"), list):
            raise CheckError("Expected candle array; response omitted.")
        market = routing[0]["market"]
        today = now.astimezone(ZoneInfo("Asia/Seoul" if market == "KR" else "America/New_York")).date()
        derived = {"adjusted": True, **split_daily_candles(result["candles"], today, market)}
    emit({"symbol": symbol, "observed_at": now.isoformat(), "source_path": path,
          "routing": routing, "result": result, **derived})


def result_items(payload: dict) -> list:
    """Extract list results; use checked_items when full symbol coverage is required."""
    result = payload.get("result", []) if isinstance(payload, dict) else []
    return result if isinstance(result, list) else []


def checked_items(payload: dict, symbols: str) -> list:
    """Reject partial, duplicate or unexpected symbols before reporting a snapshot."""
    items = result_items(payload)
    expected = set(validate_symbols(symbols))
    actual = [item.get("symbol") for item in items if isinstance(item, dict)]
    if len(items) != len(expected) or len(actual) != len(expected) or set(actual) != expected:
        raise CheckError("Missing, duplicate or unexpected symbols in response; no complete snapshot available.")
    return items


def parse_args() -> argparse.Namespace:
    """Expose read-only commands without triggering workspace or credential lookup."""
    parser = argparse.ArgumentParser(description="Read-only Toss Invest OpenAPI checks")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("diagnose", help="Run safe local diagnostics without printing secrets")
    sub.add_parser("token", help="Issue access token only")
    sub.add_parser("market", help="Run read-only market/info checks")
    sub.add_parser("accounts", help="Count accounts without printing identifiers")
    price = sub.add_parser("price", help="Fetch current prices for comma-separated symbols")
    price.add_argument("symbols", help="Comma-separated symbols, e.g. 005930,000660 or AAPL,MSFT")
    stock = sub.add_parser("stock", help="Fetch stock names and reference data for comma-separated symbols")
    stock.add_argument("symbols", help="Comma-separated symbols, e.g. 005930,000660 or AAPL,MSFT")
    flow = sub.add_parser("flow", help="KR investor share volumes; today's data stays provisional")
    flow.add_argument("symbols", help="Comma-separated KR codes")
    flow.add_argument("--days", type=int, default=5, help="Prior dates to aggregate, 1-99 (default 5)")
    orderbook = sub.add_parser("orderbook", help="Read one symbol's order book and best bid/ask")
    orderbook.add_argument("symbol")
    candles = sub.add_parser("candles", help="Read adjusted daily bars and exclude today's bar")
    candles.add_argument("symbol")
    candles.add_argument("--count", type=int, default=30, help="Number of bars, 1-200")
    return parser.parse_args()


def main() -> int:
    """Dispatch CLI work and convert expected failures into sanitized JSON errors."""
    # Parse first so --help works without a configured workspace or credentials.
    args = parse_args()
    try:
        load_dotenv(resolve_workspace_root() / ".env")
        commands = {"diagnose": command_diagnose, "token": command_token,
                    "market": command_market, "accounts": command_accounts,
                    "price": command_price, "stock": command_stock, "flow": command_flow,
                    "orderbook": command_detail, "candles": command_detail}
        commands[args.command](args)
        return 0
    except CheckError as exc:
        emit({"ok": False, "error": str(exc)})
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        emit({"ok": False, "error": "Local configuration or response failure; sensitive details omitted."})
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
