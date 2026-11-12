"""Put each workspace's refresh schedule back to what config/refresh-schedule.json says.

Run:  python3 scripts/reconcile.py [--dry-run] [--auth azcli|fab]

The service turns a schedule off after 4 failed refreshes, and anyone with access can change it in
the portal. This job runs daily, compares the service with the config file and fixes any drift.
With --dry-run it only reports. It needs no repo change to run.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fabric_client import ApiError, Client  # noqa: E402
from release import apply_schedule, cfg, model_ids, models_in, wanted_schedule  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--auth", choices=["azcli", "fab"], default="azcli")
    a = ap.parse_args()
    c = Client(a.auth)
    rows, failed = [], False
    for ws in cfg("workspaces.json")["workspaces"]:
        try:
            ws_id = c.workspace_id(ws["name"])
            ids = model_ids(c, ws_id)
            for model in models_in(ws["folder"]):
                want = wanted_schedule(ws["name"], model)
                if want is None or model not in ids:
                    rows.append((ws["name"], model, "not managed" if want is None else "model not in workspace"))
                    continue
                diff = apply_schedule(c, ws_id, ids[model], want, dry_run=a.dry_run)
                verb = "would fix" if a.dry_run else "fixed"
                rows.append((ws["name"], model, f"{verb}: {', '.join(diff)}" if diff else "matches config"))
        except (ApiError, RuntimeError) as e:
            print(f"::error title=Reconcile failed: {ws['name']}::{e}")
            failed = True
    table = "\n".join(["| Workspace | Model | Refresh schedule |", "|---|---|---|"] + [f"| {w} | {m} | {s} |" for w, m, s in rows])
    print(table)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(f"### Reconcile{' (dry run)' if a.dry_run else ''}\n\n{table}\n")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
