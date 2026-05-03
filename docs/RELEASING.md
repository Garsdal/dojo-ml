# Releasing `dojoml`

Published to PyPI as **`dojoml`** — import path stays `dojo`, so users do `uv tool install dojoml` (or `pipx install dojoml`) and then run `dojo ...`. Releases are tag-driven and run entirely in GitHub Actions; locally you only bump the version and push a tag.

The relevant workflow files are [.github/workflows/release.yml](../.github/workflows/release.yml) (publish) and [.github/workflows/ci.yml](../.github/workflows/ci.yml) (lint/test/build verification).

## One-time setup (already done for `dojoml`)

Recorded here for reference / future projects. Trusted Publishing means **no API tokens** in GitHub Secrets — PyPI verifies the GitHub Actions OIDC token directly.

1. PyPI → https://pypi.org/manage/account/publishing/ → add **pending publisher**:
   - PyPI Project Name: `dojoml`
   - Owner: `marcusgarsdal`
   - Repository name: `Dojo`
   - Workflow filename: `release.yml`  *(filename only, not the full path)*
   - Environment name: `pypi`
2. GitHub → Settings → Environments → **New environment** → `pypi`. Optionally add reviewers to gate the publish step manually.
3. (Optional) Set up the same on TestPyPI for dry runs.

After the first successful publish the "pending publisher" upgrades to a real one tied to the project.

## Cutting a release

1. Make sure `main` is green: `just test && just lint`. CI will re-run these on the matrix anyway, but failing locally is faster to fix.
2. Bump `project.version` in [pyproject.toml](../pyproject.toml). Follow semver — 0.0.x can break the API freely.
3. Commit and push the bump on `main`:
   ```bash
   git commit -am "release: v0.0.2"
   git push origin main
   ```
4. Tag and push the tag — this is what triggers the release workflow:
   ```bash
   git tag v0.0.2
   git push origin v0.0.2
   ```
5. The `Release` workflow runs three jobs in sequence:
   - **build** — verifies tag == `pyproject.toml` version, builds sdist + wheel with `uv build`, runs `twine check`.
   - **publish-pypi** — uploads to PyPI via OIDC. Pauses for approval if the `pypi` environment requires reviewers.
   - **github-release** — creates the GitHub Release with auto-generated notes and the built artifacts attached.
6. Verify within ~1 minute (PyPI CDN propagation):
   ```bash
   uv tool install dojoml --force
   dojo --version    # → Dojo.ml v0.0.2
   ```

## Version comes from package metadata

`src/dojo/_version.py` reads `__version__` via `importlib.metadata.version("dojoml")`. So the only place to bump is `pyproject.toml`. Don't hand-edit `_version.py`.

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| Workflow fails at "Verify tag matches" | Tag and `pyproject.toml` version disagree | Fix the file, recommit, delete bad tag (`git tag -d v0.0.X && git push origin :refs/tags/v0.0.X`), retag |
| PyPI: "trusted publisher not configured" | Pending-publisher fields don't match the workflow | Most common: workflow filename must be exactly `release.yml`, environment must be exactly `pypi` |
| PyPI: "version already exists" | Tried to republish an existing version | Bump to the next version. PyPI never allows reuse, even after delete |
| `dojo --version` shows old version after install | `uv tool install` hit cache | `uv tool install dojoml --force` |

If publish fails, **always fix forward** — bump the version and retag. Don't try to "redo" a release.

## What ships today (0.0.x)

- Backend, CLI, agent orchestration, all storage adapters
- **Not bundled**: the React frontend in [frontend/](../frontend/). `dojo start` runs the API; UI users still clone the repo and `npm install` the frontend separately. Bundling built assets is planned for a later release.
