"""Eval for the PR checks: a clean clone must pass, and each planted bug must fail its own check only.

Run:  python3 eval/run_eval.py [--repo <path or URL>] [--keep]

1. Clones the repo (committed state only, not your working folder) into a temp folder.
2. Runs every local check, the same steps as the "Files and model" job in pr-checks.yml.
   All must pass, and the model diff of the model against itself must report no changes.
3. For each planted bug: a fresh copy, one change, every check again. The set of failing checks
   must equal the expected set, exactly. A check that fails too often is as wrong as one that
   never fails.
4. A valid change (a measure's DAX edited correctly) must pass every check and show up in the
   model diff.

The Best Practice Analyzer needs Windows (Tabular Editor 2), so it runs on GitHub only.
eval/github_eval.py covers it with real pull requests.
Writes eval/results/local-<date>.md. Exit code 1 if any case fails.
"""
import argparse
import datetime
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
MODEL = "workspace/kalaraya/Kalaraya Sales.SemanticModel"
DEF = MODEL + "/definition"
CHECKS = ["structure", "lint", "json", "names", "config", "tmdl", "team_rules"]


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def run_checks(repo):
    """Run the local checks like CI does; return {check: (passed, output)}."""
    res = {}
    for c in ["structure", "json", "names", "config"]:
        r = run([sys.executable, "scripts/check_repo.py", c], repo)
        res[c] = (r.returncode == 0, r.stdout + r.stderr)
    r = run([sys.executable, "-m", "pyflakes", "scripts", "eval"], repo)
    res["lint"] = (r.returncode == 0, r.stdout + r.stderr)
    shutil.rmtree(repo / "build", ignore_errors=True)
    r = run([sys.executable, "scripts/build_models.py", "--out", "build/head"], repo)
    res["tmdl"] = (r.returncode == 0, r.stdout + r.stderr)
    if res["tmdl"][0]:
        bims = sorted(str(p) for p in (repo / "build/head").glob("*.bim"))
        r = run([sys.executable, "scripts/team_rules.py", *bims], repo)
        res["team_rules"] = (r.returncode == 0, r.stdout + r.stderr)
    else:
        res["team_rules"] = (None, "skipped: TMDL did not read")  # CI skips it too
    return res


def edit(path, old, new, count=1):
    t = path.read_text()
    if old not in t:
        raise RuntimeError(f"planted-bug text not found in {path.name}: {old!r}")
    path.write_text(t.replace(old, new, count))


def bug_syntax(r):
    edit(r / DEF / "tables/Sales.tmdl", "formatString: #,0", "formatSting #,0")


def bug_relationship(r):
    edit(r / DEF / "relationships.tmdl", "toColumn: Store.store_id", "toColumn: Store.shop_id")


def bug_no_description(r):
    edit(r / DEF / "tables/Sales.tmdl", "\t/// Discounts given, in rupiah.\n", "")


def bug_renamed_column_in_dax(r):
    edit(r / DEF / "tables/Sales.tmdl", "SUM ( Sales[discount_amount] )", "SUM ( Sales[discount_amt] )")


def bug_data_url(r):
    edit(r / DEF / "expressions.tmdl", "/powerbi-git-deploy/main/data/", "/powerbi-git-deploy/dev/data/")


def bug_folder_renamed(r):
    (r / MODEL).rename(r / "workspace/kalaraya/Kalaraya Sales v2.SemanticModel")


def bug_copied_item(r):
    dst = r / "workspace/kalaraya/Kalaraya Sales Copy.SemanticModel"
    shutil.copytree(r / MODEL, dst)
    plat = json.loads((dst / ".platform").read_text())
    plat["metadata"]["displayName"] = "Kalaraya Sales Copy"  # renamed properly, but logicalId copied
    (dst / ".platform").write_text(json.dumps(plat, indent=2))


def bug_bad_json(r):
    edit(r / "config/refresh-schedule.json", '"times": ["06:00"],', '"times": ["06:00"],,')


def bug_pbix(r):
    (r / "workspace/kalaraya/Kalaraya Sales.pbix").write_bytes(b"PK\x03\x04 desktop file")


def bug_bpa_only(r):
    p = r / DEF / "tables/Product.tmdl"
    t = p.read_text()
    new = re.sub(r"(column list_price_2024\n(?:\t\t.*\n)*?\t\tsummarizeBy: )none", r"\1sum", t)
    if new == t:
        raise RuntimeError("planted-bug text not found in Product.tmdl")
    p.write_text(new)


def bug_shadowed_name(r):
    # the bug the first real release hit: a loop variable hiding a function of the same name
    edit(r / "scripts/release.py", "    for src in sources:", "    for ds in sources:")
    edit(r / "scripts/release.py", "{src['gatewayId']}/datasources/{src['datasourceId']}",
         "{ds['gatewayId']}/datasources/{ds['datasourceId']}")


def valid_change(r):
    edit(r / DEF / "tables/Sales.tmdl", "measure 'Items Sold' = SUM ( Sales[qty] )",
         "measure 'Items Sold' = SUMX ( Sales, Sales[qty] )")


# name, change, checks that must fail, what it shows
CASES = [
    ("tmdl-syntax", bug_syntax, {"tmdl"}, "a typo in a TMDL property"),
    ("relationship-missing-column", bug_relationship, {"tmdl"}, "a relationship to a column that doesn't exist"),
    ("measure-no-description", bug_no_description, {"team_rules"}, "a measure without a description (T1)"),
    ("dax-renamed-column", bug_renamed_column_in_dax, {"team_rules"}, "a measure pointing at a renamed column (T4)"),
    ("data-url-drift", bug_data_url, {"team_rules"}, "the model reading another branch's data (T5)"),
    ("folder-renamed", bug_folder_renamed, {"names"}, "a folder renamed without its .platform"),
    ("copied-item-same-logicalid", bug_copied_item, {"names", "config"}, "a copied model that kept the logicalId"),
    ("bad-json-config", bug_bad_json, {"json"}, "a broken config file"),
    ("pbix-committed", bug_pbix, {"structure"}, "a Desktop .pbix committed"),
    ("python-shadowed-name", bug_shadowed_name, {"lint"}, "a script variable hiding a function: fails only at release time"),
    ("bpa-only", bug_bpa_only, set(), "a visible numeric column that sums by default: only the analyzer (GitHub) catches it"),
    ("valid-measure-change", valid_change, set(), "a correct DAX change: passes, and the diff shows it"),
]


def failing(res):
    return {c for c, (ok, _) in res.items() if ok is False}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(HERE))
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="pbi-eval-"))
    clean = tmp / "clean"
    r = run(["git", "clone", "--quiet", a.repo, str(clean)], tmp)
    if r.returncode:
        sys.exit("clone failed: " + r.stderr)
    sha = run(["git", "rev-parse", "--short", "HEAD"], clean).stdout.strip()
    # build the tool once; every copy below reuses it
    run([sys.executable, "scripts/build_models.py", "--out", "build/head"], clean)
    rows, all_ok = [], True

    res = run_checks(clean)
    diff = run([sys.executable, "scripts/model_diff.py", "build/head/Kalaraya Sales.bim", "build/head/Kalaraya Sales.bim"], clean).stdout
    ok = not failing(res) and None not in [v[0] for v in res.values()] and "No changes" in diff
    rows.append(("clean clone", "every check passes; diff of the model with itself is empty", "none",
                 ", ".join(sorted(failing(res))) or "none", ok))
    all_ok &= ok
    (clean / "build/base").mkdir(parents=True, exist_ok=True)
    shutil.copy(clean / "build/head/Kalaraya Sales.bim", clean / "build/base/Kalaraya Sales.bim")

    for name, change, want, what in CASES:
        work = tmp / name
        shutil.copytree(clean, work, symlinks=True, ignore=shutil.ignore_patterns("build"))
        change(work)
        res = run_checks(work)
        got = failing(res)
        ok = got == want
        if name == "valid-measure-change":
            d = run([sys.executable, "scripts/model_diff.py", str(clean / "build/base/Kalaraya Sales.bim"),
                     "build/head/Kalaraya Sales.bim"], work).stdout
            ok &= "Sales[Items Sold]" in d and "expression changed" in d
        rows.append((name, what, ", ".join(sorted(want)) or "none", ", ".join(sorted(got)) or "none", ok))
        all_ok &= ok
        if not ok:
            for c, (passed, out) in res.items():
                print(f"--- {name} / {c}: {passed}\n{out[-1500:]}")

    date = datetime.date.today().isoformat()
    lines = [f"# Local eval, {date}, commit {sha}", "",
             f"Result: **{'PASS' if all_ok else 'FAIL'}**, {sum(r[4] for r in rows)} of {len(rows)} cases as expected.", "",
             "| Case | What it plants | Must fail | Failed | OK |", "|---|---|---|---|---|"]
    lines += [f"| {n} | {w} | {e} | {g} | {'✅' if ok else '❌'} |" for n, w, e, g, ok in rows]
    lines += ["", "The Best Practice Analyzer needs Windows, so it runs on GitHub only (eval/github_eval.py)."]
    out = HERE / "eval/results" / f"local-{date}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nwrote {out.relative_to(HERE)}")
    if not a.keep:
        shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
