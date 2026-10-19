# The model, pinned end to end: Python 3.12 as in .python-version, every
# dependency resolved from uv.lock, and the two input spreadsheets baked in, so
# `docker run` reproduces a run on any machine with no local toolchain.
FROM python:3.12-slim

# uv itself is pinned; it is the only tool the image needs beyond Python.
COPY --from=ghcr.io/astral-sh/uv:0.9.2 /uv /uvx /usr/local/bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app

# `--no-dev` keeps the image to the runtime solver stack; build it with
# `--build-arg GROUPS=--all-groups` to get pytest, mypy, ruff and jupyterlab.
ARG GROUPS=--no-dev

# Dependencies first, in their own layer: they only change when the lock does.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project $GROUPS

# Then the project. src/battery_case/data_io/paths.py resolves the inputs
# relative to the package, so the tree has to keep its shape: data/raw next to
# src/, which is why the spreadsheets are copied rather than mounted.
COPY src/ src/
COPY data/raw/ data/raw/
COPY scripts/ scripts/
COPY tests/ tests/
COPY docs/ docs/
COPY Makefile ./
RUN uv sync --frozen $GROUPS

# Results land here; mount a host directory over it to keep them.
RUN mkdir -p data/results
VOLUME ["/app/data/results"]

ENTRYPOINT ["battery-case"]
CMD ["dispatch"]
