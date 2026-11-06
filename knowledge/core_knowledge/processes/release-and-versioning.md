# Release, Branching & Versioning Standards

> **Summary:** Technical specification of the Git branching strategy, testing quality gates, conventional commit standards, semantic versioning, and release procedures.

**Status:** 🟩 Stable  
**Owner role:** Lead Maintainer (link to [ownership-map.md](../team_and_stakeholders/ownership-map.md))  
**Last updated:** 2026-11-06  

---

## Table of Contents

- [Overview](#overview)
- [Branching Strategy: dev to main](#branching-strategy-dev-to-main)
- [Quality Gates & Verification Checklists](#quality-gates--verification-checklists)
- [Conventional Commit Standards](#conventional-commit-standards)
- [Semantic Versioning (SemVer)](#semantic-versioning-semver)
- [Release Execution Runbook](#release-execution-runbook)
- [Operational Notes](#operational-notes)
- [Appendix: Release Verification Checklist](#appendix-release-verification-checklist)

---

## Overview

This document outlines the standard release lifecycle, branch isolation model, quality gates, and commit conventions required for maintaining high operational stability across the repository.

---

## Branching Strategy: `dev` to `main`

The repository employs a streamlined two-tier branch hierarchy:

```
[dev] ───────(feature / bugfix / refactor)───────┐
  │                                               │
  │   (Automated Quality Gate: 77 Tests Passing)   │
  ▼                                               ▼
[main] ────────────────────────────────────► [Tag: vX.Y.Z]
```

### 1. `main` Branch (Production)
- **Status:** Protected, production-ready branch.
- **Rule:** Direct commits to `main` are strictly forbidden. All code entering `main` arrives via verified pull requests from `dev`.
- **Invariants:** 100% test pass rate, zero regression failures, all documentation synchronized.

### 2. `dev` Branch (Integration)
- **Status:** Primary active integration branch.
- **Usage:** Feature branches and refactors branch off from `dev` and merge back into `dev` after local verification.

### 3. Feature & Fix Branches
- **Naming Conventions:**
  * `feat/<short-description>` (e.g., `feat/graph-viewer-clustering`)
  * `fix/<short-description>` (e.g., `fix/date-parsing-dst-boundary`)
  * `refactor/<short-description>` (e.g., `refactor/event-bus-ring-buffer`)

---

## Quality Gates & Verification Checklists

Before merging any branch into `dev` or promoting `dev` to `main`, the following four automated gates must pass:

### Gate 1: Automated Test Suite (100% Pass Rate)
- **Command:** `uv run pytest`
- **Criteria:** All 77 unit and integration tests must pass with zero failures or errors:
  * 42 Unit tests (`tests/unit/`)
  * 35 Integration tests (`tests/integration/`)
  * Fast execution time: $< 4$ seconds.

### Gate 2: Context Window Integrity Check
- **Verification:** Confirm that `num_ctx = 131072` remains strictly preserved across `.env`, `src/config.py`, and `src/llm/client.py`.

### Gate 3: Core-Knowledge Isolation Audit
- **Verification:**
  1. No personal human names of maintainers or developers appear outside `knowledge/core_knowledge/team_and_stakeholders/`.
  2. Zero paths or citations refer to isolated private directories.

### Gate 4: Clean Git Working Tree
- **Command:** `git status`
- **Criteria:** No untracked cache artifacts, database files, or scratch logs staged for commit.

---

## Conventional Commit Standards

All commit messages must adhere to the Conventional Commits specification:

```
<type>(<optional-scope>): <concise-description>

[optional body explaining architectural rationale]

[optional footer(s)]
```

### Permitted Commit Types
- `feat`: A new end-user capability or agent feature (e.g., `feat(ui): add connected papers graph visualization`).
- `fix`: A bug fix in algorithms, scrapers, or database logic (e.g., `fix(dates): normalize european date dayfirst parsing`).
- `docs`: Documentation additions or Core-Knowledge updates (e.g., `docs(kipi): comprehensive repository documentation pass`).
- `refactor`: Code restructuring without feature addition or bug resolution (e.g., `refactor(pipeline): extract cooperative cancellation token`).
- `test`: Adding or updating unit/integration tests (e.g., `test(storage): add sqlite wal concurrency tests`).
- `perf`: Performance optimizations (e.g., `perf(vector): implement batch embeddings endpoint`).
- `chore`: Maintenance tasks, dependencies, or configuration updates (e.g., `chore(deps): update uv lockfile`).

---

## Semantic Versioning (SemVer)

Releases are tagged according to Semantic Versioning (`MAJOR.MINOR.PATCH`):
- **MAJOR (`X.0.0`):** Breaking architectural changes (e.g., database schema restructuring requiring migration, major model changes).
- **MINOR (`0.Y.0`):** Backwards-compatible feature additions (e.g., adding a new agent, new UI visualization view, or new CLI flag).
- **PATCH (`0.0.Z`):** Backwards-compatible bug fixes and performance improvements (e.g., regex noise pattern updates, date parsing fixes).

---

## Release Execution Runbook

When cutting a new release from `dev` to `main`:

```bash
# 1. Ensure you are on dev with latest changes
git checkout dev
git pull origin dev

# 2. Run the complete automated test suite
uv run pytest

# 3. Synchronize Core-Knowledge documentation
# (Verify all components and processes are documented)

# 4. Switch to main and merge dev
git checkout main
git merge --no-ff dev -m "release: promote dev to main (v2.0.0)"

# 5. Tag release
git tag -a v2.0.0 -m "Release v2.0.0 — Modular multi-agent OSINT architecture"

# 6. Push to remote
git push origin main --tags
git push origin dev
```

---

## Operational Notes

- **Rollback Procedure:** In the event of an operational regression, revert `main` to the previous release tag:
  ```bash
  git checkout main
  git revert HEAD -m "revert: rollback release to previous stable tag"
  git push origin main
  ```

---

## Appendix: Release Verification Checklist

- [ ] All 77 unit and integration tests passing (`uv run pytest`).
- [ ] Context window locked at `131072` tokens in `src/config.py` and `src/llm/client.py`.
- [ ] Database migrations tested on existing `political_intel.db`.
- [ ] ChromaDB vector collection verifies clean upsert and retrieval.
- [ ] UI tested on both Light and Dark mode.
- [ ] Core-Knowledge documents updated and checked against isolation rules.

---

_Generated by Kipi — Core-Knowledge Keeper_
