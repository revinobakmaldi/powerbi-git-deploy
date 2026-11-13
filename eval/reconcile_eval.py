"""Eval for the daily reconcile job: drift planted in the service must be reported, then fixed.

Run:  python3 eval/reconcile_eval.py [--workspace "Kalaraya Prod"]

Needs `gh` (to start the Reconcile workflow on main) and `fab` signed in as a workspace admin
(to plant the drift the way a person would in the portal). Steps:

1. As you: take the model over, set its credentials and move the refresh time to 07:30.
2. Reconcile with dry run: must say "would fix: times" and leave the schedule at 07:30.
3. Reconcile for real: must say "fixed: times"; the schedule is back to the config time and
   the model is owned by the service principal again.
4. Reconcile with dry run again: must say "matches config".

Writes eval/results/reconcile-<date>.md. Exit code 1 if any step is not as expected.
"""
import argparse
import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from fabric_client import Client  # noqa: E402
from release import ROOT, ds, model_ids, set_credentials, take_over, wanted_schedule  # noqa: E402

MODEL = "Kalaraya Sales"
DRIFT_TIME = "07:30"


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if r.returncode:
        raise RuntimeError(f"{' '.join(cmd)}\n{r.stdout}\n{r.stderr}")
    return r.stdout.strip()


def run_reconcile(dry_run):
    """Start the Reconcile workflow on main, wait, return (run url, the row for each workspace)."""
    before = {r["databaseId"] for r in json.loads(sh(["gh", "run", "list", "--workflow", "reconcile.yml", "-L", "20",
                                                      "--json", "databaseId"]))}
    sh(["gh", "workflow", "run", "reconcile.yml", "--ref", "main", "-f", f"dry_run={'true' if dry_run else 'false'}"])
    run = None
    for _ in range(60):
        time.sleep(5)
        runs = json.loads(sh(["gh", "run", "list", "--workflow", "reconcile.yml", "-L", "5",
                              "--json", "databaseId,status,url"]))
        new = [r for r in runs if r["databaseId"] not in before]
        if new:
            run = new[0]
            break
    if not run:
        raise RuntimeError("the Reconcile run did not start")
    subprocess.run(["gh", "run", "watch", str(run["databaseId"])], capture_output=True, stdin=subprocess.DEVNULL)
    log = sh(["gh", "run", "view", str(run["databaseId"]), "--log"])
    rows = {}
    for line in log.splitlines():
        cells = [c.strip() for c in line.split("Z ", 1)[-1].split("|")]
        if len(cells) == 5 and cells[2] == MODEL:
            rows[cells[1]] = cells[3]
    return run["url"], rows


def schedule(c, ws_id, mid):
    return c.get(f"{ds(ws_id, mid)}/refreshSchedule", audience="powerbi")


def owner(c, ws_id, mid):
    return c.get(f"{ds(ws_id, mid)}", audience="powerbi").get("configuredBy", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="Kalaraya Prod")
    a = ap.parse_args()
    c = Client("fab")
    ws_id = c.workspace_id(a.workspace)
    mid = model_ids(c, ws_id)[MODEL]
    want = wanted_schedule(a.workspace, MODEL)
    steps, ok_all = [], True

    def check(name, ok, detail, url="-"):
        nonlocal ok_all
        ok_all &= ok
        steps.append((name, detail, url, ok))
        print(f"{'OK ' if ok else 'BAD'} {name}: {detail}")

    owner_before = owner(c, ws_id, mid)
    take_over(c, ws_id, mid)
    set_credentials(c, ws_id, mid, MODEL)
    c.request("patch", f"{ds(ws_id, mid)}/refreshSchedule", {"value": {"times": [DRIFT_TIME]}}, audience="powerbi")
    s = schedule(c, ws_id, mid)
    check("plant drift (as a person)", s["times"] == [DRIFT_TIME] and owner(c, ws_id, mid) != owner_before,
          f"times {s['times']}, owner changed from the service principal to you")

    url, rows = run_reconcile(dry_run=True)
    s = schedule(c, ws_id, mid)
    check("dry run reports", rows.get(a.workspace) == "would fix: times" and s["times"] == [DRIFT_TIME],
          f"row '{rows.get(a.workspace)}', times still {s['times']}", url)

    url, rows = run_reconcile(dry_run=False)
    s = schedule(c, ws_id, mid)
    back = owner(c, ws_id, mid) == owner_before
    check("real run fixes", rows.get(a.workspace) == "fixed: times" and s["times"] == want["times"] and back,
          f"row '{rows.get(a.workspace)}', times {s['times']}, owner back to the service principal: {back}", url)

    url, rows = run_reconcile(dry_run=True)
    check("dry run after fix", all(v == "matches config" for v in rows.values()) and len(rows) >= 1,
          "; ".join(f"{k}: {v}" for k, v in rows.items()), url)

    date = datetime.date.today().isoformat()
    lines = [f"# Reconcile eval, {date}, {a.workspace}", "",
             f"Result: **{'PASS' if ok_all else 'FAIL'}**, {sum(s[3] for s in steps)} of {len(steps)} steps as expected.", "",
             "| Step | What happened | Run | OK |", "|---|---|---|---|"]
    lines += [f"| {n} | {d} | {f'[run]({u})' if u != '-' else '-'} | {'✅' if ok else '❌'} |" for n, d, u, ok in steps]
    out = ROOT / "eval/results" / f"reconcile-{date}.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
