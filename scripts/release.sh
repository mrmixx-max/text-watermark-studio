#!/usr/bin/env bash
# Release script for Text Watermark Studio
# Usage: ./scripts/release.sh <version>
# Example: ./scripts/release.sh 2.1.0
#
# This script:
# 1. Validates the version format
# 2. Ensures working directory is clean
# 3. Runs tests
# 4. Updates pyproject.toml version
# 5. Commits the version bump
# 6. Creates an annotated tag
# 7. Pushes to origin
#
# After push, the GitHub Actions workflow will:
# - Build and publish to PyPI (via OIDC)
# - Create a GitHub Release with auto-generated notes

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Validate arguments
if [ $# -ne 1 ]; then
    echo "Usage: $0 <version>"
    echo "Example: $0 2.1.0"
    exit 1
fi

VERSION="$1"

# Validate version format
if ! echo "$VERSION" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9]+)?$'; then
    log_error "Invalid version format: $VERSION"
    log_error "Expected format: X.Y.Z or X.Y.Z-label (e.g., 2.1.0 or 2.1.0-rc1)"
    exit 1
fi

cd "$PROJECT_ROOT"

# Check for clean working directory
if [ -n "$(git status --porcelain)" ]; then
    log_error "Working directory is not clean. Commit or stash changes first."
    git status --short
    exit 1
fi

# Check we're on main/master branch
BRANCH=$(git branch --show-current)
if [ "$BRANCH" != "main" ] && [ "$BRANCH" != "master" ]; then
    log_warn "Not on main/master branch (current: $BRANCH)"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Pull latest
log_info "Pulling latest changes..."
git pull origin "$BRANCH"

# Run tests
log_info "Running tests..."
if ! make test; then
    log_error "Tests failed. Fix issues before releasing."
    exit 1
fi

# Run linter
log_info "Running linter..."
if ! make lint; then
    log_error "Lint failed. Fix issues before releasing."
    exit 1
fi

# Update version in pyproject.toml
CURRENT_VERSION=$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
log_info "Current version: $CURRENT_VERSION"
log_info "New version: $VERSION"

if [ "$CURRENT_VERSION" = "$VERSION" ]; then
    log_warn "Version unchanged ($VERSION). Continuing with tag..."
else
    # Update version using sed (portable)
    if [[ "$(uname)" == "Darwin" ]]; then
        sed -i '' "s/^version = \".*\"/version = \"$VERSION\"/" pyproject.toml
    else
        sed -i "s/^version = \".*\"/version = \"$VERSION\"/" pyproject.toml
    fi
    log_info "Updated pyproject.toml to $VERSION"
fi

# Commit version bump (if changed)
if [ -n "$(git status --porcelain pyproject.toml)" ]; then
    git add pyproject.toml
    git commit -m "Bump version to $VERSION"
    log_info "Committed version bump"
fi

# Create annotated tag
TAG="v${VERSION}"
log_info "Creating tag: $TAG"
git tag -a "$TAG" -m "Release $TAG"

# Push
log_info "Pushing to origin/$BRANCH..."
git push origin "$BRANCH"
log_info "Pushing tag $TAG..."
git push origin "$TAG"

log_info "Release $TAG initiated!"
log_info "GitHub Actions will now build and publish to PyPI."
log_info "Monitor progress at: https://github.com/$(git remote get-url origin | sed 's/.*github.com[:\/]//;s/\.git$//')/actions"
