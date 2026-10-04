"""Shared fixtures. Tests never touch the network: OfflineTestCase blocks urlopen."""
from __future__ import annotations
import copy, unittest
from unittest import mock


class OfflineTestCase(unittest.TestCase):
    def setUp(self):
        blocker = mock.patch("urllib.request.urlopen", side_effect=AssertionError("network access in tests"))
        blocker.start()
        self.addCleanup(blocker.stop)


def row(sj, account_id, name, thstrm, add=None, frm_q=None, frm_add=None, rcept="20260814000001"):
    """One OpenDART fnlttSinglAcntAll row; amounts as DART strings."""
    s = lambda v: None if v is None else str(v)
    return {"sj_div": sj, "account_id": account_id, "account_nm": name, "thstrm_amount": s(thstrm),
            "thstrm_add_amount": s(add), "frmtrm_q_amount": s(frm_q), "frmtrm_add_amount": s(frm_add), "rcept_no": rcept}


def annual_rows(rcept="20260320000001"):
    return [
        row("CIS", "ifrs-full_Revenue", "매출액", 700, rcept=rcept),
        row("CIS", "dart_OperatingIncomeLoss", "영업이익", 140, rcept=rcept),
        row("CIS", "ifrs-full_ProfitLoss", "당기순이익", 105, rcept=rcept),
        row("CIS", "ifrs-full_ProfitLossAttributableToOwnersOfParent", "지배기업 소유주", 100, rcept=rcept),
        row("CIS", "ifrs-full_DilutedEarningsLossPerShare", "보통주 희석주당이익", 1000, rcept=rcept),
        row("CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름", 120, rcept=rcept),
        row("CF", "ifrs-full_PurchaseOfPropertyPlantAndEquipment", "유형자산의 취득", 20, rcept=rcept),
        row("BS", "ifrs-full_Liabilities", "부채총계", 400, rcept=rcept),
        row("BS", "ifrs-full_Equity", "자본총계", 900, rcept=rcept),
        row("BS", "ifrs-full_EquityAttributableToOwnersOfParent", "지배기업 소유주지분", 850, rcept=rcept),
        row("BS", "ifrs-full_Assets", "자산총계", 1300, rcept=rcept),
        row("BS", "ifrs-full_CashAndCashEquivalents", "현금및현금성자산", 90, rcept=rcept),
    ]


def interim_rows():
    """2Q: quarter / YTD / prior-year quarter / prior-year YTD."""
    return [
        row("CIS", "ifrs-full_Revenue", "매출액", 200, 380, 100, 190),
        row("CIS", "dart_OperatingIncomeLoss", "영업이익", 40, 76, 20, 38),
        row("CIS", "ifrs-full_ProfitLoss", "당기순이익", 30, 57, 15, 28),
        row("CIS", "ifrs-full_ProfitLossAttributableToOwnersOfParent", "지배기업 소유주", 28, 54, 14, 27),
        row("CIS", "ifrs-full_DilutedEarningsLossPerShare", "보통주 희석주당이익", 280, 540, 140, 270),
        row("CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름", 60),
        row("BS", "ifrs-full_Liabilities", "부채총계", 500),
        row("BS", "ifrs-full_Equity", "자본총계", 1000),
        row("BS", "ifrs-full_EquityAttributableToOwnersOfParent", "지배기업 소유주지분", 950),
        row("BS", "ifrs-full_Assets", "자산총계", 1500),
        row("BS", "ifrs-full_CashAndCashEquivalents", "현금및현금성자산", 100),
    ]


def snapshot(price=None, naver=None, analysis=None, shares=10):
    """Raw snapshot as collect_apr stores it before rendering (items, empty metrics)."""
    data = {
        "schema_version": 1, "kind": "detailed", "as_of": "2026-10-04", "collected_at": "2026-10-04T00:00:00+00:00",
        "source_status": "success",
        "company": {"name": "테스트", "ticker": "123456", "market": "KRX", "currency": "KRW",
                    "shares_outstanding": shares, "shares_as_of": "2025-12-31"},
        "reports": [
            {"year": 2024, "report": "annual", "metrics": {}, "items": annual_rows("20250320000001")},
            {"year": 2025, "report": "annual", "metrics": {}, "items": annual_rows()},
            {"year": 2026, "report": "2Q", "metrics": {}, "items": interim_rows()},
        ],
        "sources": [{"name": "OpenDART", "url": "https://opendart.fss.or.kr/"}],
        "market": {"price": price, "price_date": "2026-10-02" if price else None,
                   "market_cap": price * shares if price else None, "week52_high": 200, "week52_low": 100, "note": "test"},
        "analysis": analysis or {},
    }
    if naver: data["naver"] = naver
    return copy.deepcopy(data)


NAVER_ANNUAL = {"financeInfo": {
    "trTitleList": [{"isConsensus": "N", "title": "2025.12.", "key": "202512"}, {"isConsensus": "Y", "title": "2026.12.", "key": "202612"}],
    "rowList": [
        {"title": "매출액", "columns": {"202512": {"value": "15,273"}, "202612": {"value": "30,861"}}},
        {"title": "영업이익", "columns": {"202512": {"value": "3,655"}, "202612": {"value": "7,669"}}},
        {"title": "당기순이익", "columns": {"202512": {"value": "2,897"}, "202612": {"value": "5,924"}}},
        {"title": "지배주주순이익", "columns": {"202512": {"value": "2,897"}, "202612": {"value": "-"}}},
        {"title": "EPS", "columns": {"202512": {"value": "7,704"}, "202612": {"value": "15,763"}}},
        {"title": "PER", "columns": {"202512": {"value": "29.98"}, "202612": {"value": "23.22"}}},
    ]}}

NAVER_INTEGRATION = {
    "consensusInfo": {"itemCode": "278470", "createDate": "2026-10-01", "recommMean": "4.00", "priceTargetMean": "538,182"},
    "dealTrendInfos": [{"bizdate": "20261002", "foreignerPureBuyQuant": "+11,863", "organPureBuyQuant": "-18,746",
                        "individualPureBuyQuant": "+6,587", "foreignerHoldRatio": "38.39%", "closePrice": "367,000"}],
    "researches": [{"id": 96022, "bnm": "SK증권", "tit": "제목", "wdt": "20260907"}],
    "industryCompareInfo": [{"itemCode": "278470", "stockName": "자기 자신", "closePrice": "1", "marketValue": "1"},
                            {"itemCode": "090430", "stockName": "아모레퍼시픽", "closePrice": "132,500",
                             "marketValue": "7,750,290", "fluctuationsRatio": "-2.36"}],
}
