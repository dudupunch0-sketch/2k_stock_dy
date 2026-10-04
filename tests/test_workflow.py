"""Request processing, universe edits, weekly report and delta."""
import json, os, shutil, tempfile, unittest
from pathlib import Path
from unittest import mock
from stockdy import universe, workflow, weekly, delta
from tests.helpers import OfflineTestCase

UNIVERSE = {"schema_version": 1, "limits": {"holdings": 3, "watchlist": 2},
            "holdings": [{"ticker": "278470", "name": "에이피알", "market": "KRX", "corp_code": "01190568", "currency": "KRW"}],
            "watchlist": [], "validation_fixtures": [{"ticker": "AAPL"}]}


class TempRepo(OfflineTestCase):
    def setUp(self):
        super().setUp()
        self.root = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, self.root)
        (self.root / "config").mkdir(); (self.root / "requests").mkdir()
        (self.root / "config/universe.json").write_text(json.dumps(UNIVERSE, ensure_ascii=False), encoding="utf-8")

    def request(self, rid, **fields):
        path = self.root / "requests" / f"{rid}.json"
        path.write_text(json.dumps({"request_id": rid, "status": "pending", **fields}, ensure_ascii=False), encoding="utf-8")
        return path

    def read(self, path): return json.loads(path.read_text(encoding="utf-8"))


def fake_collect(key, target, **kw):
    data = {"schema_version": 1, "company": {"ticker": kw["stock"], "name": kw["company_name"], "currency": "KRW"},
            "as_of": "2026-10-04", "collected_at": "t", "source_status": "success", "reports": [],
            "sources": [{"url": "https://opendart.fss.or.kr/"}], "market": {}, "analysis": {}, "corp": kw["corp"]}
    target.parent.mkdir(parents=True, exist_ok=True); target.write_text(json.dumps(data), encoding="utf-8")
    return data


class WorkflowTest(TempRepo):
    def run_workflow(self, collect=fake_collect, resolver=None):
        resolver = resolver or mock.Mock(return_value=("00126380", "삼성전자"))
        with mock.patch.object(workflow, "ROOT", self.root), mock.patch.object(workflow, "collect_apr", side_effect=collect) as c, \
             mock.patch.object(workflow, "resolve_corp_code", resolver), mock.patch.dict(os.environ, {"DART_API_KEY": "k"}):
            try: workflow.main(); failed = False
            except SystemExit: failed = True
        return c, resolver, failed

    def test_tracked_ticker_is_collected_with_history_packet(self):
        req = self.request("apr-1", ticker="278470", market="KRX", kind="tracked")
        c, _, failed = self.run_workflow()
        self.assertFalse(failed)
        r = self.read(req)
        self.assertEqual(r["status"], "fulfilled")
        self.assertTrue((self.root / r["evidence_packet"]).exists())
        self.assertEqual(c.call_args.kwargs["corp"], "01190568")

    def test_manual_request_resolves_corp_code(self):
        req = self.request("sec-1", ticker="005930", market="KRX", kind="detailed", user_requested=True, company_name="삼성전자")
        c, resolver, failed = self.run_workflow()
        self.assertFalse(failed)
        resolver.assert_called_once_with("005930", "k")
        self.assertEqual(c.call_args.kwargs["corp"], "00126380")
        self.assertEqual(self.read(req)["corp_code"], "00126380")

    def test_unlisted_automatic_request_rejected(self):
        req = self.request("x-1", ticker="005930", market="KRX", kind="tracked")
        c, _, _ = self.run_workflow()
        self.assertEqual(self.read(req)["status"], "rejected")
        c.assert_not_called()

    def test_invalid_ticker_rejected(self):
        req = self.request("bad-1", ticker="../etc", market="KRX", kind="detailed", user_requested=True)
        self.run_workflow()
        self.assertEqual(self.read(req)["status"], "rejected")

    def test_fulfilled_request_is_skipped(self):
        self.request("done-1", ticker="278470", market="KRX", status="fulfilled")
        c, _, _ = self.run_workflow()
        c.assert_not_called()

    def test_collection_failure_marks_failed_and_exits(self):
        req = self.request("apr-2", ticker="278470", market="KRX")
        _, _, failed = self.run_workflow(collect=mock.Mock(side_effect=RuntimeError("OpenDART request failed")))
        self.assertTrue(failed)
        r = self.read(req)
        self.assertEqual(r["status"], "failed")
        self.assertIn("OpenDART", r["error"])

    def test_invalid_request_id_stops(self):
        self.request("bad id!", ticker="278470", market="KRX")
        with mock.patch.object(workflow, "ROOT", self.root), self.assertRaises(SystemExit):
            workflow.main()


class UniverseTest(TempRepo):
    def path(self): return self.root / "config/universe.json"

    def test_add_move_remove(self):
        p = self.path()
        self.assertEqual(universe.add("192820", "코스맥스", "KRX", path=p)["status"], "added")
        self.assertEqual(universe.add("192820", "코스맥스", "KRX", path=p)["status"], "unchanged")
        self.assertEqual(universe.add("192820", "코스맥스", "KRX", "holdings", path=p)["status"], "moved")
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual([x["ticker"] for x in data["holdings"]], ["278470", "192820"])
        self.assertEqual(data["watchlist"], [])
        self.assertEqual(universe.remove("192820", path=p)["status"], "removed")
        self.assertEqual(universe.remove("192820", path=p)["status"], "not_found")
        self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["validation_fixtures"], [{"ticker": "AAPL"}])

    def test_validation_and_limits(self):
        p = self.path()
        for args in (("19282", "x", "KRX"), ("NVDA", "x", "KOSPI"), ("nvda!", "x", "NASDAQ")):
            with self.assertRaises(ValueError): universe.add(*args, path=p)
        with self.assertRaises(ValueError): universe.add("005930", "x", "KRX", corp_code="123", path=p)
        universe.add("000001", "a", "KRX", path=p); universe.add("000002", "b", "KRX", path=p)
        with self.assertRaises(ValueError): universe.add("000003", "c", "KRX", path=p)
        self.assertEqual(universe.add("NVDA", "엔비디아", "NASDAQ", "holdings", path=p)["status"], "added")


class WeeklyTest(OfflineTestCase):
    def setUp(self):
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, self.tmp)
        patcher = mock.patch.object(weekly, "_tracked_tickers", return_value={"278470"}); patcher.start(); self.addCleanup(patcher.stop)

    def data(self, **extra):
        base = {"week_ending": "2026-10-09", "period_start": "2026-10-03", "status": "success", "summary": "요약",
                "coverage": [{"ticker": "278470", "status": "success"}],
                "changes": [{"ticker": "278470", "category": "news", "published_at": "2026-10-05", "headline": "h", "summary": "s", "source": "https://e.com/a"}],
                "upcoming_events": [], "unverified_or_unavailable": []}
        base.update(extra); return base

    def test_success_updates_latest(self):
        out = weekly.build_weekly_report(self.data(), self.tmp / "2026-10-09.html")
        self.assertTrue((self.tmp / "latest.html").exists())
        self.assertIn("상태: success", out.read_text(encoding="utf-8"))

    def test_invalid_rows_make_partial_and_keep_latest(self):
        bad = self.data(changes=[{"ticker": "278470", "category": "news", "published_at": "2026-09-01", "source": "https://e.com"},
                                 {"ticker": "005930", "category": "news", "published_at": "2026-10-05", "source": "https://e.com"},
                                 {"ticker": "278470", "category": "rumor", "published_at": "2026-10-05", "source": "https://e.com"},
                                 {"ticker": "278470", "category": "news", "published_at": "2026-10-05", "source": "javascript:x"}])
        page = weekly.build_weekly_report(bad, self.tmp / "2026-10-09.html").read_text(encoding="utf-8")
        self.assertIn("상태: partial", page)
        self.assertEqual(page.count("보고서에서 제외"), 4)
        self.assertFalse((self.tmp / "latest.html").exists())

    def test_missing_coverage_is_partial(self):
        page = weekly.build_weekly_report(self.data(coverage=[]), self.tmp / "a.html").read_text(encoding="utf-8")
        self.assertIn("상태: partial", page)

    def test_period_longer_than_week_rejected(self):
        with self.assertRaises(ValueError):
            weekly.build_weekly_report(self.data(period_start="2026-09-01"), self.tmp / "b.html")

    def test_dated_weekly_is_immutable(self):
        out = self.tmp / "2026-10-09.html"
        weekly.build_weekly_report(self.data(), out)
        with self.assertRaises(FileExistsError):
            weekly.build_weekly_report(self.data(summary="다름"), out)


class DeltaTest(unittest.TestCase):
    def test_changes_and_new_periods(self):
        old = {"as_of": "a", "periods": [{"year": 2025, "report": "annual", "metrics": {"revenue": 1, "eps": 2}}]}
        new = {"as_of": "b", "company": {"ticker": "278470"}, "periods": [
            {"year": 2025, "report": "annual", "metrics": {"revenue": 1, "eps": 3}},
            {"year": 2026, "report": "2Q", "metrics": {"revenue": 5}}]}
        d = delta.compare(old, new)
        self.assertEqual(d["ticker"], "278470")
        kinds = sorted(x.get("type", x.get("metric")) for x in d["changes"])
        self.assertEqual(kinds, ["eps", "new_period"])


if __name__ == "__main__":
    unittest.main()
