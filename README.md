# Power BI model under Git, with a deployment setup you can copy

A Power BI semantic model that lives in GitHub. Every change goes through a pull request with automatic checks, and Fabric's own Git sync deploys it to a Dev and a Prod workspace.

> Most Power BI teams still publish from someone's laptop. Nobody can say what changed, who changed it, or how to undo it. Here the repo is the truth: a reviewer sees each change in plain words, a broken model can't merge, and Prod changes only after someone approves.

Build 2 of a series of working builds on synthetic data. [Build 1](https://github.com/revinobakmaldi/weekly-sales-commentary-agent) is an AI agent that writes the weekly sales commentary from this same model.

## How it works

```
feature/*  ──PR + checks──▶  dev   ──Fabric Git sync──▶  Kalaraya Dev
dev        ──PR + checks──▶  main  ──Fabric Git sync──▶  Kalaraya Prod   (waits for approval)

After each merge, GitHub Actions (service principal, no stored secret):
  update the workspace from Git ─▶ set data source + refresh schedule from config/ ─▶ refresh ─▶ smoke test
```

| When | Workflow | What it does |
|---|---|---|
| Pull request into `dev` or `main` | [PR checks](.github/workflows/pr-checks.yml) | The checks below, plus a comment listing what changed in the model. Files only: no Power BI licence, no secrets. |
| Merge into `dev` or `main` | [Release](.github/workflows/release.yml) | Updates the branch's workspace from Git, applies `config/`, refreshes, and compares total sales with the data files. `main` waits for the `production` approval. |
| Daily | [Reconcile](.github/workflows/reconcile.yml) | Puts refresh schedules back to `config/refresh-schedule.json` if the service or a person changed them. Has a dry run. |

## The checks

| Check | What it stops | Tool |
|---|---|---|
| Folder structure | An item folder missing the files Fabric needs; a `.pbix` committed | `scripts/check_repo.py structure` |
| JSON files parse | One broken JSON file that breaks the sync | `scripts/check_repo.py json` |
| Item names and logicalIds | A folder renamed without its `.platform`: Fabric names the item from `.platform`, so it syncs under the old name, with no error. A copied item that kept its logicalId. | `scripts/check_repo.py names` |
| Config coverage | A workspace folder no workspace syncs; a model with no data source settings | `scripts/check_repo.py config` |
| Read TMDL | Any TMDL syntax error, or a relationship to a column that doesn't exist | [`tools/tmdl-check`](tools/tmdl-check/Program.cs): Microsoft's own TMDL serializer (TOM) |
| Team rules | A measure with no description, format string or display folder; a measure pointing at a renamed column; the model reading another branch's data | [`scripts/team_rules.py`](scripts/team_rules.py) |
| Best Practice Analyzer | Microsoft's 71 [best practice rules](https://github.com/microsoft/Analysis-Services/tree/master/BestPracticeRules); severity 3 fails | Tabular Editor 2 CLI on Windows, reading the model that `tmdl-check` writes |

The analyzer and the TMDL reader overlap on purpose. A measure that points at a renamed column passes both TMDL and the analyzer, and only breaks when someone opens a visual. The team rule catches it.

## Results

Every check is tested by planting one bug at a time. Each must fail its own check and nothing else; a check that fails too often is as wrong as one that never fails.

| Planted change | Fails | Local eval | On GitHub |
|---|---|---|---|
| None (clean copy) | nothing | ✅ | ✅ [#3](https://github.com/revinobakmaldi/powerbi-git-deploy/pull/3) |
| A typo in a TMDL property | Read TMDL | ✅ | ✅ [#4](https://github.com/revinobakmaldi/powerbi-git-deploy/pull/4) |
| A relationship to a column that doesn't exist | Read TMDL | ✅ | ✅ [#5](https://github.com/revinobakmaldi/powerbi-git-deploy/pull/5) |
| A measure without a description | Team rules | ✅ | ✅ [#6](https://github.com/revinobakmaldi/powerbi-git-deploy/pull/6) |
| A measure pointing at a renamed column | Team rules | ✅ | ✅ [#7](https://github.com/revinobakmaldi/powerbi-git-deploy/pull/7) |
| The model reading another branch's data | Team rules | ✅ | ✅ [#8](https://github.com/revinobakmaldi/powerbi-git-deploy/pull/8) |
| A folder renamed without its `.platform` | Item names | ✅ | ✅ [#9](https://github.com/revinobakmaldi/powerbi-git-deploy/pull/9) |
| A copied model that kept its logicalId | Item names, config | ✅ | ✅ [#10](https://github.com/revinobakmaldi/powerbi-git-deploy/pull/10) |
| A broken config file | JSON | ✅ | ✅ [#11](https://github.com/revinobakmaldi/powerbi-git-deploy/pull/11) |
| A `.pbix` committed | Structure | ✅ | ✅ [#12](https://github.com/revinobakmaldi/powerbi-git-deploy/pull/12) |
| A visible numeric column that sums by default | Best Practice Analyzer only | ✅ (not run locally) | ✅ [#13](https://github.com/revinobakmaldi/powerbi-git-deploy/pull/13) |
| A correct DAX change | nothing; the PR comment shows the before and after | ✅ | ✅ [#14](https://github.com/revinobakmaldi/powerbi-git-deploy/pull/14) |

Run them: `python3 eval/run_eval.py` (local, about 2.5 minutes) and `python3 eval/github_eval.py` (real pull requests, about 35 minutes). Results: [eval/results/](eval/results/).

## Use it for your team

1. Copy the repo layout: one folder per workspace under `workspace/`, one entry per workspace in [`config/workspaces.json`](config/workspaces.json).
2. Follow [docs/setup.md](docs/setup.md): two workspaces, Git connections, a service principal with a federated credential, repo variables and branch rules. About 30 minutes.
3. Change [`config/datasources.json`](config/datasources.json) and [`config/refresh-schedule.json`](config/refresh-schedule.json) for your models, and the team rules for your standards.

Run the checks locally before you push:

```bash
python3 scripts/check_repo.py
python3 scripts/build_models.py && python3 scripts/team_rules.py build/head/*.bim
```

Requirements: Python 3.9+, .NET 8 SDK (or newer), and `pip install pyarrow` for the release and smoke test.

## What you need

| Part | Free Power BI licence | With Fabric capacity (a trial works) |
|---|---|---|
| PR checks | ✅ | ✅ |
| Fabric Git sync to Dev and Prod workspaces | ❌ My workspace can't connect to Git | ✅ |
| Unattended release from GitHub | ❌ A service principal can't reach My workspace | ✅ |
| Deploy | `python3 scripts/deploy_my_workspace.py` after each merge, signed in as you | Release workflow |

Sources: [Git integration prerequisites](https://learn.microsoft.com/fabric/cicd/git-integration/git-get-started), [Git integration limitations](https://learn.microsoft.com/fabric/cicd/git-integration/git-integration-process#considerations-and-limitations), [free licence features](https://learn.microsoft.com/power-bi/fundamentals/end-user-features), [service principals and My workspace](https://learn.microsoft.com/fabric/data-science/semantic-link-service-principal-support).

This repo runs on a Fabric trial that ends in early January 2027. See [docs/after-the-trial.md](docs/after-the-trial.md) for what keeps running after that.

## Why Git sync and not a deployment pipeline

Fabric deployment pipelines also move content from Dev to Prod. Here, Git is already the source of truth, and two branches give two stages with nothing extra to run. A pipeline would be a second way to change Prod. Pick a pipeline instead when your team edits in the service and wants a compare-and-deploy screen, or needs deployment rules per stage.

## What is in the repo

| Folder | What it is |
|---|---|
| `workspace/kalaraya/` | The Kalaraya Sales model as PBIP/TMDL. Both workspaces sync this folder, from different branches. |
| `config/` | Workspaces and their branches, data source settings, refresh schedules, analyzer rules |
| `scripts/` | The checks, the release, the reconcile job and the free-licence deploy |
| `tools/tmdl-check/` | A small .NET tool around Microsoft's TMDL serializer |
| `data/` | Synthetic sales data for a fictional coffee-shop chain in Indonesia ([data/README.md](data/README.md)) |
| `eval/` | The evals and their results |
| `docs/` | Setup, life after the trial, screenshots |

## The data is synthetic

Kalaraya Coffee, its stores and its products are made up. Any match with a real business is a coincidence.

## Not covered

- Reports (PBIR). The repo holds a model only; the same layout takes a `<Name>.Report` folder next to it.
- Row-level security, gateways and on-premises sources.
- Azure DevOps. The checks are plain scripts and run on any CI.
