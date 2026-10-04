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


def resolve_corp_code(stock_code: str, api_key: str):
    """Map a 6-digit KRX stock code to its OpenDART corp_code via corpCode.xml."""
    import io, zipfile, xml.etree.ElementTree as ET
    query = urllib.parse.urlencode({"crtfc_key": api_key})
    try:
        with urllib.request.urlopen(f"{DART}/corpCode.xml?{query}", timeout=60) as response:
            body=response.read()
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            root=ET.fromstring(zf.read(zf.namelist()[0]))
    except Exception as exc:
        raise RuntimeError(f"OpenDART corp code lookup failed ({type(exc).__name__})") from None
    for item in root.iter("list"):
        if (item.findtext("stock_code") or "").strip()==stock_code:
            return (item.findtext("corp_code") or "").strip(), (item.findtext("corp_name") or "").strip()
    raise ValueError(f"No OpenDART corp_code for stock code {stock_code}")


def fetch_quote(symbol: str, shares=None, currency=None):
    """Latest close from Yahoo Finance chart API; returns a market dict, never raises."""
    empty={"price":None,"price_date":None,"market_cap":None,"symbol":symbol,"source_url":None,"note":"기준일 주가 자료 없음"}
    if not symbol: return empty
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range=5d&interval=1d"
    try:
        meta=fetch_json(url,headers={"User-Agent":"Mozilla/5.0 (Stockdy research)"})["chart"]["result"][0]["meta"]
        price=meta.get("regularMarketPrice"); stamp=meta.get("regularMarketTime")
        if price is None or not stamp: return {**empty,"note":"시세 응답에 가격 없음"}
        if currency and meta.get("currency") and meta["currency"]!=currency:
            return {**empty,"note":f"시세 통화 {meta['currency']}가 재무 통화 {currency}와 달라 사용하지 않음"}
        tz=dt.timezone(dt.timedelta(seconds=int(meta.get("gmtoffset") or 0)))
        day=dt.datetime.fromtimestamp(int(stamp),tz).date().isoformat()
        return {"price":price,"price_date":day,"market_cap":price*shares if shares else None,"symbol":symbol,
                "week52_high":meta.get("fiftyTwoWeekHigh"),"week52_low":meta.get("fiftyTwoWeekLow"),"source_url":f"https://finance.yahoo.com/quote/{urllib.parse.quote(symbol)}","note":"Yahoo Finance 최근 종가(비공식 시세, 지연 가능) · 시가총액은 공시 주식수 기준 추정"}
    except Exception as exc:
        return {**empty,"note":f"시세 조회 실패 ({type(exc).__name__})"}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def validate_snapshot(data):
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported schema_version")
    if not data.get("company", {}).get("ticker") or not data.get("company", {}).get("currency"):
        raise ValueError("Company ticker and currency are required")
    source_urls=[x.get("url","") for x in data.get("sources",[]) if urllib.parse.urlparse(str(x.get("url",""))).scheme in ("https","http") and urllib.parse.urlparse(str(x.get("url",""))).netloc]
    if data.get("source_status")=="success" and not source_urls:
        raise ValueError("Successful data snapshot requires at least one valid source URL")
    periods=set()
    for report in data.get("reports", []):
        key=(report.get("year"), report.get("report"))
        if key in periods: raise ValueError(f"Duplicate reporting period: {key}")
        periods.add(key)
        if not isinstance(report.get("metrics"), dict): raise ValueError(f"Metrics missing for {key}")
        provenance=report.get("metric_sources",{})
        report_url=report.get("source_url")
        for metric,value in report["metrics"].items():
            if value is not None and not report_url and not provenance.get(metric):
                raise ValueError(f"Metric {metric} in {key} has no source provenance")
    return True


def collect_apr(api_key: str, out: Path, *, corp="01190568", stock="278470", company_name="APR", company_ir_url=None, analysis_path=None):
    now=dt.date.today()
    reports=[]
    # Latest five complete annual report years; collect 3Q separately for the newest year.
    for year in range(now.year-1, now.year-6, -1):
        payload=dart_json("fnlttSinglAcntAll", {"corp_code":corp,"bsns_year":str(year),"reprt_code":"11011","fs_div":"CFS"}, api_key)
        if payload.get("status")!="000":
            if year==now.year-1: raise RuntimeError(f"OpenDART annual data unavailable: {payload.get('status')} {payload.get('message')}")
            continue
        reports.append({"year":year,"report":"annual","published":None,"items":payload.get("list",[])})
    # Every filed quarterly/interim report of the latest year that has any (current, else preceding).
    annual_years={r["year"] for r in reports}
    for year in (now.year, now.year-1):
        if year in annual_years: break
        found=[]
        for code, period in (("11013","1Q"),("11012","2Q"),("11014","3Q")):
            payload=dart_json("fnlttSinglAcntAll", {"corp_code":corp,"bsns_year":str(year),"reprt_code":code,"fs_div":"CFS"}, api_key)
            if payload.get("status")=="000":
                found.append({"year":year,"report":period,"published":None,"items":payload.get("list",[])})
        if found:
            reports.extend(found); break
    listing=dart_json("list", {"corp_code":corp,"bgn_de":f"{now.year-6}0101","end_de":now.strftime("%Y%m%d"),"page_count":"100","sort":"date","sort_mth":"desc"}, api_key)
    filings={x.get("rcept_no"):x for x in listing.get("list",[]) if x.get("rcept_no")}
    for report in reports:
        receipts={row.get("rcept_no") for row in report.get("items",[]) if row.get("rcept_no")}
        if len(receipts)==1:
            receipt=next(iter(receipts)); filed=filings.get(receipt,{})
            report.update(receipt_no=receipt,published=filed.get("rcept_dt"),source_url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo="+receipt)
    info=dart_json("company", {"corp_code":corp}, api_key)
    shares_payload=dart_json("stockTotqySttus", {"corp_code":corp,"bsns_year":str(now.year-1),"reprt_code":"11011"}, api_key)
    common_shares=None
    for share_row in shares_payload.get("list",[]):
        if share_row.get("se")=="보통주":
            raw=share_row.get("distb_stock_co") or share_row.get("istc_totqy")
            if raw and str(raw).replace(",","").isdigit(): common_shares=int(str(raw).replace(",","")); break
    if info.get("status")!="000": raise RuntimeError("OpenDART company profile unavailable")
    # Save source metadata separate from observations for auditability.
    sources=[{"name":"OpenDART","url":"https://opendart.fss.or.kr/","accessed":dt.datetime.now(dt.timezone.utc).isoformat(),"disclosure_date":None,"note":"Official filing-derived consolidated financial statements."}]
    if company_ir_url:
        sources.append({"name":company_name+" investor relations","url":company_ir_url,"accessed":dt.datetime.now(dt.timezone.utc).isoformat(),"disclosure_date":None,"note":"Issuer IR link configured for this company."})
    suffix={"Y":".KS","K":".KQ"}.get(info.get("corp_cls"))
    market=fetch_quote(stock+suffix if suffix else "",common_shares,"KRW")
    if market.get("source_url"):
        sources.append({"name":"Yahoo Finance 시세","url":market["source_url"],"accessed":dt.datetime.now(dt.timezone.utc).isoformat(),"disclosure_date":market["price_date"],"note":"최근 종가. 비공식 시세이며 지연될 수 있음."})
    data={"schema_version":1,"kind":"detailed","company":{"name":info.get("corp_name",company_name),"ticker":stock,"corp_code":corp,"market":"KRX","currency":"KRW","shares_outstanding":common_shares,"shares_as_of":f"{now.year-1}-12-31" if common_shares else None,"fiscal_year_end":"12-31"},"as_of":TODAY,"collected_at":dt.datetime.now(dt.timezone.utc).isoformat(),"source_status":"success","reports":reports,"sources":sources,"share_count_source":{"name":"OpenDART stockTotqySttus","as_of":f"{now.year-1}-12-31","value":common_shares},"market":market,"analysis":load_json(analysis_path) if analysis_path and Path(analysis_path).is_file() else (load_json(ROOT/"analysis/apr.json") if stock=="278470" else {}),"journal":[]}
    for item in data["reports"]:
        if item.get("items"): normalize_accounts({"reports":[item]})
    data["reports"].sort(key=lambda r:(r["year"],r["report"]))
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    return data


def normalize_accounts(data):
    for report in data.get("reports",[]):
        rows=report.get("items",[])
        is_interim=report.get("report")!="annual"
        def parse(row,field):
            raw=row.get(field)
            if raw in (None,"","-"): return None
            value=str(raw).replace(",","")
            if re.fullmatch(r"-?\d+(?:\.\d+)?",value): return float(value) if "." in value else int(value)
            return None
        def amount(statement,ids=(),labels=(),field="thstrm_amount"):
            statements=("CIS","IS") if statement=="CIS" else (statement,)
            for statement_candidate in statements:
                for wanted in ids:
                    for row in rows:
                        if row.get("sj_div")==statement_candidate and row.get("account_id")==wanted:
                            value=parse(row,field)
                            if value is not None: return value
            for statement_candidate in statements:
                for wanted in labels:
                    for row in rows:
                        if row.get("sj_div")==statement_candidate and row.get("account_nm")==wanted:
                            value=parse(row,field)
                            if value is not None: return value
            return None
        flows={
          "revenue":("CIS",("ifrs-full_Revenue",),("매출액",)),
          "operating_income":("CIS",("ifrs-full_OperatingProfitLoss","dart_OperatingIncomeLoss"),("영업이익","영업이익(손실)")),
          "net_income":("CIS",("ifrs-full_ProfitLoss",),("당기순이익","당기순이익(손실)")),
          "net_income_parent":("CIS",("ifrs-full_ProfitLossAttributableToOwnersOfParent",),()),
          "operating_cash_flow":("CF",("ifrs-full_CashFlowsFromUsedInOperatingActivities","dart_NetCashFlowsFromUsedInOperatingActivities"),("영업활동현금흐름",)),
          "capex":("CF",("ifrs-full_PurchaseOfPropertyPlantAndEquipment","dart_PurchaseOfPropertyPlantAndEquipment"),("유형자산의 취득","유형자산의 증가"))}
        metrics={}; ytd={}; standalone={}
        for key,(statement,ids,labels) in flows.items():
            current=amount(statement,ids,labels)
            metrics[key]=current
            if not is_interim or key in ("operating_cash_flow","capex"):
                ytd[key]=current
            else:
                cumulative=amount(statement,ids,labels,field="thstrm_add_amount")
                ytd[key]=cumulative if cumulative is not None else (current if report.get("report")=="1Q" else None)
            standalone[key]=current if key not in ("operating_cash_flow","capex") or not is_interim else None
        if is_interim:
            # Prior-year comparatives from the same filing: same quarter and same YTD span.
            report["prior_metrics"]={
              "quarter":{k:amount(s,i,l,field="frmtrm_q_amount") for k,(s,i,l) in flows.items() if s=="CIS"},
              "ytd":{k:amount(s,i,l,field="frmtrm_add_amount") for k,(s,i,l) in flows.items() if s=="CIS"}}
            if report.get("report")=="1Q":
                report["prior_metrics"]["ytd"]=dict(report["prior_metrics"]["quarter"])
        metrics.update({
          "liabilities":amount("BS",("ifrs-full_Liabilities",),("부채총계",)),
          "cash":amount("BS",("ifrs-full_CashAndCashEquivalents",),("현금및현금성자산",)),
          "assets":amount("BS",("ifrs-full_Assets",),("자산총계",)),
          "equity":amount("BS",("ifrs-full_Equity",),("자본총계",)),
          "equity_parent":amount("BS",("ifrs-full_EquityAttributableToOwnersOfParent",),("지배기업 소유주지분",)),
          "weighted_shares":None})
        # One EPS line (diluted, else basic) for every field so periods stay comparable.
        eps_line=next(((ids,labels) for ids,labels in ((("ifrs-full_DilutedEarningsLossPerShare",),("보통주 희석주당손익","보통주 희석주당이익")),(("ifrs-full_BasicEarningsLossPerShare",),("보통주 기본주당손익","보통주 기본주당이익"))) if amount("CIS",ids,labels) is not None),None)
        metrics["eps"]=amount("CIS",*eps_line) if eps_line else None
        metrics["eps_basis"]=("희석" if "Diluted" in eps_line[0][0] else "기본") if eps_line else None
        instant={k:metrics.get(k) for k in ("assets","liabilities","cash","equity","equity_parent")}
        ytd.pop("eps",None)
        if is_interim and eps_line:
            ytd["eps"]=amount("CIS",*eps_line,field="thstrm_add_amount") if report.get("report")!="1Q" else metrics["eps"]
            report["prior_metrics"]["quarter"]["eps"]=amount("CIS",*eps_line,field="frmtrm_q_amount")
            report["prior_metrics"]["ytd"]["eps"]=amount("CIS",*eps_line,field="frmtrm_add_amount") if report.get("report")!="1Q" else report["prior_metrics"]["quarter"]["eps"]
        report["metrics"]=metrics
        report_receipts={row.get("rcept_no") for row in rows if row.get("rcept_no")}
        if len(report_receipts)==1:
            report["receipt_no"]=next(iter(report_receipts))
            report["source_url"]="https://dart.fss.or.kr/dsaf001/main.do?rcpNo="+report["receipt_no"]
        report["ytd_metrics"]=ytd
        report["standalone_metrics"]=standalone
        report["instant_metrics"]=instant
        report["period_basis"]="annual" if not is_interim else "income_quarter_standalone_cashflow_ytd_balance_sheet_instant"


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
    concepts={"revenue":("RevenueFromContractWithCustomerExcludingAssessedTax","SalesRevenueNet","Revenues"),"operating_income":("OperatingIncomeLoss",),"net_income":("NetIncomeLoss",),"assets":("Assets",),"equity":("StockholdersEquity","StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),"operating_cash_flow":("NetCashProvidedByUsedInOperatingActivities",),"capex":("PaymentsToAcquirePropertyPlantAndEquipment",),"eps":("EarningsPerShareDiluted","EarningsPerShareBasic")}
    instant_metrics={"assets","equity"}
    def annual_value(metric,aliases,year,matching_end=None):
        for tag in aliases:
            fact=gaap.get(tag)
            if not fact: continue
            for unit,values in fact.get("units",{}).items():
                required_unit=("USD / shares","USD/shares","USD / share","USD/share") if metric=="eps" and source_currency=="USD" else ((source_currency,) if metric!="eps" and source_currency=="USD" else ())
                if unit not in required_unit: continue
                candidates=[]
                for v in values:
                    if v.get("fy")!=year or v.get("fp")!="FY" or v.get("form") not in ("10-K","20-F") or v.get("val") is None: continue
                    end=v.get("end","")
                    try:
                        end_year=dt.date.fromisoformat(end).year
                    except ValueError:
                        continue
                    if end_year not in (year, year+1): continue
                    if matching_end and end!=matching_end: continue
                    start_date=v.get("start")
                    if metric in instant_metrics:
                        if start_date: continue
                    else:
                        if not start_date: continue
                        try:
                            duration=(dt.date.fromisoformat(end)-dt.date.fromisoformat(start_date)).days
                        except ValueError: continue
                        if duration<350 or duration>380: continue
                    candidates.append(v)
                if candidates:
                    chosen=max(candidates,key=lambda v:(v.get("filed",""),v.get("end","")))
                    return chosen.get("val"),unit,chosen,tag
        return None,None,None,None
    reports=[]
    revenue_fact=next((gaap.get(tag) for tag in concepts["revenue"] if gaap.get(tag)),{})
    revenue_units=set(revenue_fact.get("units",{}))
    source_currency="USD" if "USD" in revenue_units else next((u for u in sorted(revenue_units) if "/" not in u and u not in ("shares","pure")),None)
    currency=source_currency or "unsupported"
    years=sorted({v.get("fy") for values in revenue_fact.get("units",{}).values() for v in values if v.get("fy") and v.get("fp")=="FY" and v.get("form") in ("10-K","20-F")})[-5:]
    for year in years:
        metrics={}; provenance={}; annual_end=None
        for key,aliases in concepts.items():
            value,unit,obs,used_tag=annual_value(key,aliases,year,annual_end)
            if key=="revenue" and obs: annual_end=obs.get("end")
            metrics[key]=value
            if obs: provenance[key]={"concept":used_tag,"unit":unit,"end":obs.get("end"),"filed":obs.get("filed"),"form":obs.get("form"),"accession":obs.get("accn")}
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
    market=fetch_quote(ticker.upper().replace(".","-"),shares,currency)
    data={"schema_version":1,"kind":"us_public_company","company":{"name":submissions.get("name",ticker.upper()),"ticker":ticker.upper(),"cik":cik,"market":"US","currency":currency,"shares_outstanding":shares,"shares_as_of":share_date},"as_of":TODAY,"collected_at":accessed,"source_status":"success","reports":reports,"filings":filing_rows,"sources":[{"name":"SEC companyfacts","url":f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json","accessed":accessed,"note":("Selected standard US-GAAP annual values only; USD and USD/share observations retained with accession metadata by metric." if currency=="USD" else f"Unsupported SEC presentation currency {currency}; no values are relabeled as USD.")},{"name":"SEC submissions","url":f"https://www.sec.gov/edgar/browse/?CIK={int(cik)}","accessed":accessed,"note":"Recent 10-K/20-F filing index."}]+([{"name":"Yahoo Finance 시세","url":market["source_url"],"accessed":accessed,"note":"최근 종가. 비공식 시세이며 지연될 수 있음."}] if market.get("source_url") else []),"market":market,"analysis":{},"journal":[]}
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


def earnings_base(reports):
    """Valuation earnings: trailing twelve months when the next year's interim YTD and its
    prior-year comparative exist; otherwise the latest annual figure."""
    years=[r for r in reports if r["report"]=="annual"]
    if not years: return {"net":None,"label":"연간 실적 없음","numerator":"미확인","kind":"none"}
    annual=years[-1]; am=annual.get("metrics",{})
    key="net_income_parent" if am.get("net_income_parent") is not None else "net_income"
    numerator="지배기업 귀속 순이익" if key=="net_income_parent" else "연결 순이익 (지배기업 귀속 미확인)"
    interims=[r for r in reports if r["report"]!="annual" and r["year"]==annual["year"]+1]
    for r in sorted(interims,key=lambda r:r["report"],reverse=True):
        ytd=(r.get("ytd_metrics") or {}).get(key); prior=((r.get("prior_metrics") or {}).get("ytd") or {}).get(key)
        if ytd is not None and prior is not None and am.get(key) is not None:
            e_ytd=(r.get("ytd_metrics") or {}).get("eps"); e_prior=((r.get("prior_metrics") or {}).get("ytd") or {}).get("eps")
            eps=am["eps"]+e_ytd-e_prior if None not in (am.get("eps"),e_ytd,e_prior) and am.get("eps_basis")==r.get("metrics",{}).get("eps_basis") else None
            return {"net":am[key]+ytd-prior,"eps":eps,"kind":"ttm","numerator":numerator,
                    "label":f"최근 12개월(TTM) = {annual['year']} 연간 + {r['year']} {r['report']} 누적 − {annual['year']} 같은 기간 누적"}
    return {"net":am.get(key),"eps":am.get("eps"),"kind":"annual","numerator":numerator,"label":f"{annual['year']} 연간"}


FORWARD_BASIS={"consensus":"컨센서스","analyst":"개별 증권사 추정","guidance":"회사 가이던스 기반 추정","ai":"AI 추정"}


def forward_valuation(analysis, cap, price, currency):
    """Forward PER only from an explicitly sourced estimate in the analysis input."""
    f=(analysis.get("valuation") or {}).get("forward") or {}
    basis=FORWARD_BASIS.get(f.get("basis"))
    if not basis or not f.get("year"): return None
    per=cap/f["net_income"] if cap and f.get("net_income") and f["net_income"]>0 else (price/f["eps"] if price and f.get("eps") and f["eps"]>0 else None)
    if per is None: return None
    amount=fmt(f["net_income"],currency) if f.get("net_income") else f"EPS {f['eps']:,.0f}"
    return {"per":per,"text":f"Forward PER {per:.1f}배 ({f['year']}E 순이익 {amount}, {basis})","note":f.get("note",""),"source":f.get("source")}


def latest_instant(reports):
    for r in sorted(reports,key=lambda r:(r["year"],r["report"]!="annual",r["report"]),reverse=True):
        m=r.get("metrics",{})
        if m.get("equity_parent") is not None or m.get("equity") is not None: return r
    return None


def build_report(data, out: Path):
    validate_snapshot(data)
    for r in data.get("reports",[]):
        if r.get("items") and "eps_basis" not in r.get("metrics",{}):
            normalize_accounts({"reports":[r]})  # enrich snapshots saved before comparatives were extracted
    reports=sorted(data.get("reports",[]),key=lambda r:(r["year"],r["report"]))
    years=[r for r in reports if r["report"]=="annual"]
    latest=years[-1] if years else None
    analysis=data.get("analysis",{})
    assumptions=analysis.get("valuation",{}).get("scenarios",{})
    base=earnings_base(reports); net=base["net"]
    shares=data["company"].get("shares_outstanding")
    currency=data["company"].get("currency","KRW")
    interim_rows=[r for r in reports if r.get("report")!="annual"]
    interims_html=interim_table(interim_rows,currency)
    vals=scenario_values(net,shares,assumptions)
    limitations=analysis.get("limitations",["한경컨센서스 미수집","제품별 장기 단가, 원재료, 점유율, 기관 수급, Google Trends 및 동등 기준 경쟁사 데이터 미확인"])
    limitations_text=" · ".join(html.escape(x) for x in limitations)
    scenario_basis_note=f"기준 이익: {base['label']} {fmt(net,currency)} ({base['numerator']}) · 주식수 {shares:,}주 ({data['company'].get('shares_as_of') or '기준일 미확인'})" if shares else f"기준 이익: {base['label']} · 주식수 미확인"
    market=data.get("market",{}) or {}
    price=market.get("price"); cap=market.get("market_cap")
    bs=latest_instant(reports); bm=(bs or {}).get("metrics",{})
    equity_now=bm.get("equity_parent") if bm.get("equity_parent") is not None else bm.get("equity")
    per_now=cap/net if cap and net and net>0 else None
    pbr_now=cap/equity_now if cap and equity_now and equity_now>0 else None
    hi,lo=market.get("week52_high"),market.get("week52_low")
    range_text=f"52주 {fmt_price(lo,currency)} ~ {fmt_price(hi,currency)} · 범위 내 {(price-lo)/(hi-lo)*100:.0f}% 위치" if price and hi and lo and hi>lo else ""
    valuation_card=(f'<strong>PER {per_now:.1f}배' if per_now else '<strong>PER N/A')+(f' · PBR {pbr_now:.1f}배' if pbr_now else '')+'</strong><small>'+html.escape(" · ".join(x for x in [
        (f"시가총액(추정) {fmt(cap,currency)}" if cap else "종가 없음 · 시가총액 미산출"),
        (f"이익: {base['label']}" if per_now else ""),
        (f"자본: {bs['year']} {bs['report']} 말" if pbr_now else ""),
        (f"EPS {base['eps']:,.0f} ({'TTM' if base['kind']=='ttm' else '연간'})" if base.get("eps") is not None else "")] if x))
    fwd=forward_valuation(analysis,cap,price,currency)
    valuation_card+=('<br><b>'+html.escape(fwd["text"])+'</b>'+(' '+html.escape(fwd["note"]) if fwd["note"] else '')+(f' <a href="{html.escape(safe_link(fwd["source"]),quote=True)}" target="_blank" rel="noopener">근거</a>' if fwd.get("source") else '')) if fwd else '<br>Forward PER: 출처 있는 이익 추정 없음'
    valuation_card+='</small>'
    q=next((r for r in reversed(interim_rows) if (r.get("prior_metrics") or {}).get("quarter")),None)
    def yoy(cur,prev): return cur/prev-1 if cur is not None and prev not in (None,0) and prev>0 else None
    if q:
        qm=q.get("metrics",{}); qp=q["prior_metrics"]["quarter"]
        g_rev,g_op,g_eps=yoy(qm.get("revenue"),qp.get("revenue")),yoy(qm.get("operating_income"),qp.get("operating_income")),yoy(qm.get("eps"),qp.get("eps"))
        growth_card=f'<label>최근 분기 성장 ({html.escape(str(q["year"])+" "+q["report"])}, 전년 같은 분기 대비)</label><strong>매출 {pct(g_rev)} · EPS {pct(g_eps)}</strong><small>영업이익 {pct(g_op)} · 분기 매출 {fmt(qm.get("revenue"),currency)} · 분기 EPS {"N/A" if qm.get("eps") is None else format(qm["eps"],",.0f")}</small>'
    else:
        g=yoy((latest or {}).get("metrics",{}).get("revenue"),(years[-2] if len(years)>1 else {}).get("metrics",{}).get("revenue"))
        growth_card=f'<label>최근 연간 매출 ({html.escape(str((latest or {}).get("year","—")))})</label><strong>{fmt((latest or {}).get("metrics",{}).get("revenue"),currency)}</strong><small>전년 대비 {pct(g)}</small>'
    base_sc=assumptions.get("base") or next(iter(assumptions.values()),{"profit_growth":0.15,"pe":20})
    implied=((price*shares/(net*base_sc["pe"]))**0.5-1) if price and shares and net and net>0 else None
    implied_text=f"현재 종가는 PER {base_sc['pe']}배를 가정하면 앞으로 2년간 연 {implied*100:.0f}% 이익 성장을 반영한 가격이다." if implied is not None else ""
    def vs_price(v):
        return f" · 종가 대비 {v/price*100-100:+.0f}%" if price else ""
    summary_lines="".join(f"<li>{html.escape(x.strip())}</li>" for x in re.split(r"(?<=[。.!?])\s+",analysis.get("summary","분석 요약 확인 필요")) if x.strip())
    scenario_cards="".join(f'<article class="scenario-card"><b>{html.escape(k.upper())}</b><strong>{v["value_per_share"]:,.0f} {("원/주" if currency=="KRW" else currency+"/share")}</strong><small>연간 순이익 성장 {v["assumptions"]["profit_growth"]*100:.0f}% · PER {v["assumptions"]["pe"]}배{vs_price(v["value_per_share"])}</small></article>' for k,v in (vals or {}).items())
    out.parent.mkdir(parents=True,exist_ok=True)
    report_data={k:v for k,v in data.items() if k not in ("reports","analysis","journal")}
    report_data["reports"]=[{k:v for k,v in r.items() if k!="items"} for r in reports]
    rendered={"data":report_data,"annual":[{k:v for k,v in r.items() if k!="items"} for r in years],"analysis":analysis,"valuation":vals,"base":net,"base_label":base["label"]}
    payload=json.dumps(rendered,ensure_ascii=False,separators=(",",":" )).replace("</","<\\/")
    page=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(data['company']['name'])} 투자 분석</title><style>{CSS}</style></head><body><header><nav><span>두루미 주식</span><span>자료 {html.escape(data['as_of'])} · 분석 작성 {html.escape(str(analysis.get('as_of') or '날짜 미기록'))} · {html.escape(data['company']['ticker'])}</span></nav><h1>{html.escape(data['company']['name'])}<small>{html.escape(data['company']['ticker'])} · 24개월 관점</small></h1><div class="lede"><b>3줄 요약</b><ol>{summary_lines}</ol></div></header><main><section class="cards"><article><label>기준일 주가</label><strong>{fmt_price(data.get('market',{}).get('price'),currency)}</strong><small>{html.escape(str(market.get('price_date') or '기준일 미확인'))} · {html.escape(market.get('note',''))}{('<br>'+html.escape(range_text)) if range_text else ''}</small></article><article><label>밸류에이션</label>{valuation_card}</article><article>{growth_card}</article></section><section><h2>핵심 판단</h2><div class="callout">{html.escape(analysis.get('thesis','근거 자료 기반 분석'))}</div><div class="columns">{cards(analysis.get('strengths',[]),'강점')}{cards(analysis.get('risks',[]),'핵심 위험')}</div></section>{checkpoints_table(analysis.get('checkpoints',[]))}<section><h2>재무 추세 <span>연결 기준 · {html.escape(currency)}</span></h2>{chart_svg(years,currency)}</section><section><h2>시나리오 가치 범위</h2><p class="muted">기준 이익에 2년간 연 성장률을 적용하고 평가 PER를 곱한 24개월 뒤 주당 가치입니다. 막대를 움직이면 다시 계산됩니다. {html.escape(f"비교 기준: {market.get('price_date')} 종가 {fmt_price(price,currency)} (비공식 시세)." if price else "기준일 종가가 없어 주가와 비교하지 않습니다.")}</p>{('<div class="callout">'+html.escape(implied_text)+'</div>') if implied_text else ''}<div class="columns">{scenario_cards}</div><div class="controls"><label>이익 성장률 <input id="growth" type="range" min="-50" max="100" value="{round(base_sc['profit_growth']*100)}"><output id="growthOut">{round(base_sc['profit_growth']*100)}%</output></label><label>평가 PER <input id="pe" type="range" min="5" max="60" value="{base_sc['pe']}"><output id="peOut">{base_sc['pe']}배</output></label></div><div id="scenario" class="scenario"></div><small>계산: 기준 이익 × (1 + 연간 이익 성장 가정)<sup>2</sup> × 평가 PER ÷ 주식수.</small><p class="muted">{html.escape(scenario_basis_note)}</p></section><section><h2>상세 분석</h2>{detail_sections(analysis)}</section><section><h2>재무 데이터</h2>{financial_table(years,currency)}<h3>최신 중간 실적</h3>{interims_html}</section><section><h2>자료와 확인 한계</h2><ul>{''.join(f'<li><a href="{html.escape(safe_link(s["url"]),quote=True)}" target="_blank" rel="noopener">{html.escape(s["name"])}</a> · 확인 {html.escape(s.get("accessed","미확인"))} · {html.escape(s.get("note",""))}</li>' for s in data.get('sources',[]))}</ul><p class="muted">{limitations_text} · 시나리오는 AI 분석 입력의 가정이며 회사 가이던스나 컨센서스가 아닙니다.</p></section></main><footer>생성기 {html.escape(data.get('collected_at',''))} · 이 문서는 조사 도구이며 개인화된 금융 조언이나 매매 권유가 아닙니다.</footer><script>const D={payload};{JS}</script></body></html>'''
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.name != "latest.html":
        if out.read_text(encoding="utf-8") != page:
            raise FileExistsError(f"Dated report is immutable and already exists: {out}")
    else:
        out.write_text(page,encoding="utf-8")

def safe_link(value):
    parsed=urllib.parse.urlparse(str(value or ""))
    return str(value) if parsed.scheme in ("http","https") and parsed.netloc else "#"

def fmt(v,currency="KRW"):
    if v is None: return "N/A"
    if currency=="KRW": return f"{v/1e8:,.1f}억원"
    return f"{currency} {v/1e6:,.1f}m" if abs(v)>=1e6 else f"{currency} {v:,.0f}"

def pct(v):
    return "N/A" if v is None else f"{v*100:+.1f}%"

def fmt_price(v,currency="KRW"):
    if v is None: return "기준일 주가 미확인"
    if currency=="KRW": return f"₩{v:,.0f}/주"
    return f"{currency} {v:,.2f}/share"

def cards(items,title):
    return '<article class="box"><h3>'+html.escape(title)+'</h3><ul>'+''.join('<li>'+html.escape(x['text'])+((' <a href="'+html.escape(safe_link(x['source']),quote=True)+'" target="_blank" rel="noopener">근거</a>') if x.get('source') else '')+'</li>' for x in items)+'</ul></article>'

def checkpoints_table(items):
    if not items: return ""
    rows="".join("<tr><th>"+html.escape(x.get("item",""))+"</th><td>"+html.escape(x.get("current","미확인"))+"</td><td>"+html.escape(x.get("break_signal",""))+"</td><td>"+html.escape(x.get("next_check",""))+"</td><td>"+(f'<a href="{html.escape(safe_link(x.get("source")),quote=True)}" target="_blank" rel="noopener">근거</a>' if x.get("source") else "")+"</td></tr>" for x in items)
    return '<section><h2>가설 점검표</h2><p class="muted">투자 가설이 유지되는지 보는 항목입니다. 오른쪽 신호가 나타나면 가설을 다시 검토합니다.</p><div class=scroll><table class="text"><thead><tr><th>항목</th><th>현재 상태</th><th>가설이 깨지는 신호</th><th>다음 확인 시점</th><th></th></tr></thead><tbody>'+rows+'</tbody></table></div></section>'

def detail_sections(a):
    sections=a.get('sections',[])
    return ''.join('<details><summary>'+html.escape(s['title'])+'</summary><p>'+html.escape(s['body'])+'</p>'+''.join('<p><a href="'+html.escape(safe_link(src['url']),quote=True)+'" target="_blank" rel="noopener">'+html.escape(src['label'])+'</a></p>' for src in s.get('sources',[]))+'</details>' for s in sections)

def financial_table(rows,currency="KRW"):
    keys=[("revenue","매출"),("operating_income","영업이익"),("net_income","순이익"),("operating_cash_flow","영업현금흐름"),("capex","유형자산 취득"),("fcf","잉여현금흐름"),("eps","EPS"),("revenue_growth","매출 증가율"),("operating_growth","영업이익 증가율"),("operating_margin","영업이익률"),("net_margin","순이익률"),("roe","ROE"),("debt","부채비율")]
    out=[]; previous=None; split_flag=False
    for report in rows:
        m=report.get("metrics",{}); rev=m.get("revenue"); op=m.get("operating_income")
        prior=previous.get("metrics",{}) if previous else {}
        adjacent=previous is not None and report.get("year")-previous.get("year")==1
        fcf=m.get("operating_cash_flow")-abs(m.get("capex")) if m.get("operating_cash_flow") is not None and m.get("capex") is not None else None
        rev_prior=prior.get("revenue"); op_prior=prior.get("operating_income")
        grow=rev/rev_prior-1 if adjacent and rev is not None and rev_prior not in (None,0) else None
        opgrow=op/op_prior-1 if adjacent and op is not None and op_prior not in (None,0) else None
        opm=op/rev if rev not in (None,0) and op is not None else None
        nim=m.get("net_income")/rev if rev not in (None,0) and m.get("net_income") is not None else None
        roe=None; roe_basis=None
        if adjacent:
            current_parent=m.get("equity_parent"); previous_parent=prior.get("equity_parent")
            if m.get("net_income_parent") is not None and current_parent is not None and previous_parent is not None and current_parent>0 and previous_parent>0:
                roe=m["net_income_parent"]/((current_parent+previous_parent)/2); roe_basis="지배"
            else:
                current_total=m.get("equity"); previous_total=prior.get("equity")
                if m.get("net_income") is not None and current_total is not None and previous_total is not None and current_total>0 and previous_total>0:
                    roe=m["net_income"]/((current_total+previous_total)/2); roe_basis="연결"
        roe_text="N/A" if roe is None else f"{roe*100:.1f}% ({roe_basis})"
        debt=safe_ratio(m.get("liabilities"),m.get("equity"))
        eps_text="N/A" if m.get("eps") is None else f"{currency} {m.get('eps'):,.2f}/share"
        ni,ni_prior,eps,eps_prior=m.get("net_income_parent") or m.get("net_income"),prior.get("net_income_parent") or prior.get("net_income"),m.get("eps"),prior.get("eps")
        if adjacent and all(x not in (None,0) for x in (ni,ni_prior,eps,eps_prior)) and ni>0 and ni_prior>0 and eps>0 and eps_prior>0:
            if max((eps/eps_prior)/(ni/ni_prior),(ni/ni_prior)/(eps/eps_prior))>1.8:
                eps_text+=" *"; split_flag=True
        values={"revenue":fmt(rev,currency),"operating_income":fmt(op,currency),"net_income":fmt(m.get("net_income"),currency),"operating_cash_flow":fmt(m.get("operating_cash_flow"),currency),"capex":fmt(abs(m["capex"]),currency) if m.get("capex") is not None else "N/A","fcf":fmt(fcf,currency),"eps":eps_text,"debt":("N/A" if debt is None else f"{debt*100:.0f}%"),"revenue_growth":("N/A" if grow is None else f"{grow*100:.1f}%"),"operating_growth":("N/A" if opgrow is None else f"{opgrow*100:.1f}%"),"operating_margin":("N/A" if opm is None else f"{opm*100:.1f}%"),"net_margin":("N/A" if nim is None else f"{nim*100:.1f}%"),"roe":roe_text}
        out.append("<tr><th>"+str(report["year"])+"</th>"+"".join("<td>"+html.escape(values[k])+"</td>" for k,_ in keys)+"</tr>")
        previous=report
    label={"KRW":"억원","USD":"USD million"}.get(currency,currency+" million")
    return "<div class=scroll><table><thead><tr><th>연도</th>"+"".join(f"<th>{html.escape(n)} ({label})</th>" if k in ("revenue","operating_income","net_income","operating_cash_flow","capex","fcf") else f"<th>{html.escape(n)}</th>" for k,n in keys)+"</tr></thead><tbody>"+"".join(out)+"</tbody></table></div>"+('<p class="muted">* EPS 변화가 순이익 변화와 크게 다릅니다. 주식 분할·증자 등으로 주식 수가 바뀌었을 수 있어 연도 간 EPS를 직접 비교하지 마세요.</p>' if split_flag else '')

def interim_table(rows,currency="KRW"):
    if not rows: return "<p class=muted>중간 실적 자료 없음</p>"
    out=[]
    for r in rows:
        m=r.get("metrics",{}); basis=r.get("period_basis","source basis not recorded")
        label=("분기 단독 손익 · 현금흐름은 연초 누적" if "income_quarter_standalone_cashflow_ytd" in basis else ("분기 단독" if "standalone" in basis else ("연초 누적" if "ytd" in basis.lower() or "YTD" in basis else basis)))
        url=safe_link(r.get("source_url")); pq=(r.get("prior_metrics") or {}).get("quarter") or {}
        def yoy(k):
            cur,prev=m.get(k),pq.get(k)
            return pct(cur/prev-1) if cur is not None and prev not in (None,0) and prev>0 else "N/A"
        debt=safe_ratio(m.get("liabilities"),m.get("equity"))
        cells=[fmt(m.get("revenue"),currency),yoy("revenue"),fmt(m.get("operating_income"),currency),yoy("operating_income"),fmt(m.get("net_income"),currency),("N/A" if m.get("eps") is None else format(m["eps"],",.0f")),yoy("eps"),fmt(m.get("operating_cash_flow"),currency),"N/A" if debt is None else f"{debt*100:.0f}%"]
        out.append("<tr><th>"+html.escape(str(r.get("year"))+" "+str(r.get("report")))+"<small>"+html.escape(label)+" · 공시 "+html.escape(str(r.get("published") or "날짜 미확인"))+"</small></th>"+"".join("<td>"+html.escape(c)+"</td>" for c in cells)+f'<td><a href="{html.escape(url,quote=True)}" target="_blank" rel="noopener">원문 ↗</a></td></tr>')
    return "<div class=scroll><table><thead><tr><th>기간 / 기준</th><th>매출</th><th>매출 YoY</th><th>영업이익</th><th>영업이익 YoY</th><th>순이익</th><th>EPS</th><th>EPS YoY</th><th>영업현금흐름(누적)</th><th>부채비율</th><th>출처</th></tr></thead><tbody>"+"".join(out)+"</tbody></table></div><p class=\"muted\">YoY는 전년 같은 분기 대비(같은 공시의 비교 수치)입니다.</p>"

def chart_svg(rows,currency="KRW"):
    series=[(r['year'],r.get('metrics',{}).get('revenue')) for r in rows if r.get('metrics',{}).get('revenue') is not None]
    if len(series)<2:return '<p class="muted">비교 가능한 매출 자료 부족</p>'
    m=max(v for _,v in series); w=700; h=220
    bars=''.join(f'<g><rect x="{40+i*120}" y="{h-25-v/m*170:.1f}" width="62" height="{v/m*170:.1f}" rx="8"/><text x="{71+i*120}" y="{h-6}" text-anchor="middle">{y}</text><text x="{71+i*120}" y="{h-32-v/m*170:.1f}" text-anchor="middle">{(v/1e11 if currency=="KRW" else v/1e9):.0f}{("천억" if currency=="KRW" else "B")}</text></g>' for i,(y,v) in enumerate(series[-5:]))
    return f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="연결 매출 추이">{bars}</svg>'

CSS='''*{box-sizing:border-box}body{margin:0;background:#f5f6f2;color:#17221f;font:16px/1.6 system-ui,-apple-system,sans-serif}header{padding:28px max(22px,calc((100vw - 1080px)/2));background:#173d35;color:white}nav{display:flex;flex-wrap:wrap;gap:4px 16px;justify-content:space-between;color:#bad2ca;font-size:.9rem}h1{font-size:clamp(2rem,6vw,4rem);letter-spacing:-.05em;margin:40px 0 20px}h1 small{display:block;font-size:1rem;letter-spacing:0;color:#c5ddd5;margin-top:8px}.lede{max-width:760px;background:#ffffff14;padding:16px 20px;border-radius:14px}.lede p{margin:4px 0 0}main{max-width:1080px;padding:28px 20px 70px;margin:auto}section{margin:22px 0 46px}h2{font-size:1.55rem;letter-spacing:-.03em}h2 span{color:#71827d;font-size:.85rem;font-weight:500}.cards,.columns{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}.cards article,.box{background:white;padding:20px;border:1px solid #e3e9e5;border-radius:16px}.cards label,.cards small{display:block;color:#667671}.cards strong{display:block;font-size:1.3rem;margin:10px 0}.callout{background:#e2eee9;padding:20px;border-radius:14px}.box h3{margin-top:0}.box li{margin:10px 0}.chart{width:100%;max-height:260px;background:white;border-radius:16px;padding:10px}.chart rect{fill:#287760}.chart text{font-size:12px;fill:#50635e}.controls{display:flex;flex-wrap:wrap;gap:28px;padding:18px;background:#fff;border-radius:14px}.controls label{display:grid;gap:6px;min-width:230px}.scenario{margin:14px 0;display:flex;gap:12px;flex-wrap:wrap}.scenario div{background:#fff;border-radius:12px;padding:16px;min-width:150px}.scenario strong{display:block;font-size:1.2rem}details{padding:16px 0;border-bottom:1px solid #dce4df}summary{font-weight:650;cursor:pointer}.table-wrap{overflow:auto}.scroll{overflow:auto}.scenario-card{padding:18px;background:#fff;border:1px solid #e3e9e5;border-radius:14px}.scenario-card strong,.scenario-card small{display:block;margin-top:6px}table{border-collapse:collapse;width:100%;background:white}td,th{padding:12px;border-bottom:1px solid #e5e9e6;text-align:right;white-space:nowrap}th:first-child{text-align:left}.muted,small{color:#71817b}a{color:#236a55}footer{border-top:1px solid #dce4df;padding:24px;text-align:center;color:#71817b;font-size:.85rem}.text td,.text th{white-space:normal;text-align:left;min-width:150px;vertical-align:top}@media(max-width:600px){header{padding:22px}main{padding:18px 14px 50px}.cards{grid-template-columns:1fr}}'''
JS='''const g=document.getElementById('growth'),p=document.getElementById('pe'),box=document.getElementById('scenario');function recalc(){document.getElementById('growthOut').value=g.value+'%';document.getElementById('peOut').value=p.value+'배';const latest=D.base, shares=D.data.company.shares_outstanding, m=D.data.market||{}; if(latest===null||latest===undefined||!shares||shares<=0){box.innerHTML='<div><strong>주당가치 산출 불가</strong>기준 이익 또는 주식수 미확인</div>';return}const v=latest*Math.pow(1+Number(g.value)/100,2)*Number(p.value)/shares;const unit=D.data.company.currency==='KRW'?'원/주':D.data.company.currency+'/share';let note='기준일 종가 없음 · 주가 비교 안 함';if(m.price){const d=Math.round(v/m.price*100-100);note='종가 대비 '+(d>=0?'+':'')+d+'% · '+m.price_date+' 종가 기준';if(latest>0){const need=Math.pow(m.price*shares/(latest*Number(p.value)),0.5)-1;note+='<br>PER '+p.value+'배라면 현재가는 연 '+Math.round(need*100)+'% 이익 성장을 반영'}}box.innerHTML='<div><label>사용자 조정 시나리오</label><strong>'+Math.round(v).toLocaleString()+' '+unit+'</strong><small>'+note+'</small></div>'}g.addEventListener('input',recalc);p.addEventListener('input',recalc);recalc();'''
