# uv Migration Plan

Migrate the three Docker services from `pip + requirements.txt` to `uv + pyproject.toml + uv.lock`.
Single source of truth, reproducible builds, parity between local dev and Docker.

---

## Current State (verified against repo)

- ✅ `pyproject.toml` exists at repo root (has `[dependency-groups]` for dev tooling already)
- ✅ `uv.lock` exists at repo root
- ✅ Local dev can use `uv sync`
- ❌ Each service has its own `Dockerfile` + `requirements.txt` with `pip install -r requirements.txt`
- ❌ Root `requirements.txt` (all-services combined) used by the root `Dockerfile`
- ❌ Docker build contexts are `./src/<service>` — they cannot see root `pyproject.toml`/`uv.lock`
- ❌ README still references `pip install -r requirements.txt` for local dev

**Goal:** one lockfile, one resolver, identical environments everywhere.

---

## Actual Dependencies (audited from imports)

> These correct the initial plan estimate. Streamer has **no numpy** — price generation uses stdlib `random`.
> `httpx` belongs to the **dashboard** group (it's used for HTTP fallback in the dashboard).

| Group | Packages |
|---|---|
| **shared** (root `dependencies`) | `websockets>=12.0` |
| **streamer** | *(websockets is sufficient — no extra deps)* |
| **backend** | `fastapi>=0.111.0`, `uvicorn[standard]>=0.29.0` |
| **dashboard** | `streamlit>=1.37.0`, `streamlit-echarts>=0.4.0`, `pandas>=2.0.0`, `httpx>=0.27.0` |
| **dev** | existing groups (`test`, `lint`, `type_check`, `nox`, `docs`, `licenses`) — keep as-is |

---

## Target State

```
repo-root/
├── pyproject.toml          # one source of truth — shared deps + per-service groups
├── uv.lock                 # one lockfile, all services
├── Dockerfile              # root image (reference build) — updated to use uv
├── src/
│   ├── streamer/
│   │   └── Dockerfile      # uv sync --group streamer
│   ├── backend/
│   │   └── Dockerfile      # uv sync --group backend
│   └── dashboard/
│       └── Dockerfile      # uv sync --group dashboard
└── README.md               # uv-first quickstart
```

No `requirements.txt` files anywhere.

---

## Step-by-Step Plan

### Step 1 — Update `pyproject.toml`

Add service groups to the existing `[dependency-groups]` block. Move `websockets` into root
`dependencies` since all three services use it. Keep all existing dev groups intact.

```toml
[project]
name = "test-finalto"
version = "1.0.0"
description = "Risk Management Dashboard MVP for Finalto"
requires-python = ">=3.10"
dependencies = [
    "websockets>=12.0",       # used by all three services
]

[dependency-groups]
streamer = []                 # websockets comes from root dependencies
backend = [
    "fastapi>=0.111.0",
    "uvicorn[standard]>=0.29.0",
]
dashboard = [
    "streamlit>=1.37.0",
    "streamlit-echarts>=0.4.0",
    "pandas>=2.0.0",
    "httpx>=0.27.0",
]
# existing dev groups below — keep unchanged
nox = ["nox-uv"]
test = ["pytest", "pytest-cov", "pytest-randomly"]
type_check = ["mypy"]
lint = ["ruff"]
docs = ["mkdocs-material", "mkdocs-htmlproofer-plugin", "mkdocstrings[python]", "mkdocs-api-autonav"]
licenses = ["pip-licenses-cli"]
```

> **Note on empty `streamer` group:** keeping it explicit makes the pattern consistent and
> makes it easy to add streamer-only deps later. If preferred, omit it entirely.

### Step 2 — Regenerate the lockfile

```bash
uv lock
```

Commit the updated `uv.lock`.

### Step 3 — Update `docker-compose.yml`

Build contexts must move to repo root so each Dockerfile can `COPY pyproject.toml uv.lock`.

```yaml
services:
  streamer:
    build:
      context: .
      dockerfile: src/streamer/Dockerfile
    # ... rest unchanged

  backend:
    build:
      context: .
      dockerfile: src/backend/Dockerfile
    # ...

  dashboard:
    build:
      context: .
      dockerfile: src/dashboard/Dockerfile
    # ...
```

### Step 4 — Migrate each service Dockerfile

**Key differences from current Dockerfiles:**
- Pull `uv` binary from the official image instead of using pip
- Copy `pyproject.toml` + `uv.lock` first for layer caching
- Run `uv sync --frozen --group <service>` instead of `pip install -r requirements.txt`
- Source files are now copied from the repo root path `src/<service>/`, not `.`
- CMD uses `uv run` to pick up the synced `.venv` automatically

#### `src/streamer/Dockerfile`

```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --group streamer

COPY src/streamer/ ./src/streamer/

EXPOSE 8001
CMD ["uv", "run", "python", "src/streamer/main.py"]
```

#### `src/backend/Dockerfile`

```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --group backend

COPY src/backend/ ./src/backend/

EXPOSE 8000
CMD ["uv", "run", "python", "src/backend/main.py"]
```

> **Note:** the current backend Dockerfile does `COPY . .` which puts all backend files at
> `/app/` and runs `python main.py` from there. The new Dockerfile copies to `src/backend/`
> and runs `python src/backend/main.py`. Verify that the backend's internal imports
> (`from metrics import ...`, `from state import ...`, `from streamer_client import ...`)
> still resolve — they use bare module names, so the working directory or `PYTHONPATH` must
> include `src/backend/`. If not, either set `ENV PYTHONPATH=/app/src/backend` or keep the
> flat copy layout (copy `src/backend/*` to `/app/` directly).

#### `src/dashboard/Dockerfile`

```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --group dashboard

COPY src/dashboard/ ./src/dashboard/

EXPOSE 8501
CMD ["uv", "run", "streamlit", "run", "src/dashboard/app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
```

### Step 5 — Update root `Dockerfile`

The root Dockerfile is a reference/CI image (not used by docker compose). Update it to use uv
and install all service deps:

```dockerfile
# Root Dockerfile — reference/CI single-image build, not used by docker compose.
# Build:  docker build -t finalto-risk .
# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project \
    --group streamer --group backend --group dashboard

COPY src/ ./src/
```

### Step 6 — Delete old `requirements.txt` files

```bash
git rm requirements.txt
git rm src/streamer/requirements.txt
git rm src/backend/requirements.txt
git rm src/dashboard/requirements.txt
```

### Step 7 — Update README

Replace the pip-based local dev section with:

```markdown
**Local (no Docker):**
```bash
uv sync                                         # install all groups
uv run python src/streamer/main.py              # terminal 1
uv run python src/backend/main.py               # terminal 2
uv run streamlit run src/dashboard/app.py       # terminal 3
```

To install only one service's deps:
```bash
uv sync --only-group backend
```
```

### Step 8 — Update `AGENTS.md` (if it exists)

Add under "Design Rules":

```markdown
**Dependencies:** managed via `uv` with `pyproject.toml` + `uv.lock` at repo root.
Per-service deps live in `[dependency-groups]`. Never add a `requirements.txt`.
Add deps with `uv add <pkg> --group <service>` and commit the updated lockfile.
```

---

## Watch Out For: Backend Import Paths

The current backend Dockerfile does `COPY . .` (all backend files land at `/app/`) and runs
`CMD ["python", "main.py"]` from `/app/`. This means bare imports like `from metrics import ...`
work because `/app/` is on `sys.path`.

With the new layout (`COPY src/backend/ ./src/backend/`), the entry point becomes
`python src/backend/main.py` and bare imports will break unless `/app/src/backend` is on
`sys.path`. Fix with either:

**Option A** — set `PYTHONPATH` in the Dockerfile:
```dockerfile
ENV PYTHONPATH=/app/src/backend
```

**Option B** — keep the flat copy (simpler, no path change):
```dockerfile
COPY src/backend/ ./          # flat, same as current
CMD ["uv", "run", "python", "main.py"]
```

Same consideration applies to the streamer if it has multi-file internal imports (currently
it appears to be single-file `main.py`, so no issue there).

---

## Verification Checklist

- [ ] `uv lock --check` passes
- [ ] `uv sync` works clean from a fresh clone
- [ ] `uv run python src/streamer/main.py` starts the streamer locally
- [ ] `uv run python src/backend/main.py` starts the backend locally
- [ ] `uv run streamlit run src/dashboard/app.py` opens the dashboard
- [ ] `docker compose build --no-cache` succeeds for all three services
- [ ] `docker compose up` brings the full stack up
- [ ] Dashboard at http://localhost:8501 shows live data
- [ ] No `requirements.txt` files remain: `find . -name requirements.txt`
- [ ] No `pip install` commands remain: `grep -r "pip install" .`
- [ ] `uv.lock` is committed

---

## PR Description Template

```markdown
### What
Migrate from per-service `requirements.txt` to a single root `pyproject.toml` + `uv.lock`,
using `uv` in both local dev and Docker builds.

### Why
- Single source of truth for all deps across three services
- Reproducible builds: lockfile pins exact transitive versions with hashes
- Faster Docker layer caching via uv's resolver
- Parity between local dev (`uv sync`) and Docker (`uv sync --frozen`)

### Changes
- `pyproject.toml`: added `streamer` / `backend` / `dashboard` groups; `websockets` promoted
  to shared root dependency
- `uv.lock`: regenerated
- 3x service `Dockerfile` + root `Dockerfile`: replaced `pip install` with `uv sync --frozen`
- `docker-compose.yml`: build contexts moved to repo root
- Deleted `requirements.txt`, `src/*/requirements.txt`
- README updated to uv-first quickstart

### Verification
- `docker compose build --no-cache` ✅
- `docker compose up` ✅ (stack runs, dashboard live at :8501)
- `uv sync && uv run ...` works for all three services locally ✅
```

---

## Rollback

```bash
git revert <merge-commit-sha>
```

All deleted `requirements.txt` files are recoverable from git history.

---

## Future Work (out of scope)

- GitHub Actions: cache `~/.cache/uv` keyed on `uv.lock`
- Add `uv build` step if any service should ship as a wheel
