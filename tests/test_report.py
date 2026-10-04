"""Rendered detailed report: content rules, immutability, real snapshots."""
import json, re, shutil, subprocess, tempfile, unittest
from pathlib import Path
from stockdy import core
from tests.helpers import OfflineTestCase, snapshot

ROOT = core.ROOT


def text_of(path):
    page = Path(path).read_text(encoding="utf-8")
    body = page.split("</style>", 1)[1].split("<script>", 1)[0]
    return " ".join(re.sub("<[^>]+>", " ", body).split()), page


class ReportTest(OfflineTestCase):
    def setUp(self):
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, self.tmp)

    def render(self, data, name="r.html"):
        out = self.tmp / name
        core.build_report(data, out)
        return text_of(out)

    def test_ttm_valuation_and_quarter_growth(self):
        text, _ = self.render(snapshot(price=150))
        self.assertIn("PER 11.8배", text)                     # 1,500 cap / TTM 127
        self.assertIn("최근 12개월(TTM)", text)
        self.assertIn("매출 +100.0% · EPS +100.0%", text)       # 200 vs 100, 280 vs 140
        self.assertIn("52주", text)
        self.assertIn("부채비율", text)

    def test_without_price_nothing_is_compared(self):
        text, _ = self.render(snapshot())
        self.assertIn("기준일 주가 미확인", text)
        self.assertIn("기준일 종가가 없어 주가와 비교하지 않습니다", text)
        self.assertNotIn("종가 대비", text)

    def test_removed_placeholders_stay_removed(self):
        text, _ = self.render(snapshot(price=150))
        for gone in ("투자 일기", "동일일 주가 미수집", "투자 판단 사용자 결정"):
            self.assertNotIn(gone, text)

    def test_forward_per_needs_a_source(self):
        text, _ = self.render(snapshot(price=150))
        self.assertIn("Forward PER: 출처 있는 이익 추정 없음", text)

    def test_consensus_preferred_and_guidance_kept_as_second(self):
        naver = {"consensus": {"year": 2026, "eps": 300, "revenue": 1, "prior_revenue": 1}, "source_url": "https://m.stock.naver.com/x"}
        analysis = {"valuation": {"scenarios": {"base": {"profit_growth": 0.1, "pe": 10}},
                                  "forward": {"year": 2026, "basis": "guidance", "net_income": 150, "note": "계산식"}}}
        text, _ = self.render(snapshot(price=150, naver=naver, analysis=analysis))
        self.assertIn("Forward PER 0.5배 (2026E 컨센서스 EPS 300원, FnGuide)", text)
        self.assertIn("회사 가이던스 기반 추정", text)
        self.assertLess(text.index("컨센서스 EPS"), text.index("회사 가이던스 기반"))

    def test_analysis_forward_without_basis_is_ignored(self):
        analysis = {"valuation": {"forward": {"year": 2026, "net_income": 150}}}
        text, _ = self.render(snapshot(price=150, analysis=analysis))
        self.assertIn("출처 있는 이익 추정 없음", text)

    def test_market_section_only_with_data(self):
        text, _ = self.render(snapshot(price=150))
        self.assertNotIn("시장 평가", text)
        naver = {"target": {"price_target_mean": 300, "recomm_mean": 4, "date": "2026-10-01"},
                 "flows": [{"date": "2026-10-02", "foreign": 5, "institution": -3, "individual": -2, "foreign_hold_ratio": "1%"}],
                 "peers": [{"ticker": "000001", "name": "피어", "close": 10, "market_cap": 1e10, "forward_per": 12.0, "forward_year": 2026}],
                 "research": [{"broker": "A증권", "title": "리포트", "date": "2026-09-07", "url": "https://stock.naver.com/research/company/1"}],
                 "source_url": "https://m.stock.naver.com/x", "note": "n", "errors": []}
        text, _ = self.render(snapshot(price=150, naver=naver), "m.html")
        self.assertIn("시장 평가", text)
        self.assertIn("종가 대비 +100%", text)
        self.assertIn("외국인 +5주", text)
        self.assertIn("12.0배 (2026E)", text)

    def test_checkpoints_rendered(self):
        analysis = {"checkpoints": [{"item": "이익률", "current": "25%", "break_signal": "20% 미만", "next_check": "3Q"}]}
        text, _ = self.render(snapshot(price=150, analysis=analysis))
        self.assertIn("가설 점검표", text)
        self.assertIn("20% 미만", text)

    def test_user_text_is_escaped(self):
        analysis = {"thesis": "<script>alert(1)</script>"}
        _, page = self.render(snapshot(analysis=analysis))
        self.assertNotIn("<script>alert(1)</script>", page)

    def test_dated_report_is_immutable(self):
        out = self.tmp / "2026-10-04.html"
        core.build_report(snapshot(price=150), out)
        core.build_report(snapshot(price=150), out)          # identical rerun is fine
        with self.assertRaises(FileExistsError):
            core.build_report(snapshot(price=160), out)
        latest = self.tmp / "latest.html"
        core.build_report(snapshot(price=150), latest)
        core.build_report(snapshot(price=160), latest)       # latest may change

    def test_unsourced_metric_is_rejected(self):
        data = snapshot()
        data["reports"] = [{"year": 2025, "report": "annual", "metrics": {"revenue": 1}}]
        with self.assertRaises(ValueError):
            core.build_report(data, self.tmp / "x.html")

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_page_script_parses(self):
        _, page = self.render(snapshot(price=150))
        script = self.tmp / "s.js"
        script.write_text(page.split("<script>", 1)[1].split("</script>", 1)[0], encoding="utf-8")
        subprocess.run(["node", "--check", str(script)], check=True)


class StoredSnapshotsTest(OfflineTestCase):
    """Every committed snapshot must still render with the current generator."""
    def test_all_snapshots_render(self):
        tmp = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, tmp)
        paths = sorted(ROOT.glob("data/requests/*/snapshot.json")) + sorted(ROOT.glob("data/sec/*.json"))
        self.assertTrue(paths)
        for i, path in enumerate(paths):
            with self.subTest(snapshot=str(path.relative_to(ROOT))):
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("company", {}).get("ticker") == "278470":
                    data["analysis"] = json.loads((ROOT / "analysis/apr.json").read_text(encoding="utf-8"))
                core.build_report(data, tmp / f"{i}.html")


if __name__ == "__main__":
    unittest.main()
