"""External source adapters, with every network call replaced by fixtures."""
import io, unittest, zipfile
from unittest import mock
from stockdy import core
from tests.helpers import OfflineTestCase, NAVER_ANNUAL, NAVER_INTEGRATION


def chart(price=270000.0, currency="KRW"):
    return {"chart": {"result": [{"meta": {"regularMarketPrice": price, "regularMarketTime": 1790922625, "gmtoffset": 32400,
                                           "currency": currency, "fiftyTwoWeekHigh": 306500.0, "fiftyTwoWeekLow": 141000.0}}]}}


class QuoteTest(OfflineTestCase):
    def test_close_and_market_cap(self):
        with mock.patch.object(core, "fetch_json", return_value=chart()):
            q = core.fetch_quote("192820.KS", 100, "KRW")
        self.assertEqual(q["price"], 270000.0)
        self.assertEqual(q["market_cap"], 27000000.0)
        self.assertEqual(q["price_date"], "2026-10-02")      # KST date of the stamp
        self.assertEqual(q["week52_low"], 141000.0)

    def test_currency_mismatch_is_not_used(self):
        with mock.patch.object(core, "fetch_json", return_value=chart(currency="USD")):
            q = core.fetch_quote("X", 1, "KRW")
        self.assertIsNone(q["price"])
        self.assertIn("통화", q["note"])

    def test_failure_returns_na(self):
        with mock.patch.object(core, "fetch_json", side_effect=OSError("down")):
            q = core.fetch_quote("X", 1, "KRW")
        self.assertIsNone(q["price"])
        self.assertIn("실패", q["note"])
        self.assertIsNone(core.fetch_quote("")["price"])


class NaverTest(OfflineTestCase):
    def fake(self, url, headers=None):
        if url.endswith("/finance/annual"): return NAVER_ANNUAL
        if url.endswith("/integration"): return NAVER_INTEGRATION
        raise AssertionError(url)

    def test_consensus_parsing(self):
        with mock.patch.object(core, "fetch_json", side_effect=self.fake):
            c = core.naver_consensus("278470")
        self.assertEqual(c["year"], 2026)
        self.assertEqual(c["eps"], 15763)
        self.assertEqual(c["revenue"], 3086100000000)
        self.assertIsNone(c["net_income_parent"])              # "-" stays missing
        self.assertEqual(c["net_income"], 592400000000)
        self.assertEqual(c["prior_eps"], 7704)

    def test_full_fetch(self):
        with mock.patch.object(core, "fetch_json", side_effect=self.fake):
            n = core.fetch_naver("278470")
        self.assertEqual(n["errors"], [])
        self.assertEqual(n["target"]["price_target_mean"], 538182)
        self.assertEqual(n["flows"][0]["foreign"], 11863)
        self.assertEqual(n["flows"][0]["date"], "2026-10-02")
        self.assertEqual([p["ticker"] for p in n["peers"]], ["090430"])   # self excluded
        self.assertEqual(n["peers"][0]["market_cap"], 7750290 * 1e6)
        self.assertTrue(n["research"][0]["url"].startswith("https://stock.naver.com/research/company/"))

    def test_failures_are_recorded_not_raised(self):
        with mock.patch.object(core, "fetch_json", side_effect=OSError("blocked")):
            n = core.fetch_naver("278470")
        self.assertIsNone(n["consensus"])
        self.assertEqual(len(n["errors"]), 2)
        self.assertEqual(core.fetch_naver("AAPL")["errors"], ["국내 6자리 종목만 지원"])


class DartTest(OfflineTestCase):
    def test_api_key_never_in_error(self):
        with mock.patch.object(core, "fetch_json", side_effect=OSError("https://x?crtfc_key=SECRET123")):
            with self.assertRaises(RuntimeError) as ctx:
                core.dart_json("list", {}, "SECRET123")
        self.assertNotIn("SECRET123", str(ctx.exception))
        self.assertIsNone(ctx.exception.__cause__)

    def corp_zip(self):
        xml = "<result><list><corp_code>00126380</corp_code><corp_name>삼성전자</corp_name><stock_code>005930</stock_code></list>" \
              "<list><corp_code>99999999</corp_code><corp_name>비상장</corp_name><stock_code> </stock_code></list></result>"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z: z.writestr("CORPCODE.xml", xml.encode())
        return buf.getvalue()

    def test_corp_code_lookup(self):
        class Resp(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False
        body = self.corp_zip()
        with mock.patch("urllib.request.urlopen", side_effect=lambda *a, **k: Resp(body)):
            self.assertEqual(core.resolve_corp_code("005930", "k"), ("00126380", "삼성전자"))
            with self.assertRaises(ValueError):
                core.resolve_corp_code("000000", "k")

    def test_corp_code_failure_hides_key(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("crtfc_key=SECRET123")):
            with self.assertRaises(RuntimeError) as ctx:
                core.resolve_corp_code("005930", "SECRET123")
        self.assertNotIn("SECRET123", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
