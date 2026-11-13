# Reconcile eval, 2026-11-13, Kalaraya Prod

Result: **PASS**, 4 of 4 steps as expected.

| Step | What happened | Run | OK |
|---|---|---|---|
| plant drift (as a person) | times ['07:30'], owner changed from the service principal to you | - | ✅ |
| dry run reports | row 'would fix: times', times still ['07:30'] | [run](https://github.com/revinobakmaldi/powerbi-git-deploy/actions/runs/43340757727) | ✅ |
| real run fixes | row 'fixed: times', times ['06:00'], owner back to the service principal: True | [run](https://github.com/revinobakmaldi/powerbi-git-deploy/actions/runs/43340827099) | ✅ |
| dry run after fix | Kalaraya Dev: matches config; Kalaraya Prod: matches config | [run](https://github.com/revinobakmaldi/powerbi-git-deploy/actions/runs/43340939107) | ✅ |
