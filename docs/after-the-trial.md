# After the Fabric trial

This repo was built on a 60-day Fabric trial that ends in early January 2027.

## What Microsoft says happens

When a trial ends, workspaces on the trial capacity move back to Power BI Pro, and capacity features stop ([Microsoft Learn](https://learn.microsoft.com/fabric/fundamentals/fabric-trial#when-your-fabric-trial-ends)). Git integration needs a capacity, so the workspaces stop syncing ([Microsoft Learn](https://learn.microsoft.com/fabric/cicd/git-integration/license-change)).

## What keeps running here

| Part | After the trial |
|---|---|
| PR checks | Unchanged. They read files only. |
| Release and reconcile jobs | Switched off with the repo variable `RELEASE_ENABLED=false`, so they skip instead of failing |
| Deploy | `python3 scripts/deploy_my_workspace.py` to My workspace, on a free licence |
| Screenshots and run logs from the trial | In `docs/proof/` |

## With your own capacity

Nothing changes: assign the two workspaces to your capacity and keep `RELEASE_ENABLED=true`.
