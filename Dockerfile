FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends git ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY check_kernel.py .

# Persist last-seen kernel state here - mount a volume at /data so state
# survives container restarts (otherwise every restart re-triggers a build).
VOLUME ["/data"]

ENV KERNEL_CHECK_MODE=branch \
    KERNEL_GIT=https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git \
    KERNEL_BRANCH=linux-rolling-stable \
    KERNEL_RELEASE_MONIKER=stable \
    STATE_FILE=/data/last_checked.txt \
    GITHUB_WORKFLOW_FILE=merge-and-build-kernel.yml \
    GITHUB_DISPATCH_REF=main \
    CHECK_INTERVAL_SECONDS=86400 \
    RUN_ONCE=false \
    DRY_RUN=false

ENTRYPOINT ["python", "check_kernel.py"]
