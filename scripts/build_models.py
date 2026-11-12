"""Read every semantic model in workspace/ with tools/tmdl-check and write <out>/<Name>.bim.

Run:  python3 scripts/build_models.py [--out build/head] [--root .]

--root lets the PR workflow build the target branch's models from a second checkout, so
scripts/model_diff.py can compare before and after. Exit code 1 if any model fails to read.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
TOOL = HERE / "tools/tmdl-check"
DLL = TOOL / "bin/Release/net8.0/tmdl-check.dll"


def build_tool():
    if not DLL.exists():
        r = subprocess.run(["dotnet", "build", str(TOOL), "-c", "Release", "--nologo", "-v", "q"],
                           capture_output=True, text=True)
        if r.returncode:
            sys.exit("could not build tools/tmdl-check:\n" + r.stdout[-2000:] + r.stderr[-2000:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="build/head")
    ap.add_argument("--root", default=str(HERE))
    a = ap.parse_args()
    root, out = Path(a.root).resolve(), Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    build_tool()
    failed = 0
    items = sorted((root / "workspace").rglob("*.SemanticModel")) if (root / "workspace").is_dir() else []
    for item in items:
        try:
            name = json.loads((item / ".platform").read_text())["metadata"]["displayName"]
        except (OSError, ValueError, KeyError):
            name = item.name.rsplit(".", 1)[0]
        r = subprocess.run(["dotnet", str(DLL), str(item.relative_to(root)), "--bim", str(out / f"{name}.bim")],
                           cwd=root, capture_output=True, text=True)
        print(r.stdout.strip() or r.stderr.strip())
        failed += r.returncode != 0
    if not items:
        print("no semantic models found")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
