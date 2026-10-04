from __future__ import annotations
import argparse,json,os
from pathlib import Path
from .core import ROOT,build_report,collect_apr,collect_sec
from .delta import write_delta
from .weekly import build_weekly_report

def main():
 p=argparse.ArgumentParser(description="Stockdy research collection and report tools"); sub=p.add_subparsers(dest="cmd",required=True)
 c=sub.add_parser("collect-apr");c.add_argument("--out",type=Path,default=ROOT/"data/apr/latest.json")
 s=sub.add_parser("collect-sec");s.add_argument("ticker",nargs="?",default="AAPL");s.add_argument("--out",type=Path)
 r=sub.add_parser("report");r.add_argument("data",type=Path);r.add_argument("--out",type=Path,default=ROOT/"reports/apr/latest.html")
 d=sub.add_parser("weekly-diff");d.add_argument("previous",type=Path);d.add_argument("current",type=Path);d.add_argument("--out",type=Path,default=ROOT/"reports/weekly/latest.json")
 w=sub.add_parser("weekly-report");w.add_argument("data",type=Path);w.add_argument("--out",type=Path)
 a=p.parse_args()
 if a.cmd=="collect-apr":
  key=os.environ.get("DART_API_KEY")
  if not key:p.error("DART_API_KEY environment variable is required")
  data=collect_apr(key,a.out);print(f"Collected {len(data['reports'])} APR filing periods -> {a.out}")
 elif a.cmd=="collect-sec":
  data=collect_sec(a.ticker,a.out);print(f"Collected {len(data['reports'])} SEC annual periods for {data['company']['ticker']}")
 elif a.cmd=="report":
  data=json.loads(a.data.read_text(encoding="utf-8"));build_report(data,a.out);print(f"Rendered report -> {a.out}")
 elif a.cmd=="weekly-diff":
  result=write_delta(a.previous,a.current,a.out);print(f"Compared {result['ticker']} evidence: {len(result['changes'])} changed facts -> {a.out}")
 elif a.cmd=="weekly-report":
  data=json.loads(a.data.read_text(encoding="utf-8"))
  output=a.out or ROOT/"reports/weekly"/(data.get("week_ending",data.get("as_of","latest"))+".html")
  build_weekly_report(data,output);print(f"Rendered weekly HTML -> {output}")
if __name__=="__main__":main()
