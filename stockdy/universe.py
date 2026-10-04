"""Validated edits of config/universe.json (holdings/watchlist) for chat-driven use."""
from __future__ import annotations
import json, re
from pathlib import Path
from .core import ROOT

PATH = ROOT/"config/universe.json"
MARKETS = ("KRX", "NASDAQ", "NYSE", "US")
LISTS = ("holdings", "watchlist")


def load(path: Path = PATH):
    return json.loads(path.read_text(encoding="utf-8"))


def save(data, path: Path = PATH):
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def find(data, ticker):
    ticker = ticker.upper()
    for name in LISTS:
        for i, item in enumerate(data.get(name, [])):
            if str(item.get("ticker", "")).upper() == ticker:
                return name, i
    return None, None


def add(ticker, name, market, kind="watchlist", corp_code=None, cik=None, notes=None, path: Path = PATH):
    if kind not in LISTS: raise ValueError("kind must be holdings or watchlist")
    ticker = ticker.upper().strip()
    if market not in MARKETS: raise ValueError(f"market must be one of {', '.join(MARKETS)}")
    if market == "KRX" and not re.fullmatch(r"\d{6}", ticker): raise ValueError("KRX ticker must be 6 digits")
    if market != "KRX" and not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", ticker): raise ValueError("Invalid US ticker")
    if corp_code and not re.fullmatch(r"\d{8}", corp_code): raise ValueError("corp_code must be 8 digits")
    data = load(path)
    current, index = find(data, ticker)
    if current == kind: return {"status": "unchanged", "list": kind, "ticker": ticker}
    limit = data.get("limits", {}).get(kind)
    if limit is not None and len(data.get(kind, [])) >= limit:
        raise ValueError(f"{kind} limit {limit} reached; remove one first")
    entry = data[current].pop(index) if current else {}
    entry.update({"ticker": ticker, "name": name or entry.get("name") or ticker, "market": market,
                  "currency": "KRW" if market == "KRX" else "USD"})
    if corp_code: entry["corp_code"] = corp_code
    if cik: entry["cik"] = cik
    if notes: entry["notes"] = notes
    data.setdefault(kind, []).append(entry)
    save(data, path)
    return {"status": "moved" if current else "added", "from": current, "list": kind, "ticker": ticker}


def remove(ticker, path: Path = PATH):
    data = load(path)
    current, index = find(data, ticker)
    if not current: return {"status": "not_found", "ticker": ticker.upper()}
    entry = data[current].pop(index)
    save(data, path)
    return {"status": "removed", "list": current, "ticker": entry["ticker"]}


LEGACY_FOLDERS = {"278470": "apr"}


def latest_report(ticker, root: Path = None):
    root = root or ROOT
    for folder in (LEGACY_FOLDERS.get(ticker), ticker.lower(), ticker.upper()):
        if not folder: continue
        candidate = root/"reports"/folder/"latest.html"
        if candidate.exists(): return str(candidate.relative_to(root))
    # Reports may live under a name folder (e.g. reports/cosmax); the header carries the ticker.
    for candidate in sorted((root/"reports").glob("*/latest.html")):
        if f"· {ticker}</span></nav>" in candidate.read_text(encoding="utf-8", errors="ignore")[:4000]:
            return str(candidate.relative_to(root))
    return None


def listing(path: Path = PATH):
    data = load(path)
    return {name: [{"ticker": x.get("ticker"), "name": x.get("name"), "market": x.get("market"),
                    "latest_report": latest_report(str(x.get("ticker", "")))} for x in data.get(name, [])]
            for name in LISTS} | {"limits": data.get("limits", {})}


TEMPLATE = {
    "as_of": "YYYY-MM-DD (분석 작성일)",
    "summary": "세 문장 이내 요약. 수치마다 기간·기준을 적는다.",
    "thesis": "24개월 투자 가설 한 문단과 이를 확인할 지표.",
    "strengths": [{"text": "출처가 있는 강점", "source": "https://..."}],
    "risks": [{"text": "출처가 있는 위험", "source": "https://..."}],
    "sections": [{"title": t, "body": "본문", "sources": [{"label": "출처 이름", "url": "https://..."}]} for t in (
        "1. 기업·산업 개요와 수익 구조", "2. 재무제표·실적 전망", "3. 투자 포인트·위험과 주가 위치",
        "4. 산업 성장·시장 규모·관심도", "5. 경제적 해자", "6. 경쟁사 두 곳 비교",
        "7. 비용·영업 레버리지·잠재시장", "8. IR 핵심·최근 뉴스·리서치", "9. 24개월 가치평가·행동 검토")],
    "checkpoints": [{"item": "가설을 확인할 지표", "current": "지금 값과 출처 기간", "break_signal": "가설이 깨졌다고 볼 신호",
                     "next_check": "다음 확인 시점(예: 3Q 실적 발표)", "source": "https://..."}],
    "valuation": {"method": "최근 12개월(TTM) 지배주주 순이익(없으면 최근 연간) × (1+성장률)^2 × PER ÷ 주식수. 모든 값은 AI 가정.",
                  "scenarios": {"bear": {"profit_growth": -0.15, "pe": 10}, "base": {"profit_growth": 0.10, "pe": 15},
                                "bull": {"profit_growth": 0.25, "pe": 20}},
                  "forward": {"year": 2026, "basis": "consensus | analyst | guidance | ai", "net_income": 0,
                              "note": "추정 출처와 계산 방법. 근거 없으면 forward 항목 자체를 지운다.", "source": "https://..."}},
    "limitations": ["확인하지 못한 자료와 이유"],
}
