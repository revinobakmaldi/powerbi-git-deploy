"""Repo checks that need nothing but the files: structure, JSON, item names, config coverage.

Run:  python3 scripts/check_repo.py [structure|json|names|config|all]

Each problem prints as a GitHub annotation (`::error file=...::...`), so it shows on the pull request.
Exit code 1 when any check finds a problem.

- structure: every item folder under workspace/<ws>/ is `<Name>.<Type>` with the files Fabric needs,
  and no Desktop-only files (.pbix, .pbi/ cache) are committed.
- json:      every JSON file in workspace/ and config/ parses (one bad file breaks the sync).
- names:     the folder name matches `.platform` displayName and type, and every logicalId is a
  GUID used once. A folder renamed without its `.platform` syncs under the old name, with no error.
- config:    every workspace folder is listed in config/workspaces.json, and every semantic model
  has a data source entry.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WS = ROOT / "workspace"
TYPES = {
    "SemanticModel": [".platform", "definition.pbism", "definition/database.tmdl", "definition/model.tmdl"],
    "Report": [".platform", "definition.pbir"],
}
GUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
problems = []


def error(path, msg):
    rel = Path(path).resolve().relative_to(ROOT) if Path(path).is_absolute() else path
    problems.append((str(rel), msg))


def items():
    """Yield (workspace folder, item folder) for every Fabric item folder."""
    for ws in sorted(p for p in WS.iterdir() if p.is_dir()):
        for item in sorted(ws.rglob("*")):
            if item.is_dir() and "." in item.name and item.name.rsplit(".", 1)[1] in TYPES:
                yield ws, item


def check_structure():
    if not WS.is_dir():
        error("workspace", "workspace/ folder is missing")
        return
    for ws in sorted(p for p in WS.iterdir() if p.is_dir()):
        found = False
        for child in sorted(ws.iterdir()):
            if child.name.startswith("."):
                continue
            if not child.is_dir():
                error(child, "loose file in a workspace folder; only item folders belong here")
                continue
            kind = child.name.rsplit(".", 1)[1] if "." in child.name else ""
            if kind not in TYPES:
                error(child, f"'{child.name}' is not an item folder (<Name>.SemanticModel or <Name>.Report)")
                continue
            found = True
            for need in TYPES[kind]:
                if not (child / need).exists():
                    error(child, f"{kind} folder is missing {need}")
        if not found:
            error(ws, "workspace folder has no items")
    for bad in list(ROOT.glob("workspace/**/*.pbix")) + list(ROOT.glob("workspace/**/.pbi")):
        error(bad, "Desktop file or cache committed; it must stay out of Git (.gitignore)")


def check_json():
    files = [p for p in list(WS.rglob("*")) + list((ROOT / "config").rglob("*"))
             if p.is_file() and (p.suffix in (".json", ".pbism", ".pbir") or p.name == ".platform")]
    for p in sorted(files):
        try:
            json.loads(p.read_text(encoding="utf-8"))
        except ValueError as e:
            error(p, f"invalid JSON: {e}")


def check_names():
    seen = {}
    for _, item in items():
        name, kind = item.name.rsplit(".", 1)
        plat = item / ".platform"
        try:
            meta = json.loads(plat.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue  # structure/json checks report it
        md, cfg = meta.get("metadata", {}), meta.get("config", {})
        if md.get("displayName") != name:
            error(plat, f"folder is '{name}' but .platform displayName is '{md.get('displayName')}'. "
                        "Fabric names the item from .platform, so it would sync under the wrong name.")
        if md.get("type") != kind:
            error(plat, f"folder type is {kind} but .platform type is {md.get('type')}")
        lid = str(cfg.get("logicalId", ""))
        if not GUID.match(lid):
            error(plat, f"logicalId '{lid}' is not a GUID")
        elif lid in seen:
            error(plat, f"logicalId {lid} is also used by {seen[lid]}. Copied items need a new logicalId, "
                        "or the sync fails.")
        else:
            seen[lid] = str(item.relative_to(ROOT))


def check_config():
    try:
        wcfg = json.loads((ROOT / "config/workspaces.json").read_text())["workspaces"]
        dcfg = json.loads((ROOT / "config/datasources.json").read_text())["models"]
    except (OSError, ValueError, KeyError) as e:
        error("config", f"config files unreadable: {e}")
        return
    folders = {w["folder"] for w in wcfg}
    for w in wcfg:
        if not (ROOT / w["folder"]).is_dir():
            error("config/workspaces.json", f"workspace '{w['name']}' points at missing folder {w['folder']}")
        if w.get("branch") not in ("dev", "main"):
            error("config/workspaces.json", f"workspace '{w['name']}' has branch '{w.get('branch')}'; use dev or main")
    for ws in sorted(p for p in WS.iterdir() if p.is_dir()):
        if str(ws.relative_to(ROOT)) not in folders:
            error(ws, "folder is not listed in config/workspaces.json, so no workspace syncs it")
    for _, item in items():
        kind = item.name.rsplit(".", 1)[1]
        try:
            name = json.loads((item / ".platform").read_text(encoding="utf-8"))["metadata"]["displayName"]
        except (OSError, ValueError, KeyError):
            continue  # the names check reports it
        if kind == "SemanticModel" and name not in dcfg:
            error(item, f"no entry for model '{name}' in config/datasources.json")


CHECKS = {"structure": check_structure, "json": check_json, "names": check_names, "config": check_config}


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for name in (CHECKS if which == "all" else [which]):
        before = len(problems)
        CHECKS[name]()
        n = len(problems) - before
        print(f"{name}: {'ok' if n == 0 else f'{n} problem(s)'}")
    for path, msg in problems:
        print(f"::error file={path}::{msg}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
