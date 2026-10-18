---
name: env_security_audit_completed
description: Security audit of .gitignore completed — all sensitive files removed from history, new rules cover all leaks, no source files lost (48 files verified)
type: project
category: common_pitfall
keywords:
  - "git security"
  - ".gitignore hardening"
  - "sensitive data leak"
  - "filter-branch cleanup"
usage_scenarios:
  - "Investigating accidental commits of secrets or databases"
  - "Hardening .gitignore for new projects"
  - "Recovering from public repo data leakage incidents"
---

## Security Incident — Oct 13 2026

### Problem
Sensitive files accidentally committed to **public** GitHub repository:
- `gigs_archive.db` (303 KB — real database with user data)
- `web/admin_passwords.json`, `web/.secret_key`
- `logs/bot.log`, `.qwen/settings.json`, `vscode/settings.json`
- All other `.db` files: `articles.db`, `poster_bot.db`, `posters_web.db`

### Root Cause
Files were staged into git **BEFORE** `.gitignore` rules existed. Known limitation: once tracked, `.gitignore` is ignored for those files.

### Resolution
1. ✅ Removed 9 sensitive files from index + full commit history via `git filter-branch --force`
2. ✅ Rewrote ALL branch histories (master, dev, web_redesign, 3 feature branches = 216 commits total)
3. ✅ Force-pushed cleaned remote
4. ✅ Verified **zero** source files lost (all 48 code files intact: bot/*.py, db/*.py, utils/*.py, web/routes/*.py, templates/*.html, locales/*, CSS/JS assets)
5. ✅ Hardened `.gitignore` — added missing patterns for `.env`, `web/.secret_key`, `web/admins.json`, `.vscode/`, `.qwen/settings.json`, `*.pyo`

### Prevention
`.gitignore` now covers every category of runtime file. Files created by the app at runtime will be automatically ignored — they just can't be accidentally `git add`-ed.
