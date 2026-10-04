"""Normalization of DART rows and the valuation earnings base."""
import unittest
from stockdy import core
from tests.helpers import OfflineTestCase, interim_rows, annual_rows


def normalized(year, report, rows):
    r = {"year": year, "report": report, "items": rows}
    core.normalize_accounts({"reports": [r]})
    return r


class NormalizeTest(OfflineTestCase):
    def test_interim_separates_quarter_ytd_and_prior_year(self):
        r = normalized(2026, "2Q", interim_rows())
        self.assertEqual(r["metrics"]["revenue"], 200)            # quarter alone
        self.assertEqual(r["ytd_metrics"]["revenue"], 380)        # Jan–Jun
        self.assertEqual(r["prior_metrics"]["quarter"]["revenue"], 100)
        self.assertEqual(r["prior_metrics"]["ytd"]["net_income_parent"], 27)
        self.assertEqual(r["metrics"]["eps"], 280)
        self.assertEqual(r["metrics"]["eps_basis"], "희석")
        self.assertEqual(r["ytd_metrics"]["eps"], 540)
        self.assertEqual(r["prior_metrics"]["quarter"]["eps"], 140)
        self.assertEqual(r["prior_metrics"]["ytd"]["eps"], 270)

    def test_interim_cash_flow_is_not_treated_as_quarter(self):
        r = normalized(2026, "2Q", interim_rows())
        self.assertIsNone(r["standalone_metrics"]["operating_cash_flow"])
        self.assertEqual(r["ytd_metrics"]["operating_cash_flow"], 60)

    def test_balance_sheet_and_source(self):
        r = normalized(2026, "2Q", interim_rows())
        self.assertEqual(r["instant_metrics"]["liabilities"], 500)
        self.assertEqual(r["instant_metrics"]["equity_parent"], 950)
        self.assertTrue(r["source_url"].endswith("20260814000001"))

    def test_first_quarter_uses_quarter_as_ytd(self):
        rows = [x for x in interim_rows()]
        for x in rows: x["thstrm_add_amount"] = None; x["frmtrm_add_amount"] = None
        r = normalized(2026, "1Q", rows)
        self.assertEqual(r["ytd_metrics"]["revenue"], 200)
        self.assertEqual(r["prior_metrics"]["ytd"]["revenue"], 100)
        self.assertEqual(r["prior_metrics"]["ytd"]["eps"], 140)

    def test_basic_eps_used_when_diluted_missing(self):
        rows = [x for x in interim_rows() if "Diluted" not in x["account_id"]]
        rows.append({**interim_rows()[4], "account_id": "ifrs-full_BasicEarningsLossPerShare", "account_nm": "보통주 기본주당이익"})
        r = normalized(2026, "2Q", rows)
        self.assertEqual(r["metrics"]["eps_basis"], "기본")
        self.assertEqual(r["prior_metrics"]["quarter"]["eps"], 140)


class EarningsBaseTest(OfflineTestCase):
    def reports(self, with_interim=True):
        out = [normalized(2025, "annual", annual_rows())]
        if with_interim: out.append(normalized(2026, "2Q", interim_rows()))
        return out

    def test_ttm_when_next_year_interim_exists(self):
        base = core.earnings_base(self.reports())
        self.assertEqual(base["kind"], "ttm")
        self.assertEqual(base["net"], 100 + 54 - 27)
        self.assertEqual(base["eps"], 1000 + 540 - 270)
        self.assertIn("TTM", base["label"])

    def test_annual_fallback(self):
        base = core.earnings_base(self.reports(with_interim=False))
        self.assertEqual(base["kind"], "annual")
        self.assertEqual(base["net"], 100)

    def test_ttm_eps_dropped_when_eps_basis_differs(self):
        reports = self.reports()
        reports[1]["metrics"]["eps_basis"] = "기본"
        base = core.earnings_base(reports)
        self.assertEqual(base["net"], 127)
        self.assertIsNone(base["eps"])

    def test_no_annual(self):
        self.assertIsNone(core.earnings_base([])["net"])


class SmallHelpersTest(unittest.TestCase):
    def test_num_parsing(self):
        self.assertEqual(core._num("+11,863"), 11863)
        self.assertEqual(core._num("15,273", 1e8), 1527300000000)
        self.assertIsNone(core._num("-"))
        self.assertIsNone(core._num(None))

    def test_scenario_values(self):
        v = core.scenario_values(100, 10, {"base": {"profit_growth": 0.1, "pe": 10}})
        self.assertAlmostEqual(v["base"]["value_per_share"], 100 * 1.21 * 10 / 10)
        self.assertIsNone(core.scenario_values(None, 10, {}))

    def test_pct(self):
        self.assertEqual(core.pct(0.1234), "+12.3%")
        self.assertEqual(core.pct(None), "N/A")


if __name__ == "__main__":
    unittest.main()
