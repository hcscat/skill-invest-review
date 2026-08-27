#!/usr/bin/env python3
"""Read-only Toss Invest OpenAPI checks.

Commands:
  diagnose  Run safe local diagnostics without printing secrets.
  token     Issue an access token and print only metadata.
  market    Issue a token and call read-only market/info endpoints.
  accounts  Issue a token and list account metadata.
  price     Issue a token and fetch current prices for symbols.
  stock     Issue a token and fetch stock reference data for symbols.

This script intentionally does not create, modify, or cancel orders.

Set HCSCAT_INVEST_ROOT at runtime when this script is invoked outside the
workspace that contains it. The value is never printed or persisted.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from urllib import error, parse, request


WORKSPACE_ENV = "HCSCAT_INVEST_ROOT"
KEYCHAIN_SERVICE = "toss-invest-openapi"
SYMBOLS_RE = re.compile(r"^[A-Za-z0-9.,-]+$")


def resolve_workspace_root() -> Path:
    configured = os.getenv(WORKSPACE_ENV, "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if not candidate.is_dir() or not (candidate / "scripts/toss_openapi_check.py").is_file():
            raise SystemExit(f"{WORKSPACE_ENV} is not a valid Toss Invest workspace.")
        return candidate.resolve()
    return Path(__file__).resolve().parents[1]


ROOT = resolve_workspace_root()
ENV_PATH = ROOT / ".env"


class KeychainReadError(RuntimeError):
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
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def keychain_service() -> str:
    return os.getenv("TOSS_INVEST_KEYCHAIN_SERVICE", KEYCHAIN_SERVICE).strip() or KEYCHAIN_SERVICE


def keychain_value(account: str) -> str | None:
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
    value = os.getenv(name, "").strip()
    if value:
        return value
    try:
        return keychain_value(name)
    except KeychainReadError as exc:
        raise SystemExit(str(exc)) from exc


def require_secret(name: str) -> str:
    value = secret_value(name)
    if not value:
        raise SystemExit(
            "Missing required credential: "
            f"{name}. Set it in .env or macOS Keychain service '{keychain_service()}'."
        )
    return value


def base_url() -> str:
    return os.getenv("TOSS_INVEST_BASE_URL", "https://openapi.tossinvest.com").rstrip("/")


def http_json(method: str, url: str, *, headers: dict[str, str] | None = None, body: bytes | None = None) -> tuple[int, dict]:
    req = request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return exc.code, payload


def issue_token(*, print_metadata: bool = False) -> str:
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
        raise SystemExit(json.dumps({"token_ok": False, "status": status}, ensure_ascii=False, indent=2))
    token = payload.get("access_token")
    if not token:
        raise SystemExit("Token response did not include access_token.")
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
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def get(path: str, token: str) -> tuple[int, dict]:
    return http_json("GET", f"{base_url()}{path}", headers=bearer(token))


def command_token(_args: argparse.Namespace) -> None:
    issue_token(print_metadata=True)


def command_diagnose(_args: argparse.Namespace) -> None:
    credentials = {}
    for account in ["TOSS_INVEST_CLIENT_ID", "TOSS_INVEST_CLIENT_SECRET"]:
        env_value = os.getenv(account, "").strip()
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
                "env_file_present": ENV_PATH.exists(),
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
    token = issue_token()
    checks = [
        "/api/v1/exchange-rate?baseCurrency=USD&quoteCurrency=KRW",
        "/api/v1/market-calendar/KR",
        "/api/v1/market-calendar/US",
    ]
    results = []
    for path in checks:
        status, payload = get(path, token)
        results.append({"path": path, "status": status, "ok": 200 <= status < 300, "top_level_keys": sorted(payload.keys())})
    print(json.dumps({"market_checks": results}, ensure_ascii=False, indent=2))


def command_accounts(_args: argparse.Namespace) -> None:
    token = issue_token()
    status, payload = get("/api/v1/accounts", token)
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
    symbols = args.symbols.strip()
    if not SYMBOLS_RE.fullmatch(symbols):
        raise SystemExit("Invalid symbols. Use comma-separated symbols such as 005930,000660 or AAPL,MSFT.")
    token = issue_token()
    query = parse.urlencode({"symbols": symbols})
    prices_status, prices_payload = get(f"/api/v1/prices?{query}", token)
    stocks_status, stocks_payload = get(f"/api/v1/stocks?{query}", token)
    prices = result_items(prices_payload)
    stocks_by_symbol = {item.get("symbol"): item for item in result_items(stocks_payload) if isinstance(item, dict)}
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
            }
        )
    print(
        json.dumps(
            {
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
    symbols = args.symbols.strip()
    if not SYMBOLS_RE.fullmatch(symbols):
        raise SystemExit("Invalid symbols. Use comma-separated symbols such as 005930,000660 or AAPL,MSFT.")
    token = issue_token()
    query = parse.urlencode({"symbols": symbols})
    status, payload = get(f"/api/v1/stocks?{query}", token)
    items = []
    for item in result_items(payload):
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
            }
        )
    print(json.dumps({"stock_info_ok": 200 <= status < 300, "status": status, "result": items}, ensure_ascii=False, indent=2))


def result_items(payload: dict) -> list:
    result = payload.get("result", []) if isinstance(payload, dict) else []
    return result if isinstance(result, list) else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only Toss Invest OpenAPI checks")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("diagnose", help="Run safe local diagnostics without printing secrets")
    sub.add_parser("token", help="Issue access token only")
    sub.add_parser("market", help="Run read-only market/info checks")
    sub.add_parser("accounts", help="List account metadata with masked account number")
    price = sub.add_parser("price", help="Fetch current prices for comma-separated symbols")
    price.add_argument("symbols", help="Comma-separated symbols, e.g. 005930,000660 or AAPL,MSFT")
    stock = sub.add_parser("stock", help="Fetch stock names and reference data for comma-separated symbols")
    stock.add_argument("symbols", help="Comma-separated symbols, e.g. 005930,000660 or AAPL,MSFT")
    return parser.parse_args()


def main() -> int:
    load_dotenv(ENV_PATH)
    args = parse_args()
    if args.command == "diagnose":
        command_diagnose(args)
    elif args.command == "token":
        command_token(args)
    elif args.command == "market":
        command_market(args)
    elif args.command == "accounts":
        command_accounts(args)
    elif args.command == "price":
        command_price(args)
    elif args.command == "stock":
        command_stock(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
