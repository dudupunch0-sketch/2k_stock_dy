from __future__ import annotations
import argparse,json,os
from pathlib import Path
from .core import ROOT,build_report,collect_apr,collect_sec,fetch_quote,fetch_naver
from .delta import write_delta
from .weekly import build_weekly_report
from . import universe

def main():
 p=argparse.ArgumentParser(description="Stockdy research collection and report tools"); sub=p.add_subparsers(dest="cmd",required=True)
 c=sub.add_parser("collect-apr");c.add_argument("--out",type=Path,default=ROOT/"data/apr/latest.json")
 s=sub.add_parser("collect-sec");s.add_argument("ticker",nargs="?",default="AAPL");s.add_argument("--out",type=Path)
 r=sub.add_parser("report");r.add_argument("data",type=Path);r.add_argument("--analysis",type=Path);r.add_argument("--out",type=Path,default=ROOT/"reports/apr/latest.html");r.add_argument("--refresh-price","--refresh-market",dest="refresh_price",action="store_true",help="fetch latest close and (KRX) Naver consensus/flows when the snapshot has none")
 d=sub.add_parser("weekly-diff");d.add_argument("previous",type=Path);d.add_argument("current",type=Path);d.add_argument("--out",type=Path,default=ROOT/"reports/weekly/latest.json")
 w=sub.add_parser("weekly-report");w.add_argument("data",type=Path);w.add_argument("--out",type=Path)
 u=sub.add_parser("universe",help="list/add/remove holdings and watchlist");us=u.add_subparsers(dest="action",required=True)
 us.add_parser("list")
 ua=us.add_parser("add");ua.add_argument("ticker");ua.add_argument("--name",required=True);ua.add_argument("--market",required=True,choices=universe.MARKETS);ua.add_argument("--kind",default="watchlist",choices=universe.LISTS);ua.add_argument("--corp-code");ua.add_argument("--cik");ua.add_argument("--notes")
 ur=us.add_parser("remove");ur.add_argument("ticker")
 mk=sub.add_parser("market",help="print latest close and (KRX) Naver consensus/target/flows/peers as JSON");mk.add_argument("ticker")
 t=sub.add_parser("analysis-template",help="write a blank analysis file to fill in");t.add_argument("out",type=Path)
 a=p.parse_args()
 if a.cmd=="universe":
  try:
   result=universe.listing() if a.action=="list" else (universe.add(a.ticker,a.name,a.market,a.kind,a.corp_code,a.cik,a.notes) if a.action=="add" else universe.remove(a.ticker))
  except ValueError as exc: p.exit(2,f"error: {exc}\n")
  print(json.dumps(result,ensure_ascii=False,indent=2));return
 if a.cmd=="market":
  code=a.ticker.upper()
  if code.isdigit():
   quote=next((q for q in (fetch_quote(code+s) for s in (".KS",".KQ")) if q.get("price")),fetch_quote(""));result={"ticker":code,"quote":quote,"naver":fetch_naver(code)}
  else: result={"ticker":code,"quote":fetch_quote(code.replace(".","-"))}
  print(json.dumps(result,ensure_ascii=False,indent=2));return
 if a.cmd=="analysis-template":
  out=a.out if a.out.is_absolute() else ROOT/a.out
  if out.exists(): p.exit(2,f"error: {out} already exists\n")
  out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(universe.TEMPLATE,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");print(f"Wrote template -> {out}");return
 if a.cmd=="collect-apr":
  key=os.environ.get("DART_API_KEY")
  if not key:p.error("DART_API_KEY environment variable is required")
  data=collect_apr(key,a.out);print(f"Collected {len(data['reports'])} APR filing periods -> {a.out}")
 elif a.cmd=="collect-sec":
  data=collect_sec(a.ticker,a.out);print(f"Collected {len(data['reports'])} SEC annual periods for {data['company']['ticker']}")
 elif a.cmd=="report":
  data_path=a.data if a.data.is_absolute() else ROOT/a.data
  data=json.loads(data_path.read_text(encoding="utf-8"))
  if a.analysis:
   analysis_path=a.analysis if a.analysis.is_absolute() else ROOT/a.analysis
   analysis_root=(ROOT/"analysis").resolve();analysis_path=analysis_path.resolve()
   if analysis_root not in analysis_path.parents or not analysis_path.is_file(): p.error("--analysis must name an existing JSON file under analysis/")
   data["analysis"]=json.loads(analysis_path.read_text(encoding="utf-8"))
  if a.refresh_price and not (data.get("market") or {}).get("price"):
   c=data["company"];sym=c["ticker"]
   for candidate in ([sym+".KS",sym+".KQ"] if c.get("market")=="KRX" else [sym.replace(".","-")]):
    quote=fetch_quote(candidate,c.get("shares_outstanding"),c.get("currency"))
    if quote.get("price"): data["market"]=quote;break
   print(f"Price: {data.get('market',{}).get('price')} ({data.get('market',{}).get('price_date')})")
  if a.refresh_price and data["company"].get("market")=="KRX" and not data.get("naver"):
   data["naver"]=fetch_naver(data["company"]["ticker"])
   print(f"Naver: consensus={'yes' if data['naver'].get('consensus') else 'no'} target={'yes' if data['naver'].get('target') else 'no'} peers={len(data['naver'].get('peers') or [])} errors={data['naver'].get('errors')}")
  output=a.out if a.out.is_absolute() else ROOT/a.out
  build_report(data,output);print(f"Rendered report -> {output}")
 elif a.cmd=="weekly-diff":
  result=write_delta(a.previous,a.current,a.out);print(f"Compared {result['ticker']} evidence: {len(result['changes'])} changed facts -> {a.out}")
 elif a.cmd=="weekly-report":
  data=json.loads(a.data.read_text(encoding="utf-8"))
  output=a.out or ROOT/"reports/weekly"/(data.get("week_ending",data.get("as_of","latest"))+".html")
  build_weekly_report(data,output);print(f"Rendered weekly HTML -> {output}")
if __name__=="__main__":main()
