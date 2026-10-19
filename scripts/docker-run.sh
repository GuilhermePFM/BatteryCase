#!/usr/bin/env bash
# Run the model in Docker, on any machine, with no local Python or solver.
#
#   scripts/docker-run.sh                          # full dispatch, all three years
#   scripts/docker-run.sh inputs                   # spec + data quality
#   scripts/docker-run.sh dispatch --start 2018-01-01 --end 2018-01-31
#   scripts/docker-run.sh --shell                  # a shell inside the image
#   DEV=1 scripts/docker-run.sh --shell            # same, with pytest/mypy/ruff
#
# Results are written to ./data/results on the host, as a native run would.
set -euo pipefail

IMAGE=${IMAGE:-battery-case}
REPO_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
RESULTS_DIR=${RESULTS_DIR:-$REPO_ROOT/data/results}

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found: install Docker, or run the model natively with 'uv run battery-case'." >&2
  exit 127
fi

# The dev groups (pytest, mypy, ruff, jupyterlab) are a separate image, so the
# default one stays small.
if [[ ${DEV:-0} == 1 ]]; then
  BUILD_ARGS=(--build-arg "GROUPS=--all-groups")
  TAG="$IMAGE:dev"
else
  BUILD_ARGS=()
  TAG="$IMAGE:latest"
fi

# Rebuild every time: Docker's layer cache makes this a no-op when nothing
# changed, and it means a code edit can never be run as a stale image.
docker build ${PLATFORM:+--platform "$PLATFORM"} "${BUILD_ARGS[@]}" -t "$TAG" "$REPO_ROOT" >&2

mkdir -p "$RESULTS_DIR"

RUN_ARGS=(
  --rm
  --init
  -v "$RESULTS_DIR:/app/data/results"
  ${PLATFORM:+--platform "$PLATFORM"}
)
# A tty when there is one, so --progress console draws its live display.
[[ -t 0 && -t 1 ]] && RUN_ARGS+=(-it)
# Write results as the invoking user, not as root.
[[ $(uname -s) == Linux ]] && RUN_ARGS+=(--user "$(id -u):$(id -g)")

if [[ ${1:-} == --shell ]]; then
  shift
  exec docker run "${RUN_ARGS[@]}" --entrypoint bash "$TAG" "$@"
fi

exec docker run "${RUN_ARGS[@]}" "$TAG" "$@"
