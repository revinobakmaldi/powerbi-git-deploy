"""What changed in a semantic model between two model.bim files, as Markdown for a PR comment.

Run:  python3 scripts/model_diff.py base.bim head.bim [--title "Kalaraya Sales"]

Lists tables, columns, measures and relationships that were added, removed or changed, with the
old and new DAX for changed measures. A reviewer who doesn't read TMDL can still see what moves.
"""
import argparse
import json
from pathlib import Path


def load(path):
    if not path or not Path(path).exists():
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))["model"]


def text(v):
    return "\n".join(v) if isinstance(v, list) else (v or "")


def index(m):
    out = {"tables": {}, "columns": {}, "measures": {}, "relationships": {}}
    for t in (m or {}).get("tables", []):
        out["tables"][t["name"]] = {"partitions": [text(p.get("source", {}).get("expression")) for p in t.get("partitions", [])]}
        for c in t.get("columns", []):
            out["columns"][f"{t['name']}[{c['name']}]"] = {k: c.get(k) for k in ("dataType", "sourceColumn", "formatString", "isHidden", "summarizeBy", "description")}
        for ms in t.get("measures", []):
            out["measures"][f"{t['name']}[{ms['name']}]"] = {"expression": text(ms.get("expression")).strip(),
                                                             **{k: ms.get(k) for k in ("formatString", "description", "displayFolder")}}
    for r in (m or {}).get("relationships", []):
        key = f"{r['fromTable']}[{r['fromColumn']}] → {r['toTable']}[{r['toColumn']}]"
        out["relationships"][key] = {k: r.get(k) for k in ("isActive", "crossFilteringBehavior", "fromCardinality", "toCardinality")}
    return out


def diff(base, head):
    a, b = index(base), index(head)
    res = {}
    for kind in a:
        added = sorted(set(b[kind]) - set(a[kind]))
        removed = sorted(set(a[kind]) - set(b[kind]))
        changed = []
        for k in sorted(set(a[kind]) & set(b[kind])):
            if a[kind][k] != b[kind][k]:
                fields = [f for f in b[kind][k] if a[kind][k].get(f) != b[kind][k].get(f)]
                changed.append((k, fields, a[kind][k], b[kind][k]))
        res[kind] = (added, removed, changed)
    return res


def markdown(res, title, base_missing):
    lines = [f"### Model changes: {title}", ""]
    if base_missing:
        lines += ["New model: it does not exist on the target branch yet.", ""]
    total = sum(len(x) for v in res.values() for x in v)
    if total == 0:
        return "\n".join(lines + ["No changes to tables, columns, measures or relationships."])
    rows = [f"| {kind.capitalize()} | {len(a)} | {len(r)} | {len(c)} |" for kind, (a, r, c) in res.items() if a or r or c]
    lines += ["| Object | Added | Removed | Changed |", "|---|---|---|---|", *rows, ""]
    for kind, (added, removed, changed) in res.items():
        for k in added:
            lines.append(f"- ➕ {kind[:-1]} `{k}`")
        for k in removed:
            lines.append(f"- ➖ {kind[:-1]} `{k}`")
        for k, fields, old, new in changed:
            lines.append(f"- ✏️ {kind[:-1]} `{k}`: {', '.join(fields)} changed")
            if "expression" in fields:
                lines += ["  <details><summary>DAX before and after</summary>", "",
                          "  ```dax", *("  " + ln for ln in str(old["expression"]).splitlines()), "  ```",
                          "  ```dax", *("  " + ln for ln in str(new["expression"]).splitlines()), "  ```",
                          "  </details>"]
            for f in fields:
                if f not in ("expression", "partitions"):
                    lines.append(f"  - {f}: `{old.get(f)}` → `{new.get(f)}`")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("head")
    ap.add_argument("--title")
    a = ap.parse_args()
    base, head = load(a.base), load(a.head)
    print(markdown(diff(base, head), a.title or Path(a.head).stem, base is None))


if __name__ == "__main__":
    main()
