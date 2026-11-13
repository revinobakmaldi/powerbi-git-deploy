# One-time setup

About 30 minutes. You need a Fabric capacity (a [Fabric trial](https://learn.microsoft.com/fabric/fundamentals/fabric-trial) works), admin rights in your Fabric tenant, and a GitHub repo you own. Names below are this repo's; change them in `config/workspaces.json` for yours.

Steps 3, 5 and 6 involve credentials. Do them yourself in the portals; never paste a token into a chat, a file or a commit.

## 1. Branches

```bash
git checkout -b dev && git push -u origin dev
```

`main` is production, `dev` is integration. Work happens on `feature/*` branches.

## 2. Two workspaces on the capacity

Create **Kalaraya Dev** and **Kalaraya Prod**, with the workspace type set to your Fabric capacity (or *Fabric Trial*). With the Fabric CLI:

```bash
fab api workspaces -X post -i '{"displayName":"Kalaraya Dev","capacityId":"<capacity id>"}' </dev/null
fab api workspaces -X post -i '{"displayName":"Kalaraya Prod","capacityId":"<capacity id>"}' </dev/null
```

`fab ls .capacities -l </dev/null` lists capacity ids.

## 3. Tenant settings (Fabric admin portal → Tenant settings)

Turn on, for your account or a security group that holds the service principal:

| Setting | Section | Why |
|---|---|---|
| Users can synchronize workspace items with their Git repositories | Git integration | Fabric Git sync |
| Users can sync workspace items with GitHub repositories | Git integration | GitHub as the Git provider |
| Service principals can call Fabric public APIs | Developer settings | The release job calls the Fabric and Power BI APIs |

Microsoft renames these settings from time to time; search the page for "GitHub" and "Service principals".

## 4. A GitHub token for Fabric

GitHub → Settings → Developer settings → Fine-grained tokens → Generate:
- Repository access: **only this repo**
- Permissions: **Contents: Read and write**
- An expiry date you will remember (Fabric stops syncing when it expires)

## 5. Connect both workspaces to Git

In each workspace: **Workspace settings → Git integration → GitHub → Add account**. Paste the token there, with the repo URL. Then:

| Workspace | Branch | Git folder |
|---|---|---|
| Kalaraya Dev | `dev` | `workspace/kalaraya` |
| Kalaraya Prod | `main` | `workspace/kalaraya` |

When Fabric asks which way to sync, take the content **from Git**. Both workspaces sync the same folder from different branches: that is what makes Dev and Prod.

The "Add account" step creates a Fabric connection that stores the token. You reuse it in step 7.

## 6. A service principal, with no secret

Microsoft Entra admin center → App registrations → New registration (e.g. `powerbi-git-deploy-release`). No redirect URI. Then **Certificates & secrets → Federated credentials → Add**, scenario *GitHub Actions deploying Azure resources*, three times.

The form asks for the organization **and its ID**, the repository **and its ID**. GitHub now signs runs with these numbers in the subject (`repo:<owner>@<owner id>/<repo>@<repo id>:...`), so a renamed or re-created repo can't reuse your trust. Get the numbers, and check which format your repo uses:

```bash
gh api users/<owner> -q .id
gh api repos/<owner>/<repo> -q .id
gh api repos/<owner>/<repo>/actions/oidc/customization/sub   # "use_immutable_subject": true
```

If it says `false` (repos created before mid-2026), either opt the repo in to the immutable format ([Microsoft Learn](https://learn.microsoft.com/entra/workload-id/workload-identities-github-immutable-subjects)), or click **Edit** next to *Subject identifier* and type the older form, e.g. `repo:<owner>/<repo>:environment:development`.

The three credentials:

| Entity type | Value | Used by |
|---|---|---|
| Environment | `development` | release job on `dev` |
| Environment | `production` | release job on `main` |
| Branch | `main` | daily reconcile job |

GitHub signs each run with a short-lived token that Entra trusts. Nothing secret is stored in GitHub.

If the tenant setting in step 3 is limited to a security group, add the app to that group.

## 7. Give the service principal access

- Both workspaces → **Manage access** → add the app as **Admin** (needed to update from Git).
- Fabric → **Settings → Manage connections and gateways** → the GitHub connection from step 5 → **Manage users** → add the app. Copy the connection's **ID**.

A service principal can't use "Automatic" Git credentials, so the release job points it at this shared connection.

## 8. GitHub repo settings

**Settings → Secrets and variables → Actions → Variables** (variables, not secrets: none of these is secret):

| Variable | Value |
|---|---|
| `AZURE_CLIENT_ID` | the app's Application (client) ID |
| `AZURE_TENANT_ID` | your Directory (tenant) ID |
| `FABRIC_GIT_CONNECTION_ID` | the connection ID from step 7 |
| `RELEASE_ENABLED` | `true` |

**Settings → Environments**: create `development` (no reviewers) and `production` with **Required reviewers** = the model owner. The release to Prod waits there. Under *Deployment branches → Selected branches*, limit `development` to `dev` and `production` to `main`, so a run from another branch can't get the credential.

**Settings → Rules → Rulesets** (or Branches → branch protection) for `dev` and `main`:
- Require a pull request, with 1 approval and review from Code Owners on `main`
- Require status checks: **Files and model** and **Best Practice Analyzer**
- Block force pushes and deletion

Working alone? GitHub doesn't let you approve your own pull request. Add the **Repository admin** role as a bypass actor, *for pull requests only*: you can then merge your own PR after reading it, and nobody can push straight to `dev` or `main`. This repo is set up that way.

## 9. First release

Actions → **Release** → Run workflow on `dev`, then on `main`. Each run updates the workspace from Git, sets the data source to anonymous, applies the refresh schedule, refreshes and compares the total with the data files.

## Free licence instead

No capacity, no Git sync: keep the PR checks, and after each merge to `main` run

```bash
python3 scripts/deploy_my_workspace.py </dev/null
```

It imports the model into your **My workspace** as you (`fab auth login`), refreshes it and runs the same smoke test.
