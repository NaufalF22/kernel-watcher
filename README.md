# kernel-watcher

A small container that polls kernel.org and triggers the
`merge-and-build-kernel.yml` GitHub Actions workflow (via `workflow_dispatch`)
whenever it sees a new kernel — without depending on GitHub's own `schedule`
trigger.

## Why this exists alongside the workflow's own `schedule` trigger

The build workflow already checks kernel.org on a cron and skips the build if
nothing changed. That's enough for most cases. This container is only worth
running if you want to avoid GitHub's caveat that **scheduled workflows are
automatically disabled after 60 days with no repository activity** — if this
repo goes quiet (no commits, no manual runs), the in-repo cron silently stops
firing until someone notices and re-enables it. A watcher running on your own
infrastructure (server, NAS, homelab) doesn't have that failure mode, since
it calls the GitHub API directly instead of relying on GitHub's scheduler.

If you're fine with the built-in `schedule` trigger, you don't need this.

## Setup

```bash
cd kernel-watcher
cp .env.example .env
# edit .env: set GITHUB_TOKEN and GITHUB_REPOSITORY

docker compose up -d --build
```

`GITHUB_TOKEN` needs permission to trigger workflow runs on the target repo:
- Fine-grained PAT: **Actions: Read and write** on that repo
- Classic PAT: **repo** scope

## What it checks

By default it runs `git ls-remote` against `linux-rolling-stable` on
`git.kernel.org` every 24 hours (`KERNEL_CHECK_MODE=branch`) — the same check
the workflow's own `check-update` job does. State (the last commit SHA it
saw) is kept in a Docker volume at `/data/last_checked.txt` so restarting the
container doesn't retrigger a build for a kernel it's already handled.

To watch official stable kernel.org releases instead of a branch's latest
commit, set:

```bash
KERNEL_CHECK_MODE=release
KERNEL_RELEASE_MONIKER=stable   # or "mainline", "longterm"
```

This reads `https://www.kernel.org/releases.json` instead.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `GITHUB_TOKEN` | — | Required. PAT with Actions write access to the target repo |
| `GITHUB_REPOSITORY` | — | Required. `owner/repo` hosting the workflow |
| `GITHUB_WORKFLOW_FILE` | `merge-and-build-kernel.yml` | Workflow filename to dispatch |
| `GITHUB_DISPATCH_REF` | `main` | Branch the workflow file lives on |
| `KERNEL_CHECK_MODE` | `branch` | `branch` or `release` |
| `KERNEL_GIT` | kernel.org stable git URL | Used in `branch` mode |
| `KERNEL_BRANCH` | `linux-rolling-stable` | Used in `branch` mode; also passed as the `linux_branch` workflow input |
| `KERNEL_RELEASE_MONIKER` | `stable` | Used in `release` mode |
| `STATE_FILE` | `/data/last_checked.txt` | Where the last-seen value is persisted |
| `CHECK_INTERVAL_SECONDS` | `86400` (24h) | Sleep between checks in the watch loop |
| `RUN_ONCE` | `false` | If `true`, checks once and exits — use this instead of the loop if you're driving it from an external cron/systemd timer/k8s CronJob rather than `restart: unless-stopped` |
| `DRY_RUN` | `false` | If `true`, logs what it would trigger instead of calling the GitHub API — useful for testing |

## Running a one-shot check (e.g. from cron/systemd instead of a long-lived container)

```bash
docker run --rm \
  -e GITHUB_TOKEN=xxx \
  -e GITHUB_REPOSITORY=yourname/wsl-kernel \
  -e RUN_ONCE=true \
  -v kernel-watcher-state:/data \
  kernel-watcher
```

Point your host's cron/systemd timer at this instead of `docker compose up -d`
if you'd rather the scheduling live outside the container.

## Testing without triggering a real build

```bash
docker run --rm \
  -e GITHUB_TOKEN=xxx \
  -e GITHUB_REPOSITORY=yourname/wsl-kernel \
  -e RUN_ONCE=true \
  -e DRY_RUN=true \
  -v kernel-watcher-state:/data \
  kernel-watcher
```
