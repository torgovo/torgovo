#!/usr/bin/env bash
set -euo pipefail

SKILLS_REPO="https://github.com/alirezarezvani/claude-skills.git"
ANTIGRAVITY_DIR="$HOME/.gemini/antigravity/skills"
TEMP_DIR="/tmp/claude-skills-torgovo"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Antigravity Skills — Torgovo Stack"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

mkdir -p "$ANTIGRAVITY_DIR"

# Clone or update
if [ -d "$TEMP_DIR/.git" ]; then
  echo "→ Using cached clone"
  cd "$TEMP_DIR" && git pull --quiet
else
  echo "→ Cloning..."
  rm -rf "$TEMP_DIR"
  git clone --depth 1 "$SKILLS_REPO" "$TEMP_DIR"
fi

# ── Zipped skills (engineering-team/) ───────────────────────────────────────
declare -a ZIP_SKILLS=(
  "senior-architect"
  "senior-backend"
  "senior-frontend"
  "senior-fullstack"
  "senior-devops"
  "senior-qa"
  "tdd-guide"
  "code-reviewer"
)

# ── Folder skills (engineering/skills/) ─────────────────────────────────────
declare -a FOLDER_SKILLS=(
  "database-designer"
  "database-schema-designer"
  "api-design-reviewer"
  "api-test-suite-builder"
  "ci-cd-pipeline-builder"
  "observability-designer"
  "dependency-auditor"
  "tech-debt-tracker"
  "performance-profiler"
  "env-secrets-manager"
  "runbook-generator"
  "migration-architect"
  "release-manager"
  "pr-review-expert"
)

INSTALLED=0
FAILED=0

# Install zipped skills
for SKILL in "${ZIP_SKILLS[@]}"; do
  SRC="$TEMP_DIR/engineering-team/$SKILL.zip"
  DST="$ANTIGRAVITY_DIR/$SKILL"
  
  if [ -f "$SRC" ]; then
    rm -rf "$DST"
    mkdir -p "$DST"
    unzip -q "$SRC" -d "$DST"
    echo "  ✓ $SKILL (from zip)"
    INSTALLED=$((INSTALLED + 1))
  else
    echo "  ✗ MISSING ZIP: engineering-team/$SKILL.zip"
    FAILED=$((FAILED + 1))
  fi
done

# Install folder skills (from engineering/skills/)
for SKILL in "${FOLDER_SKILLS[@]}"; do
  SRC="$TEMP_DIR/engineering/skills/$SKILL"
  DST="$ANTIGRAVITY_DIR/$SKILL"
  
  if [ -d "$SRC" ]; then
    rm -rf "$DST"
    cp -r "$SRC" "$DST"
    echo "  ✓ $SKILL (from folder)"
    INSTALLED=$((INSTALLED + 1))
  else
    echo "  ✗ MISSING: engineering/skills/$SKILL"
    FAILED=$((FAILED + 1))
  fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Done: $INSTALLED installed, $FAILED failed"
echo "  Location: $ANTIGRAVITY_DIR"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Activate in Antigravity:"
echo "  activate_skill(name=\"senior-backend\")      # Django/DRF work"
echo "  activate_skill(name=\"database-designer\")   # Schema / migrations"
echo "  activate_skill(name=\"api-design-reviewer\") # REST endpoint review"
echo "  activate_skill(name=\"ci-cd-pipeline-builder\") # GitHub Actions"