"""Process explicit collection requests and preserve immutable evidence snapshots."""
import datetime as dt
import json
import os
import re
from pathlib import Path
from .core import ROOT, collect_apr

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    tmp.replace(path)

def main():
    key=os.environ.get("DART_API_KEY")
    if not key:
        for request_path in sorted((ROOT/"requests").glob("*.json")):
            request=json.loads(request_path.read_text(encoding="utf-8"))
            if request.get("status") not in ("fulfilled","rejected"):
                request.update(status="failed",error="DART_API_KEY is unavailable",completed_at=dt.datetime.now(dt.timezone.utc).isoformat())
                save(request_path,request)
        raise SystemExit("DART_API_KEY is unavailable")
    universe=json.loads((ROOT/"config/universe.json").read_text(encoding="utf-8"))
    allowed=universe.get("holdings",[])+universe.get("watchlist",[])
    for path in sorted((ROOT/"requests").glob("*.json")):
        req=json.loads(path.read_text(encoding="utf-8")); rid=req.get("request_id","")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}",rid): raise SystemExit("Invalid request id")
        if req.get("status")=="fulfilled": continue
        company=next((x for x in allowed if x.get("ticker")==req.get("ticker") and x.get("market")==req.get("market")),None)
        if not company or company.get("market")!="KRX":
            req.update(status="rejected",error="Not an enabled KRX holding/watchlist company")
            save(path,req); continue
        target=ROOT/"data"/"requests"/rid/"snapshot.json"
        if target.exists():
            data=json.loads(target.read_text(encoding="utf-8"))
            history=ROOT/"data"/"history"/company["ticker"]/(data["as_of"]+"-"+rid+".json")
            if not history.exists():
                packet={"request_id":rid,"source_snapshot":str(target.relative_to(ROOT)),"company":data["company"],"as_of":data["as_of"],"collected_at":data["collected_at"],"periods":[{"year":x["year"],"report":x["report"],"basis":x.get("period_basis"),"published":x.get("published"),"source_url":x.get("source_url"),"metrics":x.get("metrics",{})} for x in data.get("reports",[])],"sources":data.get("sources",[]),"market":data.get("market",{}),"analysis":data.get("analysis",{})}
                save(history,packet)
            req.update(status="fulfilled",result=str(target.relative_to(ROOT)),evidence_packet=str(history.relative_to(ROOT)),completed_at=dt.datetime.now(dt.timezone.utc).isoformat())
            save(path,req); continue
        req.update(status="collecting",started_at=dt.datetime.now(dt.timezone.utc).isoformat()); save(path,req)
        try:
            if not re.fullmatch(r"\d{8}",str(company.get("corp_code",""))): raise ValueError("Invalid configured corp_code")
            if not re.fullmatch(r"[A-Z0-9.-]{1,16}",str(company.get("ticker",""))): raise ValueError("Invalid configured ticker")
            analysis_name=company.get("analysis_file")
            analysis=(ROOT/"analysis"/analysis_name).resolve() if analysis_name else None
            if analysis and ROOT.joinpath("analysis").resolve() not in analysis.parents: raise ValueError("analysis_file must stay inside analysis/")
            data=collect_apr(key,target,corp=company["corp_code"],stock=company["ticker"],company_name=company.get("name",company["ticker"]),analysis_path=analysis)
            packet={"request_id":rid,"source_snapshot":str(target.relative_to(ROOT)),"company":data["company"],"as_of":data["as_of"],"collected_at":data["collected_at"],"periods":[{"year":x["year"],"report":x["report"],"basis":x["period_basis"],"published":x.get("published"),"source_url":x.get("source_url"),"metrics":x["metrics"]} for x in data["reports"]],"sources":data["sources"],"market":data["market"],"analysis":data["analysis"]}
            history=ROOT/"data"/"history"/company["ticker"]/(data["as_of"]+"-"+rid+".json")
            save(history,packet)
            req.update(status="fulfilled",result=str(target.relative_to(ROOT)),evidence_packet=str(history.relative_to(ROOT)),completed_at=dt.datetime.now(dt.timezone.utc).isoformat())
            save(path,req)
        except Exception as exc:
            req.update(status="failed",error=f"{type(exc).__name__}: {exc}",completed_at=dt.datetime.now(dt.timezone.utc).isoformat())
            save(path,req)
            raise
if __name__=="__main__": main()
