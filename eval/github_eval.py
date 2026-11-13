"""Eval on GitHub: real pull requests with planted bugs must turn red on the right check.

Run:  python3 eval/github_eval.py [--base dev] [--cases tmdl-syntax,bpa-only,...]

Needs `gh` signed in with push rights. For each case it branches from origin/<base>, plants the
change (same functions as eval/run_eval.py), pushes, opens a pull request, waits for the
"PR checks" workflow and reads which steps failed. The failing set must equal the expected set.
Then it closes the pull request (it stays visible as proof) and deletes the branch.

On GitHub the Best Practice Analyzer runs too, so the "bpa-only" case must fail there and only there.
The analyzer job runs only when the "Files and model" job passed.
Writes eval/results/github-<date>.md. Exit code 1 if any case fails.
"""
import argparse
import datetime
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_eval  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
STEP = {
    "Folder structure": "structure",
    "Python scripts lint": "lint",
    "JSON files parse": "json",
    "Item names and logicalIds": "names",
    "Config covers every workspace and model": "config",
    "Read TMDL with Microsoft's serializer": "tmdl",
    "Team rules": "team_rules",
    "Run the rules in config/bpa-rules.json (severity 3 fails)": "bpa",
}
DEFAULT = ["clean", "tmdl-syntax", "measure-no-description", "folder-renamed", "bpa-only", "valid-measure-change"]


def sh(cmd, cwd=None, check=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if check and r.returncode:
        raise RuntimeError(f"{' '.join(cmd)}\n{r.stdout}\n{r.stderr}")
    return r.stdout.strip()


def wait_run(repo, sha, timeout=1500):
    start = time.time()
    while time.time() - start < timeout:
        runs = json.loads(sh(["gh", "run", "list", "-R", repo, "--workflow", "pr-checks.yml", "--commit", sha,
                              "--json", "databaseId,status,conclusion,url"]))
        if runs and runs[0]["status"] == "completed":
            return runs[0]
        time.sleep(20)
    raise RuntimeError(f"no finished PR checks run for {sha} after {timeout}s")


def failed_checks(repo, run_id):
    jobs = json.loads(sh(["gh", "run", "view", str(run_id), "-R", repo, "--json", "jobs"]))["jobs"]
    failed, ran = set(), set()
    for job in jobs:
        for st in job.get("steps", []):
            if st["name"] in STEP and st["conclusion"] in ("success", "failure"):
                ran.add(STEP[st["name"]])
                if st["conclusion"] == "failure":
                    failed.add(STEP[st["name"]])
    return failed, ran


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="dev")
    ap.add_argument("--cases", default=",".join(DEFAULT))
    a = ap.parse_args()
    repo = sh(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], cwd=HERE)
    cases = {c[0]: c for c in run_eval.CASES}
    cases["clean"] = ("clean", lambda r: None, set(), "no change: every check passes")
    expected_extra = {"bpa-only": {"bpa"}}
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    rows, all_ok = [], True
    tmp = Path(tempfile.mkdtemp(prefix="pbi-gh-eval-"))
    src = tmp / "src"
    sh(["git", "clone", "--quiet", f"https://github.com/{repo}.git", str(src)])
    for name in a.cases.split(","):
        _, change, want, what = cases[name]
        want = set(want) | expected_extra.get(name, set())
        branch = f"eval/{name}-{stamp}"
        sh(["git", "checkout", "-q", "-B", branch, f"origin/{a.base}"], cwd=src)
        change(src)
        sh(["git", "add", "-A", "--force"], cwd=src)  # --force: the .pbix case plants a file .gitignore would skip
        sh(["git", "commit", "-q", "--allow-empty", "-m", f"[eval] planted: {what}"], cwd=src)
        sha = sh(["git", "rev-parse", "HEAD"], cwd=src)
        sh(["git", "push", "-q", "origin", branch], cwd=src)
        pr = sh(["gh", "pr", "create", "-R", repo, "--base", a.base, "--head", branch,
                 "--title", f"[eval] {name}: {what}",
                 "--body", "Opened by `eval/github_eval.py`. It plants one change on purpose and checks that "
                           "the right check fails. It is closed without merging."])
        run = wait_run(repo, sha)
        got, ran = failed_checks(repo, run["databaseId"])
        ok = got == want
        all_ok &= ok
        rows.append((name, what, ", ".join(sorted(want)) or "none", ", ".join(sorted(got)) or "none", pr, run["url"], ok))
        print(f"{'OK ' if ok else 'BAD'} {name}: expected {sorted(want)}, failed {sorted(got)}  {pr}")
        sh(["gh", "pr", "close", pr, "-R", repo, "--comment",
            f"Eval case `{name}`: expected failing checks {sorted(want) or 'none'}, got {sorted(got) or 'none'} "
            f"({'as expected' if ok else 'NOT as expected'}). Closed on purpose.", "--delete-branch"], check=False)
        sh(["git", "checkout", "-q", "--detach"], cwd=src)
        sh(["git", "reset", "-q", "--hard"], cwd=src)
        sh(["git", "clean", "-qfd"], cwd=src)

    date = datetime.date.today().isoformat()
    base_sha = sh(["git", "rev-parse", "--short", f"origin/{a.base}"], cwd=src)
    lines = [f"# GitHub eval, {date}, {a.base} at {base_sha}", "",
             f"Result: **{'PASS' if all_ok else 'FAIL'}**, {sum(r[6] for r in rows)} of {len(rows)} pull requests as expected.", "",
             "| Case | What it plants | Must fail | Failed | Pull request | Run | OK |", "|---|---|---|---|---|---|---|"]
    lines += [f"| {n} | {w} | {e} | {g} | [{p.rsplit('/', 1)[-1]}]({p}) | [run]({u}) | {'✅' if ok else '❌'} |"
              for n, w, e, g, p, u, ok in rows]
    out = HERE / "eval/results" / f"github-{date}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
