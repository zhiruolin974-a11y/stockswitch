import unittest
from dataclasses import replace
from datetime import timedelta

from src.market.calendar import ChinaAMarketRules
from src.market.fake import FakeMarketDataProvider
from src.market.models import MarketDataError, MarketDataStale
from src.market.provider import INDEX_SYMBOLS
from src.market.tencent import parse_tencent_batch, validate_symbol
from tests.helpers import OPEN, frame, quote


class MarketTests(unittest.TestCase):
    def test_quote_age(self):
        self.assertEqual(quote().age_seconds(OPEN), 0)

    def test_quote_invalid_price(self):
        with self.assertRaises(ValueError):
            replace(quote(), last_price=0)

    def test_quote_stale(self):
        with self.assertRaises(MarketDataStale):
            quote().require_fresh(OPEN + timedelta(seconds=21), 20)

    def test_fake_deterministic_sequence(self):
        fake = FakeMarketDataProvider([frame(10), frame(11)])
        fake.connect()
        self.assertEqual(fake.get_quote("sz000001").last_price, 10)
        fake.advance()
        self.assertEqual(fake.get_quote("sz000001").last_price, 11)

    def test_fake_provider_failure(self):
        fake = FakeMarketDataProvider([frame()], fail_at=1)
        fake.connect()
        fake.get_quote("sz000001")
        with self.assertRaises(MarketDataError):
            fake.get_quote("sz000001")

    def test_index_quotes(self):
        fake = FakeMarketDataProvider([frame()])
        fake.connect()
        self.assertEqual(set(fake.get_index_quotes()), set(INDEX_SYMBOLS))

    def test_market_hours_and_lunch(self):
        rules = ChinaAMarketRules()
        self.assertTrue(rules.can_trade(OPEN))
        self.assertEqual(rules.state(OPEN.replace(hour=12)), "Lunch Break")
        self.assertFalse(rules.can_trade(OPEN.replace(hour=15)))
        self.assertFalse(rules.can_trade(OPEN + timedelta(days=5)))

    def test_symbols_reject_non_a_shares(self):
        self.assertEqual(validate_symbol(" SZ000001 "), "sz000001")
        self.assertEqual(validate_symbol("600519"), "sh600519")
        self.assertEqual(validate_symbol("000300", allow_index=True), "sh000300")
        with self.assertRaises(ValueError):
            validate_symbol("../bad")

    def test_tencent_batch_parser(self):
        fields = ["0"] * 40
        fields[1], fields[3], fields[4], fields[5] = "平安银行", "11.3", "11.0", "11.1"
        fields[6], fields[30], fields[33], fields[34], fields[37] = "100", "20260928100000", "11.4", "10.9", "200"
        raw = ('v_sz000001="' + "~".join(fields) + '";').encode("gb18030")
        parsed = parse_tencent_batch(raw, ("sz000001",), OPEN)["sz000001"]
        self.assertEqual(parsed.volume, 10000)
        self.assertEqual(parsed.turnover, 2_000_000)
        self.assertTrue(parsed.is_delayed)
        with self.assertRaises(MarketDataError):
            parse_tencent_batch(raw, ("sh600519",), OPEN)
