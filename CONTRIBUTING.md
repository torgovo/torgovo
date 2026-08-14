# Contributing to Torgovo2

Thanks for contributing! This guide keeps the project healthy and reviewable.

## Project model

- **Canonical docs live in `docs/`** (`docs/README.md` is the index). Never create
  a parallel docs folder — that caused the old `docs/updated docs (claude)/` drift.
- `CLAUDE.md` and `docs/PROJECT.md` are the rules for AI-assisted development.
  Follow them when editing with an assistant.

## Development workflow

1. Branch from `develop` (not `main`): `git checkout -b feat/my-change develop`
2. Make your change. Every non-trivial block gets a comment.
3. Run checks locally before pushing:

   ```bash
   pre-commit run --all-files
   python manage.py check
   .venv/bin/python -m pytest tests/ -q
   ```

4. Commit with a Conventional Commit message (enforced by the `commit-msg` hook):

   ```
   <type>(<scope>): <short summary>

   <optional body — what, why, not how>
   ```

   Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `security`.
   Example: `fix(webhooks): validate secret in body for non-TradingView platforms`

5. Open a Pull Request into `main` (CI runs `pre-commit`, `manage.py check`,
   and the full test suite; PRs to `main` are gated).
6. Use the PR template from `docs/internal/COMMS.md`.

## Testing standard

- Add tests for every change (all scenarios, including worst cases).
- Run the full suite — it must stay green (`1859+ passed`, 13 skipped).
- Never weaken or delete a passing test to make a change "fit".

## Releases

- Semantic versioning: tag releases `v<major>.<minor>.<patch>` (e.g. `v0.1.0`).
- Each release updates `docs/CHANGELOG.md`.
- Full sequence lives in `docs/internal/SOPs.md` (deploy section).

## Incidents

Follow `docs/internal/SOPs.md` incident tiers (SEV1 15min / SEV2 1hr / SEV3 24hr)
and notify via the `#incidents` channel per `docs/internal/COMMS.md`.
