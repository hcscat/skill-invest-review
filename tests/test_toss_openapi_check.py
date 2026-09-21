#!/usr/bin/env python3
"""Offline regression tests using synthetic data; no credentials or trading calls."""

from contextlib import redirect_stdout
from datetime import date, datetime
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib import error


# Test this package's adapter, not another copy installed on the host.
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "toss_openapi_check.py"
SPEC = importlib.util.spec_from_file_location("toss_check_under_test", SCRIPT)
toss = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(toss)


def calendar(day, start=None, end=None, market="US"):
    """Build a minimal calendar fixture; absent sessions represent closed windows."""
    session = {"startTime": start, "endTime": end} if start else None
    today = {"date": day, "regularMarket": session}
    empty = {"regularMarket": None}
    if market == "KR":
        today = {"date": day, "integrated": {"regularMarket": session} if session else None}
        empty = {"integrated": None}
    return {"today": today, "previousBusinessDay": dict(empty), "nextBusinessDay": dict(empty)}


def record(day, buy="10", sell="4", net="6"):
    """Create independent synthetic category values for deliberate corruption tests."""
    value = {"buyVolume": buy, "sellVolume": sell, "netBuyVolume": net}
    return {"date": day, "updatedAt": day + "T20:00:00+09:00",
            **{group: dict(value) for group in toss.FLOW_GROUPS}}


class SessionTests(unittest.TestCase):
    """Cover calendar boundaries and prove blocked commands stop before symbol reads."""

    def test_summer_open_and_exclusive_close(self):
        cal = calendar("2025-06-02", "2025-06-02T22:30:00+09:00", "2025-06-03T05:00:00+09:00")
        self.assertTrue(toss.session_state(cal, "US", datetime.fromisoformat("2025-06-02T22:30:00+09:00"))["open"])
        self.assertFalse(toss.session_state(cal, "US", datetime.fromisoformat("2025-06-03T05:00:00+09:00"))["open"])

    def test_winter_dst_and_kst_midnight(self):
        cal = calendar("2025-01-06", "2025-01-06T23:30:00+09:00", "2025-01-07T06:00:00+09:00")
        self.assertFalse(toss.session_state(cal, "US", datetime.fromisoformat("2025-01-06T22:45:00+09:00"))["open"])
        self.assertTrue(toss.session_state(cal, "US", datetime.fromisoformat("2025-01-07T00:30:00+09:00"))["open"])

    def test_early_close(self):
        cal = calendar("2025-11-28", "2025-11-28T09:30:00-05:00", "2025-11-28T13:00:00-05:00")
        self.assertFalse(toss.session_state(cal, "US", datetime.fromisoformat("2025-11-28T13:01:00-05:00"))["open"])

    def test_holiday_next_open(self):
        cal = calendar("2025-07-04")
        cal["nextBusinessDay"] = {"regularMarket": {"startTime": "2025-07-07T09:30:00-04:00", "endTime": "2025-07-07T16:00:00-04:00"}}
        state = toss.session_state(cal, "US", datetime.fromisoformat("2025-07-04T10:00:00-04:00"))
        self.assertEqual(state["reason"], "calendar_closed")
        self.assertEqual(state["next_open"], "2025-07-07T09:30:00-04:00")

    def test_stale_and_malformed_calendar_fail_closed(self):
        now = datetime.fromisoformat("2025-06-02T10:00:00-04:00")
        self.assertEqual(toss.session_state(calendar("2025-05-30"), "US", now)["reason"], "stale_calendar")
        cal = calendar("2025-06-02", "2025-06-02T09:30:00", "2025-06-02T16:00:00")
        self.assertEqual(toss.session_state(cal, "US", now)["reason"], "invalid_calendar")

    def test_korean_route_and_partial_closure(self):
        cal = calendar("2025-06-02", "2025-06-02T09:00:00+09:00", "2025-06-02T15:30:00+09:00", "KR")
        self.assertFalse(toss.session_state(cal, "KR", datetime.fromisoformat("2025-06-02T08:30:00+09:00"))["open"])
        self.assertTrue(toss.session_state(cal, "KR", datetime.fromisoformat("2025-06-02T10:00:00+09:00"))["open"])

    def test_closed_us_commands_make_no_symbol_request(self):
        cal = calendar("2025-06-02")
        args = [toss.argparse.Namespace(command="price", symbols="DEMO"),
                toss.argparse.Namespace(command="stock", symbols="DEMO"),
                toss.argparse.Namespace(command="orderbook", symbol="DEMO"),
                toss.argparse.Namespace(command="candles", symbol="DEMO", count=3)]
        for arg in args:
            command = {"price": toss.command_price, "stock": toss.command_stock}.get(arg.command, toss.command_detail)
            with self.subTest(command=arg.command), patch.object(toss, "issue_token", return_value="synthetic"), patch.object(toss, "get", return_value=(200, {"result": cal})) as get, patch.object(toss, "utc_now", return_value=datetime.fromisoformat("2025-06-02T10:00:00-04:00")):
                with self.assertRaises(toss.CheckError):
                    command(arg)
                self.assertEqual([call.args[0] for call in get.call_args_list], ["/api/v1/market-calendar/US"])

    def test_session_ending_between_price_and_reference_requests(self):
        cal = calendar("2025-06-02", "2025-06-02T09:30:00-04:00", "2025-06-02T16:00:00-04:00")
        before = datetime.fromisoformat("2025-06-02T15:59:59-04:00")
        after = datetime.fromisoformat("2025-06-02T16:00:00-04:00")
        responses = [(200, {"result": cal}), (200, {"result": [{"symbol": "DEMO"}]})]
        # Advance time between reads to reproduce a close during an in-flight batch.
        with patch.object(toss, "issue_token", return_value="synthetic"), patch.object(toss, "utc_now", side_effect=[before, before, after]), patch.object(toss, "get", side_effect=responses) as get:
            with self.assertRaises(toss.CheckError):
                toss.command_price(toss.argparse.Namespace(symbols="DEMO"))
        self.assertEqual(len(get.call_args_list), 2)
        self.assertFalse(any('/stocks?' in call.args[0] for call in get.call_args_list))


class FlowTests(unittest.TestCase):
    """Preserve missingness and reject aggregates built from inconsistent evidence."""

    def summary(self, rows, days=2):
        """Freeze the observation date so flow tests never depend on today's clock."""
        return toss.flow_summary(rows, as_of=date(2025, 6, 4), days=days, expected_latest="2025-06-03")

    def test_provisional_excluded_and_zero_preserved(self):
        today = record("2025-06-04", "0", "0", "0")
        today["individual"] = None
        result = self.summary([today, record("2025-06-02"), record("2025-06-03", "0", "0", "0")])
        self.assertEqual(result["totals"]["individual"]["netBuyVolume"], 6)
        self.assertEqual(result["included_dates"], ["2025-06-03", "2025-06-02"])
        self.assertIsNone(result["provisional_records"][0]["individual"])
        self.assertEqual(result["provisional_records"][0]["foreigner"]["netBuyVolume"], "0")
        self.assertTrue(result["latest_date_verified"])
        self.assertFalse(result["consecutive_sessions_verified"])

    def test_null_does_not_become_zero(self):
        row = record("2025-06-03")
        row["institution"] = None
        result = self.summary([row, record("2025-06-02")])
        self.assertIsNone(result["totals"]["institution"])
        self.assertEqual(result["totals"]["foreigner"]["netBuyVolume"], 12)

    def test_invalid_net_fraction_negative_buy(self):
        for buy, sell, net in [("10", "4", "7"), ("10.5", "4", "6.5"), ("-1", "4", "-5")]:
            with self.subTest(buy=buy, net=net):
                result = self.summary([record("2025-06-03", buy, sell, net)], days=1)
                self.assertIsNone(result["totals"]["foreigner"])
                self.assertTrue(result["issues"])

    def test_duplicate_or_future_dates_invalidate_aggregate(self):
        for extra in [record("2025-06-03"), record("2025-06-05"), {"date": "bad"}]:
            result = self.summary([record("2025-06-03"), extra])
            self.assertIsNone(result["totals"]["foreigner"])
            self.assertIn("invalid_duplicate_or_future_date", result["issues"])

    def test_missing_latest_and_insufficient_coverage_are_explicit(self):
        result = self.summary([record("2025-06-02")])
        self.assertFalse(result["latest_date_verified"])
        self.assertIn("insufficient_prior_dates", result["issues"])
        self.assertIn("latest_completed_date_missing_or_unverified", result["issues"])

    def test_flow_rejects_us_and_invalid_count_before_token(self):
        for symbol, days in [("DEMO", 5), ("123456", 100)]:
            with patch.object(toss, "issue_token") as token:
                with self.assertRaises(toss.CheckError):
                    toss.command_flow(toss.argparse.Namespace(symbols=symbol, days=days))
                token.assert_not_called()

    def test_batch_uses_one_token_and_sequential_requests(self):
        cal = calendar("2025-06-04", market="KR")
        cal["previousBusinessDay"]["date"] = "2025-06-03"
        responses = [(200, {"result": cal})] + [(200, {"result": {"records": [record("2025-06-03")], "nextUntil": None}})] * 2
        with patch.object(toss, "issue_token", return_value="synthetic") as token, patch.object(toss, "get", side_effect=responses) as get, patch.object(toss, "utc_now", return_value=datetime.fromisoformat("2025-06-04T10:00:00+09:00")), redirect_stdout(io.StringIO()) as output:
            toss.command_flow(toss.argparse.Namespace(symbols="123456,234567", days=1))
        token.assert_called_once()
        self.assertEqual(len(get.call_args_list), 3)
        result = json.loads(output.getvalue())
        self.assertEqual(len(result["result"]), 2)
        self.assertEqual(result["result"][0]["totals"]["foreigner"]["netBuyVolume"], 6)


class QuoteAndCandleTests(unittest.TestCase):
    """Exercise quote ordering, invalid levels and market-local candle dates."""

    def test_unsorted_best_quotes_and_invalid_levels(self):
        levels = [{"price": "103", "volume": "3"}, {"price": "101", "volume": "2"},
                  {"price": "100", "volume": "0"}, {"price": "NaN", "volume": "1"}]
        self.assertEqual(toss.best_quote(levels, side="asks")["price"], "101")
        self.assertEqual(toss.best_quote(levels, side="bids")["price"], "103")
        self.assertIsNone(toss.best_quote([], side="bids"))

    def test_daily_midnight_is_not_a_completed_current_bar(self):
        rows = [{"timestamp": "2025-06-04T00:00:00+09:00"}, {"timestamp": "2025-06-03T00:00:00+09:00"}]
        result = toss.split_daily_candles(rows, date(2025, 6, 4), "KR")
        self.assertEqual(result["prior_date_candles"], rows[1:])
        self.assertEqual(result["excluded_today_or_future"], rows[:1])

    def test_us_daily_bars_use_exchange_date(self):
        rows = [{"timestamp": "2025-06-04T00:00:00-04:00"}]
        self.assertFalse(toss.split_daily_candles(rows, date(2025, 6, 4), "US")["prior_date_candles"])

    def test_duplicate_candle_rejected(self):
        row = {"timestamp": "2025-06-03T00:00:00+09:00"}
        with self.assertRaises(toss.CheckError):
            toss.split_daily_candles([row, row], date(2025, 6, 4), "KR")

    def test_incomplete_symbol_snapshot_rejected(self):
        for rows in [[], [{"symbol": "DEMO"}, {"symbol": "DEMO"}], [{"symbol": "OTHER"}]]:
            with self.assertRaises(toss.CheckError):
                toss.checked_items({"result": rows}, "DEMO")


class PrivacyAndCliTests(unittest.TestCase):
    """Check credential-free CLI paths and safe failure output with synthetic inputs."""

    def test_symbol_validation_and_alphanumeric_kr(self):
        self.assertEqual(toss.validate_symbols("1234A0,demo"), ["1234A0", "DEMO"])
        self.assertTrue(toss.KR_SYMBOL_RE.fullmatch("1234A0"))
        for symbols in ["", "DEMO,", "DEMO,DEMO", "DEMO/PRIVATE", ",".join(str(i) for i in range(201))]:
            with self.assertRaises(toss.CheckError):
                toss.validate_symbols(symbols)

    def test_workspace_selected_at_runtime(self):
        # Isolate both filesystem markers and environment overrides from the real host.
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=True):
            root = Path(temp)
            (root / "scripts").mkdir()
            (root / "scripts" / "toss_openapi_check.py").touch()
            (root / "data").mkdir()
            with patch.object(Path, "cwd", return_value=root):
                self.assertEqual(toss.resolve_workspace_root(), root.resolve())
            with patch.dict(os.environ, {toss.WORKSPACE_ENV: temp}):
                self.assertEqual(toss.resolve_workspace_root(), root.resolve())

    def test_help_does_not_read_credentials_or_discover_workspace(self):
        with patch("sys.argv", ["check", "--help"]), patch.object(toss, "resolve_workspace_root") as root, redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                toss.main()
        self.assertEqual(result.exception.code, 0)
        root.assert_not_called()

    def test_missing_keychain_binary_returns_unavailable(self):
        with patch.object(toss.shutil, "which", return_value=None):
            self.assertIsNone(toss.keychain_value("SYNTHETIC_CREDENTIAL"))

    def test_unsafe_base_url_rejected_without_echo(self):
        with patch.dict(os.environ, {"TOSS_INVEST_BASE_URL": "https://private-user:synthetic@example.test"}):
            with self.assertRaises(toss.CheckError) as result:
                toss.base_url()
        self.assertNotIn("private-user", str(result.exception))

    def test_http_failure_omits_body_and_redirects(self):
        exc = error.HTTPError("https://example.test", 403, "synthetic", {}, io.BytesIO(b"private payload"))
        with patch.object(toss.request.OpenerDirector, "open", side_effect=exc):
            self.assertEqual(toss.http_json("GET", "https://example.test"), (403, {}))
        self.assertIsNone(toss.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.test"))

    def test_trading_write_blocked_before_network(self):
        with patch.object(toss.request, "build_opener") as opener:
            with self.assertRaises(toss.CheckError):
                toss.http_json("POST", "https://example.test/api/v1/orders")
            opener.assert_not_called()

    def test_cli_returns_nonzero_without_path_or_error_payload(self):
        with patch("sys.argv", ["check", "market"]), patch.object(toss, "resolve_workspace_root", side_effect=OSError("synthetic private location")), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(toss.main(), 1)
        self.assertFalse(json.loads(output.getvalue())["ok"])
        self.assertNotIn("synthetic private location", output.getvalue())


if __name__ == "__main__":
    unittest.main()
