"""Deterministic collection, validation, valuation and HTML rendering for Stockdy."""
from __future__ import annotations
import gzip, html, json, math, os, re, urllib.parse, urllib.request, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TODAY = dt.date.today().isoformat()
DART = "https://opendart.fss.or.kr/api"
SEC = "https://data.sec.gov"


def fetch_json(url: str, *, headers=None, timeout=30):
    req = urllib.request.Request(url, headers=headers or {"User-Agent":"Stockdy research contact research@example.com"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body=response.read()
        if response.headers.get("Content-Encoding", "").lower()=="gzip" or body[:2] == b"\x1f\x8b": body=gzip.decompress(body)
        return json.loads(body.decode("utf-8"))


def dart_json(endpoint: str, params: dict, api_key: str):
    # Never expose a credential-bearing URL in exceptions, stdout or saved artifacts.
    query = urllib.parse.urlencode({**params, "crtfc_key": api_key})
    try:
        return fetch_json(f"{DART}/{endpoint}.json?{query}")
    except Exception as exc:
        raise RuntimeError(f"OpenDART request failed for {endpoint} ({type(exc).__name__})") from None


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def validate_snapshot(data):
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported schema_version")
    if not data.get("company", {}).get("ticker") or not data.get("company", {}).get("currency"):
        raise ValueError("Company ticker and currency are required")
    periods=set()
    for report in data.get("reports", []):
        key=(report.get("year"), report.get("report"))
        if key in periods: raise ValueError(f"Duplicate reporting period: {key}")
        periods.add(key)
        if not isinstance(report.get("metrics"), dict): raise ValueError(f"Metrics missing for {key}")
    return True


def collect_apr(api_key: str, out: Path, *, corp="01190568", stock="278470", company_name="APR", analysis_path=None):
    now=dt.date.today()
    reports=[]
    # Latest five complete annual report years; collect 3Q separately for the newest year.
    for year in range(now.year-1, now.year-6, -1):
        payload=dart_json("fnlttSinglAcntAll", {"corp_code":corp,"bsns_year":str(year),"reprt_code":"11011","fs_div":"CFS"}, api_key)
        if payload.get("status")!="000":
            if year==now.year-1: raise RuntimeError(f"OpenDART annual data unavailable: {payload.get('status')} {payload.get('message')}")
            continue
        reports.append({"year":year,"report":"annual","published":None,"items":payload.get("list",[])})
    # Most recently filed quarterly/interim report from current or preceding year.
    for year in (now.year, now.year-1):
        for code, period in (("11014","3Q"),("11012","2Q"),("11013","1Q")):
            payload=dart_json("fnlttSinglAcntAll", {"corp_code":corp,"bsns_year":str(year),"reprt_code":code,"fs_div":"CFS"}, api_key)
            if payload.get("status")=="000":
                reports.append({"year":year,"report":period,"published":None,"items":payload.get("list",[])}); break
        if reports and reports[-1]["year"]==year and reports[-1]["report"]!="annual": break
    listing=dart_json("list", {"corp_code":corp,"bgn_de":f"{now.year-6}0101","end_de":now.strftime("%Y%m%d"),"page_count":"100","sort":"date","sort_mth":"desc"}, api_key)
    for disclosure in listing.get("list",[]):
        title=disclosure.get("report_nm","")
        match=re.search(r"\((\d{4})\.(\d{2})",title)
        if not match: continue
        disclosed_year=int(match.group(1)); kind="annual" if "사업보고서" in title else ("2Q" if "반기보고서" in title else ("3Q" if "3분기" in title else "1Q"))
        for report in reports:
            if report["year"]==disclosed_year and report["report"]==kind:
                if not report.get("receipt_no"):
                    report["published"]=disclosure.get("rcept_dt")
                    report["receipt_no"]=disclosure.get("rcept_no")
                    report["source_url"]="https://dart.fss.or.kr/dsaf001/main.do?rcpNo="+str(disclosure.get("rcept_no",""))
                break
    info=dart_json("company", {"corp_code":corp}, api_key)
    shares_payload=dart_json("stockTotqySttus", {"corp_code":corp,"bsns_year":str(now.year-1),"reprt_code":"11011"}, api_key)
    common_shares=None
    for share_row in shares_payload.get("list",[]):
        if share_row.get("se")=="보통주":
            raw=share_row.get("distb_stock_co") or share_row.get("istc_totqy")
            if raw and str(raw).replace(",","").isdigit(): common_shares=int(str(raw).replace(",","")); break
    if info.get("status")!="000": raise RuntimeError("OpenDART company profile unavailable")
    # Save source metadata separate from observations for auditability.
    sources=[{"name":"OpenDART","url":"https://opendart.fss.or.kr/","accessed":dt.datetime.now(dt.timezone.utc).isoformat(),"disclosure_date":None,"note":"Official filing-derived consolidated financial statements."},
             {"name":"APR Investor Relations","url":"https://www.apr-in.com/ir.php","accessed":dt.datetime.now(dt.timezone.utc).isoformat(),"disclosure_date":None,"note":"Official corporate/IR entry point; latest materials require manual verification."}]
    data={"schema_version":1,"kind":"detailed","company":{"name":info.get("corp_name","에이피알"),"ticker":stock,"corp_code":corp,"market":"KRX","currency":"KRW","shares_outstanding":common_shares,"shares_as_of":f"{now.year-1}-12-31" if common_shares else None,"fiscal_year_end":"12-31"},"as_of":TODAY,"collected_at":dt.datetime.now(dt.timezone.utc).isoformat(),"source_status":"success","reports":reports,"sources":sources,"share_count_source":{"name":"OpenDART stockTotqySttus","as_of":f"{now.year-1}-12-31","value":common_shares},"market":{"price":None,"price_date":None,"market_cap":None,"note":"Unavailable: no trusted point-in-time market quote collector configured. Valuation controls use earnings multiple as an explicit scenario assumption."},"analysis":load_json(analysis_path) if analysis_path and Path(analysis_path).is_file() else (load_json(ROOT/"analysis/apr.json") if stock=="278470" else {}),"journal":[]}
    for item in data["reports"]:
        if item.get("items"): normalize_accounts({"reports":[item]})
    data["reports"].sort(key=lambda r:(r["year"],r["report"]))
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    return data


def normalize_accounts(data):
    for report in data.get("reports",[]):
        rows=report["items"]
        def amount(statement, ids=(), names=()):
            for row in rows:
                if row.get("sj_div") not in ((statement, "CIS") if statement == "IS" else (statement,)): continue
                account=(row.get("account_id") or "").lower()
                label=(row.get("account_nm") or "").lower()
                if not (any(account==x.lower() for x in ids) or any(x.lower() in account or x.lower() in label for x in names)): continue
                raw=row.get("thstrm_add_amount") if statement in ("CIS", "IS") and report.get("report") != "annual" else row.get("thstrm_amount")
                if raw in (None, ""): raw=row.get("thstrm_amount")
                if raw not in (None, "") and re.fullmatch(r"-?[0-9,]+", str(raw)): return int(str(raw).replace(",",""))
            return None
        report["metrics"]={
          "revenue":amount("CIS",("ifrs-full_Revenue",),("매출액",)),
          "operating_income":amount("CIS",("ifrs-full_OperatingProfitLoss",),("영업이익",)),
          "net_income":amount("CIS",("ifrs-full_ProfitLoss",),("당기순이익",)),
          "net_income_parent":amount("CIS",("ifrs-full_ProfitLossAttributableToOwnersOfParent",),("지배기업 소유주지분",)),
          "assets":amount("BS",("ifrs-full_Assets",),("자산총계",)),
          "equity":amount("BS",("ifrs-full_Equity",),("자본총계",)),
          "operating_cash_flow":amount("CF",("ifrs-full_CashFlowsFromUsedInOperatingActivities",),("영업활동현금흐름",)),
          "capex":amount("CF",(),("purchaseofpropertyplantandequipment", "유형자산의 증가")),
          "weighted_shares":None}
        report["period_basis"]="annual" if report["report"]=="annual" else "interim_ytd_balance_sheet_and_flow_basis"


def find(mapping, names):
    for wanted in names:
        for key,val in mapping.items():
            if wanted in key: return val
    return None


def collect_sec(ticker="AAPL", out=None):
    headers={"User-Agent":os.environ.get("SEC_USER_AGENT","Stockdy research contact research@example.com"),"Accept-Encoding":"gzip, deflate"}
    directory=fetch_json("https://www.sec.gov/files/company_tickers.json",headers=headers)
    match=next((x for x in directory.values() if x.get("ticker","").upper()==ticker.upper()),None)
    if not match: raise ValueError(f"Ticker not found in SEC company directory: {ticker}")
    cik=str(match["cik_str"]).zfill(10); submissions=fetch_json(f"https://data.sec.gov/submissions/CIK{cik}.json",headers=headers)
    payload=fetch_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",headers=headers)
    gaap=payload.get("facts",{}).get("us-gaap",{}); dei=payload.get("facts",{}).get("dei",{})
    concepts={"revenue":("RevenueFromContractWithCustomerExcludingAssessedTax","SalesRevenueNet","Revenues"),"operating_income":("OperatingIncomeLoss",),"net_income":("NetIncomeLoss",),"assets":("Assets",),"equity":("StockholdersEquity","StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),"operating_cash_flow":("NetCashProvidedByUsedInOperatingActivities",),"capex":("PaymentsToAcquirePropertyPlantAndEquipment",)}
    def annual_value(aliases, year):
        for tag in aliases:
            fact=gaap.get(tag)
            if not fact: continue
            for unit, values in fact.get("units",{}).items():
                candidates=[v for v in values if v.get("fy")==year and v.get("fp")=="FY" and v.get("form") in ("10-K","20-F") and v.get("val") is not None]
                if candidates:
                    chosen=max(candidates,key=lambda v:(v.get("filed",""),v.get("end","")))
                    return chosen.get("val"),unit,chosen
        return None,None,None
    reports=[]
    years=sorted({v.get("fy") for fact in gaap.values() for values in fact.get("units",{}).values() for v in values if v.get("fy") and v.get("fp")=="FY" and v.get("form") in ("10-K","20-F")})[-5:]
    for year in years:
        metrics={}; provenance={}
        for key,aliases in concepts.items():
            value,unit,obs=annual_value(aliases,year); metrics[key]=value
            if obs: provenance[key]={"concept":next((t for t in aliases if t in gaap),"US-GAAP"),"unit":unit,"end":obs.get("end"),"filed":obs.get("filed"),"form":obs.get("form"),"accession":obs.get("accn")}
        reports.append({"year":year,"report":"annual","period_basis":"annual","metrics":metrics,"metric_sources":provenance})
    shares=None; share_date=None
    fact=dei.get("EntityCommonStockSharesOutstanding",{})
    for unit,values in fact.get("units",{}).items():
        candidates=[v for v in values if v.get("form") in ("10-K","20-F") and v.get("val") is not None]
        if candidates:
            x=max(candidates,key=lambda v:(v.get("filed",""),v.get("end",""))); shares=x["val"]; share_date=x.get("end"); break
    recent=submissions.get("filings",{}).get("recent",{})
    filing_rows=[]
    for i,form in enumerate(recent.get("form",[])):
        if form in ("10-K","20-F") and i<len(recent.get("filingDate",[])):
            filing_rows.append({"form":form,"filed":recent["filingDate"][i],"accession":recent.get("accessionNumber",[""]*len(recent["form"]))[i],"primary_document":recent.get("primaryDocument",[""]*len(recent["form"]))[i]})
    accessed=dt.datetime.now(dt.timezone.utc).isoformat()
    data={"schema_version":1,"kind":"us_public_company","company":{"name":submissions.get("name",ticker.upper()),"ticker":ticker.upper(),"cik":cik,"market":"US","currency":"USD","shares_outstanding":shares,"shares_as_of":share_date},"as_of":TODAY,"collected_at":accessed,"source_status":"success","reports":reports,"filings":filing_rows,"sources":[{"name":"SEC companyfacts","url":f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json","accessed":accessed,"note":"Selected standard US-GAAP annual values only; source observations and filing accession metadata retained by metric."},{"name":"SEC submissions","url":f"https://www.sec.gov/edgar/browse/?CIK={int(cik)}","accessed":accessed,"note":"Recent 10-K/20-F filing index."}],"market":{"price":None,"price_date":None,"market_cap":None,"note":"Point-in-time quote not collected."},"analysis":{},"journal":[]}
    out=out or ROOT/f"data/sec/{ticker.upper()}.json"; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); return data


def quarterly_standalone(current_ytd, previous_ytd, current_duration, previous_duration):
    """Derive standalone quarter for flow measures; reject unlike periods and EPS."""
    if current_duration=="quarter" or previous_duration=="quarter": return current_ytd
    if current_duration!=previous_duration: raise ValueError("Cumulative durations do not match")
    return current_ytd-previous_ytd


def safe_ratio(numerator,denominator):
    if numerator is None or denominator is None or denominator<=0: return None
    return numerator/denominator


def scenario_values(net_income, shares, assumptions):
    if net_income is None or not shares or shares<=0: return None
    result={}
    for name, a in assumptions.items():
        forecast=net_income*(1+a["profit_growth"])**2
        value=forecast*a["pe"]/shares
        result[name]={"net_income":forecast,"value_per_share":value,"assumptions":a}
    return result


def build_report(data, out: Path):
    validate_snapshot(data)
    reports=sorted(data.get("reports",[]),key=lambda r:(r["year"],r["report"]))
    years=[r for r in reports if r["report"]=="annual"]
    metrics=[r.get("metrics",{}) for r in years]
    latest=years[-1] if years else None
    analysis=data.get("analysis",{})
    assumptions=analysis.get("valuation",{}).get("scenarios",{})
    net=(latest or {}).get("metrics",{}).get("net_income_parent")
    if net is None: net=(latest or {}).get("metrics",{}).get("net_income")
    shares=data["company"].get("shares_outstanding")
    vals=scenario_values(net,shares,assumptions)
    scenario_cards="".join(f'<article class="scenario-card"><b>{html.escape(k.upper())}</b><strong>{v["value_per_share"]:,.0f}원/주</strong><small>연간 순이익 성장 {v["assumptions"]["profit_growth"]*100:.0f}% · PER {v["assumptions"]["pe"]}배</small></article>' for k,v in (vals or {}).items())
    out.parent.mkdir(parents=True,exist_ok=True)
    report_data={k:v for k,v in data.items() if k not in ("reports","analysis","journal")}
    report_data["reports"]=[{k:v for k,v in r.items() if k!="items"} for r in reports]
    rendered={"data":report_data,"annual":[{k:v for k,v in r.items() if k!="items"} for r in years],"analysis":analysis,"valuation":vals}
    payload=json.dumps(rendered,ensure_ascii=False,separators=(",",":" )).replace("</","<\\/")
    page=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(data['company']['name'])} 투자 분석</title><style>{CSS}</style></head><body><header><nav><span>두루미 주식</span><span>{html.escape(data['as_of'])} · {html.escape(data['company']['ticker'])}</span></nav><h1>{html.escape(data['company']['name'])}<small>{html.escape(data['company']['ticker'])} · 24개월 관점</small></h1><div class="lede"><b>3줄 요약</b><p>{html.escape(analysis.get('summary','분석 요약 확인 필요'))}</p></div></header><main><section class="cards"><article><label>확인된 주가</label><strong>미확인</strong><small>{html.escape(data.get('market',{}).get('note',''))}</small></article><article><label>최근 연결 연간 매출</label><strong>{fmt((latest or {}).get('metrics',{}).get('revenue'))}</strong><small>{html.escape(str((latest or {}).get('year','—')))} · KRW</small></article><article><label>투자 판단</label><strong>사용자 결정</strong><small>자동 매매 지시 없음 · 보유 수량/원가 미제공</small></article></section><section><h2>핵심 판단</h2><div class="callout">{html.escape(analysis.get('thesis','근거 자료 기반 분석'))}</div><div class="columns">{cards(analysis.get('strengths',[]),'강점')}{cards(analysis.get('risks',[]),'핵심 위험')}</div></section><section><h2>재무 추세 <span>연결 기준 · 원</span></h2>{chart_svg(years)}</section><section><h2>시나리오 가치 범위</h2><p class="muted">24개월 수익 성장률과 평가 PER를 바꾸면 아래 값이 재계산됩니다. 실시간 주가 비교는 시세 원천을 연결하지 않아 표시하지 않습니다.</p><div class="columns">{scenario_cards}</div><div class="controls"><label>이익 성장률 <input id="growth" type="range" min="-50" max="100" value="20"><output id="growthOut">20%</output></label><label>평가 PER <input id="pe" type="range" min="5" max="60" value="25"><output id="peOut">25배</output></label></div><div id="scenario" class="scenario"></div><small>계산: 최근 연결 순이익 × (1 + 24개월 연환산 이익 성장률)<sup>2</sup> × 평가 PER ÷ 발행주식수. 주식수 또는 연결 순이익이 없어 주당가치 산출 불가.</small></section><section><h2>상세 분석</h2>{detail_sections(analysis)}</section><section><h2>재무 데이터</h2>{financial_table(years)}</section><section><h2>자료와 확인 한계</h2><ul>{''.join(f'<li><a href="{html.escape(safe_link(s["url"]),quote=True)}" target="_blank" rel="noopener">{html.escape(s["name"])}</a> · 확인 {html.escape(s.get("accessed","미확인"))} · {html.escape(s.get("note",""))}</li>' for s in data.get('sources',[]))}</ul><p class="muted">한경컨센서스·증권사 전망 0건 수집. 제품별 매출·단가·원재료·시장점유율·외국인/기관 수급·Google Trends·경쟁사 동등 비교·최근 뉴스는 검증 가능한 공개 근거를 확보하지 못해 미확인으로 남겼습니다. 시나리오는 AI 분석 입력의 가정이며 회사 가이던스나 컨센서스가 아닙니다.</p></section><section><h2>투자 일기</h2><p>사용자 메모 없음. 향후 journal/에 기록되는 사용자 의견과 AI 분석은 별도로 보존됩니다.</p></section></main><footer>생성기 {html.escape(data.get('collected_at',''))} · 이 문서는 조사 도구이며 개인화된 금융 조언이나 매매 권유가 아닙니다.</footer><script>const D={payload};{JS}</script></body></html>'''
    out.write_text(page,encoding="utf-8")

def safe_link(value):
    parsed=urllib.parse.urlparse(str(value or ""))
    return str(value) if parsed.scheme in ("http","https") and parsed.netloc else "#"

def fmt(v):
    if v is None:return "미확인"
    n=v/1e8
    return f"{n:,.1f} 억원" if abs(n)>=1 else f"{v:,.0f} 원"

def cards(items,title):
    return '<article class="box"><h3>'+html.escape(title)+'</h3><ul>'+''.join('<li>'+html.escape(x['text'])+((' <a href="'+html.escape(safe_link(x['source']),quote=True)+'" target="_blank" rel="noopener">근거</a>') if x.get('source') else '')+'</li>' for x in items)+'</ul></article>'
def detail_sections(a):
    sections=a.get('sections',[])
    return ''.join('<details><summary>'+html.escape(s['title'])+'</summary><p>'+html.escape(s['body'])+'</p>'+''.join('<p><a href="'+html.escape(safe_link(src['url']),quote=True)+'" target="_blank" rel="noopener">'+html.escape(src['label'])+'</a></p>' for src in s.get('sources',[]))+'</details>' for s in sections)
def financial_table(rows):
    keys=[('revenue','매출'),('operating_income','영업이익'),('net_income','순이익'),('operating_cash_flow','영업현금흐름'),('capex','유형자산 취득'),('equity','자본')]
    return '<div class="table-wrap"><table><thead><tr><th>회계연도</th>'+''.join('<th>'+k[1]+' (억원)</th>' for k in keys)+'</tr></thead><tbody>'+''.join('<tr><th>'+str(r['year'])+'</th>'+''.join('<td>'+fmt(r.get('metrics',{}).get(k[0]))+'</td>' for k in keys)+'</tr>' for r in rows)+'</tbody></table></div>'
def chart_svg(rows):
    series=[(r['year'],r.get('metrics',{}).get('revenue')) for r in rows if r.get('metrics',{}).get('revenue') is not None]
    if len(series)<2:return '<p class="muted">비교 가능한 매출 자료 부족</p>'
    m=max(v for _,v in series); w=700; h=220
    bars=''.join(f'<g><rect x="{40+i*120}" y="{h-25-v/m*170:.1f}" width="62" height="{v/m*170:.1f}" rx="8"/><text x="{71+i*120}" y="{h-6}" text-anchor="middle">{y}</text><text x="{71+i*120}" y="{h-32-v/m*170:.1f}" text-anchor="middle">{v/1e11:.0f}천억</text></g>' for i,(y,v) in enumerate(series[-5:]))
    return f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="연결 매출 추이">{bars}</svg>'

CSS='''*{box-sizing:border-box}body{margin:0;background:#f5f6f2;color:#17221f;font:16px/1.6 system-ui,-apple-system,sans-serif}header{padding:28px max(22px,calc((100vw - 1080px)/2));background:#173d35;color:white}nav{display:flex;justify-content:space-between;color:#bad2ca;font-size:.9rem}h1{font-size:clamp(2rem,6vw,4rem);letter-spacing:-.05em;margin:40px 0 20px}h1 small{display:block;font-size:1rem;letter-spacing:0;color:#c5ddd5;margin-top:8px}.lede{max-width:760px;background:#ffffff14;padding:16px 20px;border-radius:14px}.lede p{margin:4px 0 0}main{max-width:1080px;padding:28px 20px 70px;margin:auto}section{margin:22px 0 46px}h2{font-size:1.55rem;letter-spacing:-.03em}h2 span{color:#71827d;font-size:.85rem;font-weight:500}.cards,.columns{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}.cards article,.box{background:white;padding:20px;border:1px solid #e3e9e5;border-radius:16px}.cards label,.cards small{display:block;color:#667671}.cards strong{display:block;font-size:1.3rem;margin:10px 0}.callout{background:#e2eee9;padding:20px;border-radius:14px}.box h3{margin-top:0}.box li{margin:10px 0}.chart{width:100%;max-height:260px;background:white;border-radius:16px;padding:10px}.chart rect{fill:#287760}.chart text{font-size:12px;fill:#50635e}.controls{display:flex;flex-wrap:wrap;gap:28px;padding:18px;background:#fff;border-radius:14px}.controls label{display:grid;gap:6px;min-width:230px}.scenario{margin:14px 0;display:flex;gap:12px;flex-wrap:wrap}.scenario div{background:#fff;border-radius:12px;padding:16px;min-width:150px}.scenario strong{display:block;font-size:1.2rem}details{padding:16px 0;border-bottom:1px solid #dce4df}summary{font-weight:650;cursor:pointer}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;background:white}td,th{padding:12px;border-bottom:1px solid #e5e9e6;text-align:right;white-space:nowrap}th:first-child{text-align:left}.muted,small{color:#71817b}a{color:#236a55}footer{border-top:1px solid #dce4df;padding:24px;text-align:center;color:#71817b;font-size:.85rem}@media(max-width:600px){header{padding:22px}main{padding:18px 14px 50px}.cards{grid-template-columns:1fr}}'''
JS='''const g=document.getElementById('growth'),p=document.getElementById('pe'),box=document.getElementById('scenario');function recalc(){document.getElementById('growthOut').value=g.value+'%';document.getElementById('peOut').value=p.value+'배';const annual=D.annual, latest=annual.length?(annual[annual.length-1].metrics.net_income_parent??annual[annual.length-1].metrics.net_income):null, shares=D.data.company.shares_outstanding; if(!latest||!shares){box.innerHTML='<div><strong>주당가치 산출 불가</strong>연결 순이익 또는 발행주식수 입력값 미확인</div>';return}const v=latest*Math.pow(1+Number(g.value)/100,2)*Number(p.value)/shares;box.innerHTML='<div><label>사용자 조정 시나리오</label><strong>'+Math.round(v).toLocaleString()+' 원/주</strong><small>확정 가격 대비 차이 미계산</small></div>'}g.addEventListener('input',recalc);p.addEventListener('input',recalc);recalc();'''
