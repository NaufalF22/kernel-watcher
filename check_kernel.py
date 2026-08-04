#!/usr/bin/env python3
"""
Polls kernel.org for new kernel commits/releases and triggers a GitHub
Actions workflow_dispatch run when something new shows up.

Two check modes:
  - "branch"  (default): git ls-remote against a branch on git.kernel.org,
              compares the latest commit SHA. Matches what the "Merge and
              Build Kernel" workflow's own check-update job does, but runs
              outside GitHub's scheduler.
  - "release": reads https://www.kernel.org/releases.json and watches a
              given moniker (e.g. "stable", "mainline", "longterm").

State (the last SHA/version seen) is persisted to STATE_FILE so re-running
the container doesn't retrigger a build for a kernel it already saw.
"""

import json
import os
import subprocess
import sys
import time
import urllib.request

KERNEL_CHECK_MODE = os.environ.get("KERNEL_CHECK_MODE", "branch")  # branch | release
KERNEL_GIT = os.environ.get("KERNEL_GIT", "https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git")
KERNEL_BRANCH = os.environ.get("KERNEL_BRANCH", "linux-rolling-stable")
KERNEL_RELEASE_MONIKER = os.environ.get("KERNEL_RELEASE_MONIKER", "stable")

STATE_FILE = os.environ.get("STATE_FILE", "/data/last_checked.txt")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY")  # "owner/repo"
GITHUB_WORKFLOW_FILES = [
    f.strip() for f in os.environ.get("GITHUB_WORKFLOW_FILE", "merge-and-build-kernel.yml").split(",") if f.strip()
]
GITHUB_DISPATCH_REF = os.environ.get("GITHUB_DISPATCH_REF", "main")

CHECK_INTERVAL_SECONDS = int(os.environ.get("CHECK_INTERVAL_SECONDS", "86400"))  # 24h
RUN_ONCE = os.environ.get("RUN_ONCE", "false").lower() == "true"
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"


def log(msg: str) -> None:
    print(f"[kernel-watcher] {msg}", flush=True)


def get_latest_branch_sha() -> str:
    result = subprocess.run(
        ["git", "ls-remote", KERNEL_GIT, f"refs/heads/{KERNEL_BRANCH}"],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    line = result.stdout.strip()
    if not line:
        raise RuntimeError(f"Branch '{KERNEL_BRANCH}' not found on {KERNEL_GIT}")
    return line.split()[0]


def get_latest_release_version() -> str:
    with urllib.request.urlopen("https://www.kernel.org/releases.json", timeout=30) as resp:
        data = json.load(resp)
    for release in data.get("releases", []):
        if release.get("moniker") == KERNEL_RELEASE_MONIKER:
            return release["version"]
    raise RuntimeError(f"No release found with moniker '{KERNEL_RELEASE_MONIKER}'")


def get_latest() -> str:
    if KERNEL_CHECK_MODE == "branch":
        return get_latest_branch_sha()
    if KERNEL_CHECK_MODE == "release":
        return get_latest_release_version()
    raise ValueError(f"Unknown KERNEL_CHECK_MODE: {KERNEL_CHECK_MODE}")


def load_last_seen() -> str:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return f.read().strip()
    return ""


def save_last_seen(value: str) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        f.write(value + "\n")


def trigger_workflow(latest: str) -> None:
    if not GITHUB_TOKEN or not GITHUB_REPOSITORY:
        raise RuntimeError(
            "GITHUB_TOKEN and GITHUB_REPOSITORY must be set to trigger the workflow"
        )

    url = (
        f"https://api.github.com/repos/{GITHUB_REPOSITORY}"
        f"/actions/workflows/{GITHUB_WORKFLOW_FILE}/dispatches"
    )
    payload = {
        "ref": GITHUB_DISPATCH_REF,
        "inputs": {
            "linux_branch": KERNEL_BRANCH,
        },
    }

    if DRY_RUN:
        log(f"DRY_RUN: would POST to {url} with {payload}")
        return

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            log(f"Workflow dispatch accepted (HTTP {resp.status}) for {latest}")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"GitHub API returned {e.code}: {body}") from e


def run_once() -> None:
    log(f"Checking kernel.org (mode={KERNEL_CHECK_MODE}, branch={KERNEL_BRANCH})...")
    latest = get_latest()
    last_seen = load_last_seen()

    log(f"Latest:    {latest}")
    log(f"Last seen: {last_seen or '<none recorded>'}")

    if latest == last_seen:
        log("No change - nothing to do.")
        return

    log("New kernel detected - triggering workflow_dispatch.")
    trigger_workflow(latest)
    save_last_seen(latest)


def main() -> None:
    if RUN_ONCE:
        run_once()
        return

    log(f"Starting watch loop, checking every {CHECK_INTERVAL_SECONDS}s.")
    while True:
        try:
            run_once()
        except Exception as e:  # noqa: BLE001 - keep the loop alive on transient errors
            log(f"ERROR: {e}")
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        log(f"FATAL: {e}")
        sys.exit(1)
