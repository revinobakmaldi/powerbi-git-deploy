# Proof from the Fabric trial

Taken on 13 November 2026, the day the release path first ran end to end. The trial ends in early January 2027; these stay as the record.

| # | Screenshot | What it shows |
|---|---|---|
| 1 | [01-dev-workspace-synced-to-dev.jpg](01-dev-workspace-synced-to-dev.jpg) | Kalaraya Dev, connected to the `dev` branch, model synced. No next refresh: Dev's schedule is off in `config/refresh-schedule.json`. |
| 2 | [02-prod-release-waits-for-approval.jpg](02-prod-release-waits-for-approval.jpg) | The release to Kalaraya Prod stops at the `production` environment until the owner approves. |
| 3 | [03-prod-release-approved-refreshed-smoke-passed.jpg](03-prod-release-approved-refreshed-smoke-passed.jpg) | After approval: updated from Git, refresh completed, smoke test passed, schedule set from config. |
| 4 | [04-prod-workspace-synced-to-main.jpg](04-prod-workspace-synced-to-main.jpg) | Kalaraya Prod, connected to `main`, model synced, next refresh on the configured weekday. |

The runs behind them:

| Run | Result |
|---|---|
| [First release on `dev`](https://github.com/revinobakmaldi/powerbi-git-deploy/actions/runs/43338296020) | Failed after the Git update: a script bug. Fixed in [#15](https://github.com/revinobakmaldi/powerbi-git-deploy/pull/15), which also added the lint check that catches it |
| [Release on `dev`](https://github.com/revinobakmaldi/powerbi-git-deploy/actions/runs/43338933484) | Kalaraya Dev updated from Git by the service principal, refresh completed, smoke test passed |
| [Release on `main`](https://github.com/revinobakmaldi/powerbi-git-deploy/actions/runs/43339438657) | Same for Kalaraya Prod, after approval |
| [Reconcile eval](../../eval/results/) | Drift planted by a person was reported by a dry run, fixed by the real run, and matched config afterwards |
