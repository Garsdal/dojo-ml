# Releasing `dojoml`

The package is published to PyPI as **`dojoml`** (the import path stays `dojo`, so users do `pip install dojoml` then `from dojo import ...`).

Releases are tag-driven and run entirely in GitHub Actions. Locally you only bump the version and push a tag.

## One-time setup (PyPI Trusted Publishing)

Trusted Publishing means **no API tokens** stored in GitHub secrets. PyPI verifies the GitHub Actions OIDC token directly.

1. Reserve the name on PyPI by creating an account and an empty project — go to https://pypi.org/manage/account/publishing/ and add a **pending publisher**:
   - PyPI Project Name: `dojoml`
   - Owner: `marcusgarsdal` (your GitHub user/org)
   - Repository name: `Dojo`
   - Workflow filename: `release.yml`
   - Environment name: `pypi`
2. In GitHub: Settings → Environments → **New environment** → name it `pypi`. Optionally add reviewers as a manual gate before publish.
3. (Optional) Repeat with TestPyPI if you want a dry run.

After the first successful publish, the "pending publisher" upgrades to a normal trusted publisher tied to the project.

## Cutting a release

1. Make sure `main` is green (`just test && just lint`).
2. Bump the version in [pyproject.toml](pyproject.toml) (`project.version`). Follow semver. For 0.0.x prerelease the API can break freely.
3. Commit:
   ```
   git commit -am "release: v0.0.2"
   ```
4. Tag and push:
   ```
   git tag v0.0.2
   git push origin main --tags
   ```
5. The `Release` workflow will:
   - Verify the tag matches `pyproject.toml` version (fails fast if not)
   - Build sdist + wheel with `uv build`
   - `twine check` the metadata
   - Publish to PyPI via OIDC
   - Create a GitHub Release with auto-generated notes and the built artifacts attached

If the publish step fails, fix forward — never reuse a version number. PyPI rejects re-uploads of an existing version.

## What ships in 0.0.x

- Backend, CLI, agent orchestration, storage adapters
- **Not bundled**: the React frontend in [frontend/](frontend/). `dojo start` will run the API; UI users still need to clone and `npm install` the frontend separately. Bundling built assets is planned for a later release.
