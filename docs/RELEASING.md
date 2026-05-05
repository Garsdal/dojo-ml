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

The fast path is **paste the [release prompt](#release-prompt-for-llms) into a fresh Claude Code session at the end of your work session and let it drive**. It enforces the changelog discipline and pauses for confirmation before the irreversible `git push --tags`.

If you'd rather do it by hand:

1. Make sure `main` is green: `just test && just lint`. CI will re-run these on the matrix anyway, but failing locally is faster to fix.
2. Update [CHANGELOG.md](../CHANGELOG.md): add a new `## [vX.Y.Z] - YYYY-MM-DD` section above the previous one. Always include `### Agent prompts` first, even if empty — see "Why prompt changes get a dedicated section" below.
3. Bump `project.version` in [pyproject.toml](../pyproject.toml). Follow semver — 0.0.x can break the API freely.
4. Commit the bump + changelog together:
   ```bash
   git commit -am "release: v0.0.X"
   git push origin main
   ```
5. Tag and push the tag — this is what triggers the release workflow:
   ```bash
   git tag v0.0.X
   git push origin v0.0.X
   ```
6. The `Release` workflow runs three jobs in sequence:
   - **build** — verifies tag == `pyproject.toml` version, builds sdist + wheel with `uv build`, runs `twine check`.
   - **publish-pypi** — uploads to PyPI via OIDC. Pauses for approval if the `pypi` environment requires reviewers.
   - **github-release** — creates the GitHub Release with auto-generated notes and the built artifacts attached.
7. Verify within ~1 minute (PyPI CDN propagation):
   ```bash
   uv tool install dojoml --force
   dojo --version    # → Dojo.ml v0.0.X
   ```

## Why prompt changes get a dedicated section

The agent's behaviour is steered almost entirely by:

- The system prompt in [src/dojo/agents/prompts.py](../src/dojo/agents/prompts.py)
- Tool descriptions in [src/dojo/tools/](../src/dojo/tools/) (the agent reads these from the MCP tool schema)
- The end-of-run extractor prompt in [src/dojo/agents/summarizer.py](../src/dojo/agents/summarizer.py)

A one-word change to any of these can shift agent behaviour across every domain — silently, without breaking a single test. The CHANGELOG's `### Agent prompts` section is the rolling record of "what did we tell the agent differently this version?" and is what makes regressions traceable. Always populate it (or write `(none)`).

## Release prompt for LLMs

Paste the block below into a Claude Code session at the end of your work and the model will drive the release. It expects a clean working tree (or the changes you just made are what's shipping). It will pause and ask before the irreversible `git push origin <tag>`.

````
You are completing a release of Dojo.ml. Drive these steps in order. Do not
skip the prompt-diff scrutiny in step 4 — that's the whole point of having a
release workflow in this repo.

# 1. Sanity check

Run `git status`. If the tree has untracked or modified files, those are what's
shipping in this release — confirm with the user before proceeding. Run
`just test && just lint` and stop on failure (don't try to fix; ask the user).

# 2. Find the previous release and the new version

- Run `git describe --tags --abbrev=0` to get the most recent tag.
- Read `version` from `pyproject.toml`. They should match.
- Default new version: bump patch (0.0.x → 0.0.x+1). 0.0.x can break freely;
  bump minor only on substantial new features. Ask the user if unsure.

# 3. Gather the commit log

Run `git log <last-tag>..HEAD --oneline` for the commits since the last
release. (If the working tree is dirty, also include uncommitted changes —
they'll go in this release's commit.)

# 4. CRITICAL — scrutinize prompt and tool-description changes

Run each of these and READ the diff fully. Do not skim. A renamed flag, a
deleted "skip" or "always", a new bullet — all of these change agent
behaviour and MUST be called out:

- `git diff <last-tag>..HEAD -- 'src/dojo/agents/prompts.py'`
- `git diff <last-tag>..HEAD -- 'src/dojo/agents/summarizer.py'` (if it exists)
- `git diff <last-tag>..HEAD -- 'src/dojo/tools/'` (every tool description the
  agent sees)

If the working tree is dirty, also run the same `git diff` commands without
the range to capture uncommitted changes.

For each prompt/description change, write ONE bullet describing what the
agent will now do differently. Reference the file with a markdown link.
Don't paraphrase the diff — name the actual rule that changed.

# 5. Update CHANGELOG.md

Insert a new section directly below `## [Unreleased]`:

```markdown
## [vX.Y.Z] - YYYY-MM-DD

### Agent prompts
<one bullet per change from step 4. If none, write "(none in this release)">

### Added
<new user-visible features, modules, CLI commands, API routes>

### Changed
<refactors with user-visible effects, tightened invariants, behavioural shifts>

### Fixed
<bugs fixed>

### Removed
<deletions visible to users>
```

Skip empty sections except `### Agent prompts` — that one is always present.

# 6. Bump the version

Edit `pyproject.toml`: change `version = "X.Y.Z"` to the new version. Don't
touch `src/dojo/_version.py` — it reads from package metadata.

# 7. Commit

Stage CHANGELOG.md, pyproject.toml, uv.lock (if dirty), and any other files
that are part of this release. Commit:

```bash
git commit -m "release: vX.Y.Z"
```

# 8. STOP and ask for confirmation

Show the user:
- The CHANGELOG entry you just wrote (the section, not the whole file)
- The commit hash and message

Ask: "Ready to push and publish vX.Y.Z to PyPI?" — wait for an explicit
yes. The next step is irreversible: PyPI never accepts the same version
twice, even after delete.

# 9. Push and tag

On confirmation:

```bash
git push origin main
git tag vX.Y.Z
git push origin vX.Y.Z
```

The tag push triggers `.github/workflows/release.yml` which builds and
publishes to PyPI.

# 10. Report

Tell the user:
- Tag pushed
- Watch the publish at https://github.com/<owner>/Dojo/actions
- Verify with `uv tool install dojoml --force && dojo --version`
````

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
