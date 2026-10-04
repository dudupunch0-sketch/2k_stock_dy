"""Process user collection requests; holdings are only required for weekly coverage."""
import datetime as dt
import json
import os
import re
from pathlib import Path
from .core import ROOT, collect_apr, collect_sec, validate_snapshot

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    tmp.replace(path)

def evidence_packet(data,rid,target):
    return {"request_id":rid,"source_snapshot":str(target.relative_to(ROOT)),"company":data["company"],"as_of":data["as_of"],"collected_at":data["collected_at"],"periods":[{"year":x["year"],"report":x["report"],"basis":x.get("period_basis"),"published":x.get("published"),"source_url":x.get("source_url"),"metrics":x.get("metrics",{}),"ytd_metrics":x.get("ytd_metrics",{}),"standalone_metrics":x.get("standalone_metrics",{}),"instant_metrics":x.get("instant_metrics",{}),"metric_sources":x.get("metric_sources",{})} for x in data.get("reports",[])],"sources":data.get("sources",[]),"market":data.get("market",{}),"analysis":data.get("analysis",{})}

def main():
    key=os.environ.get("DART_API_KEY")
    universe=json.loads((ROOT/"config/universe.json").read_text(encoding="utf-8"))
    allowed=universe.get("holdings",[])+universe.get("watchlist",[])
    failures=[]
    for path in sorted((ROOT/"requests").glob("*.json")):
        req=json.loads(path.read_text(encoding="utf-8")); rid=req.get("request_id","")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}",rid): raise SystemExit("Invalid request id")
        if req.get("status")=="fulfilled": continue
        ticker=str(req.get("ticker","")).upper()
        if not re.fullmatch(r"[A-Z0-9.-]{1,16}",ticker):
            req.update(status="rejected",error="Invalid ticker"); save(path,req); continue
        company=next((x for x in allowed if str(x.get("ticker","")).upper()==ticker and x.get("market")==req.get("market")),None)
        manual=req.get("kind")=="detailed" and req.get("user_requested") is True
        if company is None and manual:
            company={"ticker":ticker,"name":req.get("company_name",ticker),"market":req.get("market"),"corp_code":req.get("corp_code"),"cik":req.get("cik"),"currency":req.get("currency"),"analysis_file":req.get("analysis_file"),"ir_url":req.get("ir_url")}
        if company is None:
            req.update(status="rejected",error="Add ticker to tracking list or mark an explicitly user-requested detailed analysis"); save(path,req); continue
        market=company.get("market")
        target=ROOT/"data"/"requests"/rid/"snapshot.json"
        try:
            if target.exists():
                data=json.loads(target.read_text(encoding="utf-8"))
                validate_snapshot(data)
                if data.get("source_status")!="success": raise ValueError("Existing snapshot is not a successful collection")
                if str(data.get("company",{}).get("ticker","")).upper()!=ticker:
                    raise ValueError("Existing snapshot ticker does not match request")
            elif market=="KRX":
                if not key: raise RuntimeError("DART_API_KEY unavailable for Korean filing collection")
                corp=str(company.get("corp_code",""))
                if not re.fullmatch(r"\d{8}",corp): raise ValueError("Invalid configured corp_code")
                analysis_name=company.get("analysis_file")
                analysis=(ROOT/"analysis"/analysis_name).resolve() if analysis_name else None
                if analysis and ROOT.joinpath("analysis").resolve() not in analysis.parents: raise ValueError("analysis_file must stay inside analysis/")
                data=collect_apr(key,target,corp=corp,stock=ticker,company_name=company.get("name",ticker),company_ir_url=company.get("ir_url"),analysis_path=analysis)
            elif market in ("NASDAQ","NYSE","US"):
                data=collect_sec(ticker,target)
            else:
                raise ValueError("Supported markets are KRX, NASDAQ, NYSE, and US")
            history=ROOT/"data"/"history"/ticker/(data["as_of"]+"-"+rid+".json")
            packet_ok=False
            if history.exists() and history.stat().st_size:
                try:
                    prior=json.loads(history.read_text(encoding="utf-8"))
                    packet_ok=bool(prior.get("request_id")==rid and prior.get("company") and prior.get("periods") is not None)
                except (ValueError,OSError):
                    packet_ok=False
            if not packet_ok:
                save(history,evidence_packet(data,rid,target))
            req.update(status="fulfilled",result=str(target.relative_to(ROOT)),evidence_packet=str(history.relative_to(ROOT)),completed_at=dt.datetime.now(dt.timezone.utc).isoformat())
            save(path,req)
        except Exception as exc:
            req.update(status="failed",error=f"{type(exc).__name__}: {exc}",completed_at=dt.datetime.now(dt.timezone.utc).isoformat())
            save(path,req); failures.append(rid)
    if failures: raise SystemExit("One or more collection requests failed; see request status files")

if __name__=="__main__": main()
