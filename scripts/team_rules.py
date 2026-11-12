"""Team rules for a semantic model, read from the model.bim that tools/tmdl-check writes.

Run:  python3 scripts/team_rules.py build/<Name>.bim

These are rules this team wants to block a merge on. The Best Practice Analyzer covers general
modelling advice; these cover what it leaves as a warning or can't see:

- T1 every measure has a description (it shows as a tooltip, and the AI in Build 1 reads it)
- T2 every measure has a format string
- T3 every measure sits in a display folder
- T4 every Table[column] and [measure] that a measure refers to exists in the model.
     TMDL and the analyzer both accept a measure that points at a renamed column; it only breaks
     when someone opens a visual.
- T5 the model's DataUrl matches config/datasources.json, so every workspace reads the same files
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = re.compile(r"(?:'((?:[^']|'')+)'|\b([A-Za-z_][A-Za-z0-9_]*))?\[([^\]]+)\]")
STRING = re.compile(r'"(?:[^"]|"")*"')
COMMENT = re.compile(r"//[^\n]*|--[^\n]*|/\*.*?\*/", re.S)


def expr_text(e):
    return "\n".join(e) if isinstance(e, list) else (e or "")


def check(bim):
    m = json.loads(Path(bim).read_text(encoding="utf-8"))["model"]
    name = Path(bim).stem
    out = []
    tables = {t["name"]: t for t in m.get("tables", [])}
    cols = {t: {c["name"] for c in tables[t].get("columns", [])} for t in tables}
    meas = {ms["name"]: t for t in tables for ms in tables[t].get("measures", [])}

    for t, tab in tables.items():
        for ms in tab.get("measures", []):
            where = f"{t}[{ms['name']}]"
            if not ms.get("description", "").strip():
                out.append(("T1", where, "measure has no description"))
            if not ms.get("formatString", "").strip():
                out.append(("T2", where, "measure has no format string"))
            if not ms.get("displayFolder", "").strip():
                out.append(("T3", where, "measure is not in a display folder"))
            dax = COMMENT.sub(" ", STRING.sub('""', expr_text(ms.get("expression"))))
            for q, plain, ref in REF.findall(dax):
                table = (q.replace("''", "'") if q else plain) or None
                if table:
                    if table not in tables:
                        out.append(("T4", where, f"refers to table '{table}', which does not exist"))
                    elif ref not in cols[table] and ref not in meas:
                        out.append(("T4", where, f"refers to {table}[{ref}], which does not exist"))
                elif ref not in meas:
                    out.append(("T4", where, f"refers to measure [{ref}], which does not exist"))

    cfg = json.loads((ROOT / "config/datasources.json").read_text())["models"].get(name)
    if cfg:
        url = None
        for e in m.get("expressions", []):
            if e["name"] == "DataUrl":
                mt = re.match(r'\s*"([^"]*)"', expr_text(e.get("expression")))
                url = mt.group(1) if mt else None
        if url != cfg["data_url"]:
            out.append(("T5", "DataUrl", f"model reads '{url}' but config/datasources.json says '{cfg['data_url']}'"))
    return out


def main():
    bad = 0
    for bim in sys.argv[1:]:
        found = check(bim)
        bad += len(found)
        print(f"team rules: {Path(bim).stem}: {'ok' if not found else f'{len(found)} problem(s)'}")
        for rule, where, msg in found:
            print(f"::error title=Team rule {rule}::{Path(bim).stem} {where}: {msg}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
