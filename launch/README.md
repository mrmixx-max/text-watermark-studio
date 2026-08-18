# Launch Artifacts — Text Watermark Studio v2.0.0

This directory contains all launch and marketing prep artifacts for the v2.0.0 public release.

> ⚠️ **These are preparation-only. Nothing has been posted publicly.**

## Files

| File | Purpose |
|---|---|
| `GITHUB_REPO_DESCRIPTION.md` | One-line repo summary + GitHub Topics (tags) for discoverability |
| `RELEASE_POST.md` | CHANGELOG-style announcement for the v2.0.0 GitHub Release |
| `TWITTER_ANNOUNCEMENT.md` | 280-char X/Twitter announcement (primary + alternatives) |
| `LINKEDIN_ANNOUNCEMENT.md` | Full LinkedIn post with hashtags |
| `DEMO_SCRIPT.md` | Three copy-pasteable demo use-cases with commands |
| `CONTRIBUTING.md` | Improved contributor guide (replaces the stub in the repo root) |

## How to Use

### GitHub Release
1. Copy the content of `RELEASE_POST.md` into the GitHub Release notes for tag `v2.0.0`.
2. Attach the wheel (`dist/text_watermark_studio-2.0.0-py3-none-any.whl`) and sdist (`dist/text_watermark_studio-2.0.0.tar.gz`).
3. Add the topics from `GITHUB_REPO_DESCRIPTION.md` → Topics section.

### Social Media
1. Post the primary Twitter announcement (`TWITTER_ANNOUNCEMENT.md`).
2. Post the LinkedIn announcement (`LINKEDIN_ANNOUNCEMENT.md`).
3. Pin a tweet or create a thread for visibility.

### Contributor Guide
1. Replace the root `CONTRIBUTING.md` with the improved version from this directory.
2. The original was a 10-line stub; the new version has setup, structure, style guide, testing, and PR process.

### Demo Script
1. Use `DEMO_SCRIPT.md` for live demos, tutorials, or onboarding material.
2. Each scenario is self-contained and runs locally.

## Checklist

- [ ] GitHub repo description updated
- [ ] GitHub Topics added
- [ ] GitHub Release created with `RELEASE_POST.md`
- [ ] X/Twitter announcement posted
- [ ] LinkedIn announcement posted
- [ ] Root `CONTRIBUTING.md` replaced with improved version
- [ ] Demo script tested end-to-end
