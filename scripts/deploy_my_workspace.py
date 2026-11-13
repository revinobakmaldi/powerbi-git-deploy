"""Fallback for a free Power BI licence: deploy the model to your own "My workspace".

Run:  python3 scripts/deploy_my_workspace.py </dev/null

No Fabric capacity, no Git sync, no service principal: the Fabric CLI (`fab`, signed in as you)
imports the model folder, then the same steps as the release job run: set the data source
credentials, refresh, and compare the total with the data files. Run it after you merge to main.
Run `fab` commands with stdin closed (`</dev/null`); it can hang otherwise.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fabric_client import Client  # noqa: E402
from release import ROOT, model_ids, refresh, set_credentials, smoke  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", default="workspace/kalaraya")
    ap.add_argument("--workspace", default="My workspace")
    a = ap.parse_args()
    c = Client("fab")
    ws_id = c.workspace_id(a.workspace)
    failed = False
    for item in sorted((ROOT / a.folder).glob("*.SemanticModel")):
        name = json.loads((item / ".platform").read_text())["metadata"]["displayName"]
        r = subprocess.run(["fab", "import", f"{a.workspace}.Personal/{name}.SemanticModel", "-i", str(item), "-f"],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=900)
        if r.returncode:
            sys.exit(f"import failed: {(r.stdout + r.stderr)[-800:]}")
        mid = model_ids(c, ws_id)[name]
        n = set_credentials(c, None, mid, name)
        ref = refresh(c, None, mid)
        res = {"model": name, "datasources": n, "refresh": ref["status"]}
        if ref["status"] == "Completed":
            got, exp, ok = smoke(c, None, mid)
            res["smoke"] = "passed" if ok else f"FAILED: model {got}, data files {exp}"
            failed |= not ok
        else:
            res["error"] = ref.get("serviceExceptionJson")
            failed = True
        print(json.dumps(res, indent=2))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
