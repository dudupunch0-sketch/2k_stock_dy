"""Compact evidence-only week-over-week comparison."""
from __future__ import annotations
import json
from pathlib import Path

def compare(previous: dict, current: dict) -> dict:
    old={(x["year"],x["report"]):x for x in previous.get("periods",[])}
    changes=[]
    for item in current.get("periods",[]):
        key=(item["year"],item["report"]); before=old.get(key)
        if before is None:
            changes.append({"period":f"{key[0]} {key[1]}","type":"new_period","current":item.get("metrics",{}),"source":item.get("source_url")})
            continue
        for metric,value in item.get("metrics",{}).items():
            prior=before.get("metrics",{}).get(metric)
            if prior!=value:
                changes.append({"period":f"{key[0]} {key[1]}","metric":metric,"previous":prior,"current":value,"source":item.get("source_url")})
    return {"schema_version":1,"ticker":current.get("company",{}).get("ticker"),"as_of":current.get("as_of"),"previous_as_of":previous.get("as_of"),"changes":changes,"news":"not collected by this pipeline","price":"not collected by this pipeline","analyst_estimates":"not collected by this pipeline","sources":current.get("sources",[])}

def write_delta(previous_path: Path,current_path: Path,out: Path):
    old=json.loads(previous_path.read_text(encoding="utf-8")); new=json.loads(current_path.read_text(encoding="utf-8"))
    data=compare(old,new); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); return data
