"""Release one branch to its Fabric workspace: update from Git, apply config, refresh, smoke test.

Run (GitHub Actions, as the service principal):  python3 scripts/release.py --branch main --since <old sha>
Run (your machine, as you, through the Fabric CLI): python3 scripts/release.py --branch dev --auth fab </dev/null

For each workspace in config/workspaces.json on that branch:
 1. Scope: skip it if the push changed nothing in its folder or in config/ (unless --force).
 2. Check its Git connection: right branch, right folder, initialized.
 3. Service principal only: point its Git credentials at the shared Fabric GitHub connection
    (FABRIC_GIT_CONNECTION_ID). A service principal can't use "Automatic" Git credentials.
 4. Update the workspace from Git. The repo wins over the workspace (PreferRemote): a fix made by
    hand in the service is overwritten. Fix it in Git instead.
 5. For each semantic model in the folder: take it over (needed to set credentials), set the data
    source credentials from config/datasources.json and the refresh schedule from
    config/refresh-schedule.json, refresh it, then run a DAX query and compare the total with the
    data files in this repo.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fabric_client import ApiError, Client  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"


def cfg(name):
    return json.loads((CONFIG / name).read_text())


def models_in(folder):
    out = []
    for plat in sorted((ROOT / folder).rglob(".platform")):
        md = json.loads(plat.read_text())["metadata"]
        if md["type"] == "SemanticModel":
            out.append(md["displayName"])
    return out


def changed_paths(since):
    r = subprocess.run(["git", "diff", "--name-only", f"{since}..HEAD"], cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        return None  # unknown base (first push, force push): treat everything as changed
    return [p for p in r.stdout.splitlines() if p]


def in_scope(ws, paths):
    if paths is None:
        return True
    return any(p.startswith(ws["folder"] + "/") or p.startswith("config/") for p in paths)


# ---------- Git sync ----------

def check_connection(c, ws_id, ws):
    conn = c.get(f"workspaces/{ws_id}/git/connection")
    state = conn.get("gitConnectionState")
    d = conn.get("gitProviderDetails") or {}
    want_dir = "/" + ws["folder"].strip("/")
    if state != "ConnectedAndInitialized":
        raise RuntimeError(f"'{ws['name']}' Git connection is '{state}'. Connect it in workspace settings first (docs/setup.md).")
    if d.get("branchName") != ws["branch"] or d.get("directoryName", "").rstrip("/") != want_dir:
        raise RuntimeError(f"'{ws['name']}' is connected to {d.get('branchName')}:{d.get('directoryName')}, "
                           f"config/workspaces.json says {ws['branch']}:{want_dir}")
    return d


def use_shared_git_connection(c, ws_id):
    conn_id = os.environ.get("FABRIC_GIT_CONNECTION_ID")
    if not conn_id:
        return "own"
    c.request("patch", f"workspaces/{ws_id}/git/myGitCredentials",
              {"source": "ConfiguredConnection", "connectionId": conn_id})
    return "shared connection"


def update_from_git(c, ws_id, expect_sha=None):
    st = c.get(f"workspaces/{ws_id}/git/status")
    remote, head = st.get("remoteCommitHash"), st.get("workspaceHead")
    if expect_sha and remote and remote != expect_sha:
        print(f"  note: branch head is {remote[:7]}, this run is for {expect_sha[:7]} (a newer commit landed)")
    if remote == head:
        print(f"  workspace already at {str(head)[:7]}")
        return head, False
    body = {"remoteCommitHash": remote, "workspaceHead": head,
            "conflictResolution": {"conflictResolutionType": "Workspace", "conflictResolutionPolicy": "PreferRemote"},
            "options": {"allowOverrideItems": True}}
    status, headers, _ = c.request("post", f"workspaces/{ws_id}/git/updateFromGit", body)
    if status == 202:
        c.wait_operation(headers)
    print(f"  updated from Git: {str(head)[:7] if head else 'empty'} -> {remote[:7]}")
    return remote, True


# ---------- post-sync config (Power BI REST) ----------

def model_ids(c, ws_id):
    return {m["displayName"]: m["id"] for m in c.get(f"workspaces/{ws_id}/semanticModels").get("value", [])}


def ds(ws_id, mid):
    """Power BI dataset path. My workspace has no group id in the Power BI API, so ws_id=None means My workspace."""
    return f"groups/{ws_id}/datasets/{mid}" if ws_id else f"datasets/{mid}"


def take_over(c, ws_id, mid):
    c.request("post", f"{ds(ws_id, mid)}/Default.TakeOver", {}, audience="powerbi")


def set_credentials(c, ws_id, mid, model):
    spec = cfg("datasources.json")["models"][model]["credential"]
    sources = c.get(f"{ds(ws_id, mid)}/datasources", audience="powerbi").get("value", [])
    for ds in sources:
        body = {"credentialDetails": {"credentialType": spec["type"],
                                      "credentials": json.dumps({"credentialData": ""}),
                                      "encryptedConnection": "Encrypted", "encryptionAlgorithm": "None",
                                      "privacyLevel": spec["privacy_level"]}}
        c.request("patch", f"gateways/{ds['gatewayId']}/datasources/{ds['datasourceId']}", body, audience="powerbi")
    return len(sources)


def wanted_schedule(ws_name, model):
    s = cfg("refresh-schedule.json")
    own = s["schedules"].get(ws_name, {}).get(model)
    if own is None:
        return None
    return {**s["defaults"], **own}


def apply_schedule(c, ws_id, mid, want, dry_run=False):
    """Make the service's refresh schedule match `want`. Returns the list of fields that differed."""
    have = c.get(f"{ds(ws_id, mid)}/refreshSchedule", audience="powerbi") or {}
    keys = ["enabled"] + ([k for k in ("days", "times", "localTimeZoneId", "notifyOption")] if want["enabled"] else [])
    diff = [k for k in keys if have.get(k) != want.get(k)]
    if diff and not dry_run:
        body = {k: want[k] for k in keys}
        c.request("patch", f"{ds(ws_id, mid)}/refreshSchedule", {"value": body}, audience="powerbi")
    return diff


def refresh(c, ws_id, mid, wait=1200):
    c.request("post", f"{ds(ws_id, mid)}/refreshes", {"notifyOption": "NoNotification"}, audience="powerbi")
    start = time.time()
    time.sleep(10)
    while time.time() - start < wait:
        v = c.get(f"{ds(ws_id, mid)}/refreshes?$top=1", audience="powerbi").get("value", [])
        if v and v[0].get("status") not in (None, "Unknown", "NotStarted"):
            return v[0]
        time.sleep(15)
    raise RuntimeError("refresh did not finish in time")


def expected_totals():
    import pyarrow.parquet as pq
    t = pq.read_table(ROOT / "data/fact_sales.parquet", columns=["net_amount"])
    return {"net": int(sum(x for x in t.column("net_amount").to_pylist())), "rows": t.num_rows}


def smoke(c, ws_id, mid):
    q = {"queries": [{"query": 'EVALUATE ROW("net", [Net Sales], "rows", COUNTROWS(Sales))'}],
         "serializerSettings": {"includeNulls": True}}
    _, _, d = c.request("post", f"{ds(ws_id, mid)}/executeQueries", q, audience="powerbi")
    row = d["results"][0]["tables"][0]["rows"][0]
    got = {"net": int(round(row["[net]"])), "rows": int(row["[rows]"])}
    exp = expected_totals()
    return got, exp, got == exp


# ---------- main ----------

def release(c, ws, args):
    print(f"\n== {ws['name']} (branch {ws['branch']}, folder {ws['folder']})")
    ws_id = c.workspace_id(ws["name"])
    d = check_connection(c, ws_id, ws)
    print(f"  Git: {d.get('ownerName')}/{d.get('repositoryName')} {d.get('branchName')}:{d.get('directoryName')}")
    print(f"  Git credentials: {use_shared_git_connection(c, ws_id)}")
    head, updated = update_from_git(c, ws_id, os.environ.get("GITHUB_SHA"))
    ids = model_ids(c, ws_id)
    result = {"workspace": ws["name"], "commit": str(head)[:7], "updated": updated, "models": []}
    for model in models_in(ws["folder"]):
        mid = ids.get(model)
        if not mid:
            raise RuntimeError(f"model '{model}' is in Git but not in '{ws['name']}' after the update")
        r = {"model": model}
        take_over(c, ws_id, mid)
        r["datasources"] = set_credentials(c, ws_id, mid, model)
        want = wanted_schedule(ws["name"], model)
        if want is None:
            r["schedule"] = "not managed"
        else:
            changed = apply_schedule(c, ws_id, mid, want)
            r["schedule"] = f"changed: {', '.join(changed)}" if changed else "as configured"
        if not args.skip_refresh:
            ref = refresh(c, ws_id, mid)
            r["refresh"] = ref["status"]
            if ref["status"] != "Completed":
                r["error"] = ref.get("serviceExceptionJson")
            else:
                got, exp, ok = smoke(c, ws_id, mid)
                r["smoke"] = "passed" if ok else f"FAILED: model {got}, data files {exp}"
        print("  " + json.dumps(r))
        result["models"].append(r)
    return result


def summary(results):
    lines = ["| Workspace | Commit | Model | Refresh | Smoke test | Schedule |", "|---|---|---|---|---|---|"]
    for res in results:
        for m in res["models"]:
            lines.append(f"| {res['workspace']} | {res['commit']} | {m['model']} | {m.get('refresh', 'skipped')} | "
                         f"{m.get('smoke', '-')} | {m['schedule']} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch", default=os.environ.get("GITHUB_REF_NAME"))
    ap.add_argument("--auth", choices=["azcli", "fab"], default="azcli")
    ap.add_argument("--since", help="commit before this push; only workspaces whose folder or config changed are released")
    ap.add_argument("--force", action="store_true", help="release even if nothing in scope changed")
    ap.add_argument("--skip-refresh", action="store_true")
    args = ap.parse_args()
    targets = [w for w in cfg("workspaces.json")["workspaces"] if w["branch"] == args.branch]
    if not targets:
        sys.exit(f"no workspace is mapped to branch '{args.branch}' in config/workspaces.json")
    paths = None if (args.force or not args.since or set(args.since) == {"0"}) else changed_paths(args.since)
    c = Client(args.auth)
    results, failed = [], False
    for ws in targets:
        if not in_scope(ws, paths):
            print(f"\n== {ws['name']}: nothing changed in {ws['folder']} or config/, skipped")
            continue
        try:
            res = release(c, ws, args)
        except (ApiError, RuntimeError) as e:
            print(f"::error title=Release failed: {ws['name']}::{e}")
            failed = True
            continue
        results.append(res)
        failed |= any(m.get("refresh", "Completed") != "Completed" or str(m.get("smoke", "")).startswith("FAILED")
                      for m in res["models"])
    if results:
        table = summary(results)
        print("\n" + table)
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
                f.write("### Release\n\n" + table + "\n")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
