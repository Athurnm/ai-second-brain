---
description: Pull the latest AI Second Brain template updates from upstream into this fork - merge, resolve, and surface any new setup steps
---

Update this harness from the upstream template repo. Do each phase in order and report what changed at the end.

## Phase 1: Sync from upstream

1. Check the remote list: `git remote -v`.
   - If there is no `upstream` remote, add it:
     `git remote add upstream https://github.com/BrianArfi/ai-second-brain.git`
2. `git fetch upstream`
3. Compare before merging: `git log --oneline HEAD..upstream/main` - if empty, tell the user they are already up to date and STOP.
4. Make sure the working tree is clean (`git status`). If there are uncommitted changes, commit them first ("wip before harness update") so nothing is lost in the merge.
5. `git merge upstream/main`

## Phase 2: Resolve conflicts (only if the merge stops)

- Personal files (`CLAUDE.md`, `.env`, `token*.json`, `journal/`, `Dashboard.md`) are gitignored and can never conflict - do not touch them.
- For template files (skills, scripts, docs) the user has NOT deliberately customized: take the upstream version (`git checkout --theirs <file>`).
- For files the user HAS customized: show both versions and ask which to keep before resolving. Never silently discard their edits.
- Finish with `git add -A` on the resolved files + `git commit`.

## Phase 3: Surface new setup steps

1. Diff the env template against their live env:
   - List variable names in `.env.example` that do not exist in `.env`.
   - For each missing variable, quote its comment block from `.env.example` and ask the user for a value (or confirm skipping it if the feature is optional).
   - Append the filled variables to `.env`. NEVER overwrite `.env`.
2. Skim the merged commits (`git log` range from Phase 1, plus `CHANGELOG.md` if updated) and check whether any new skill needs a token, credential, or one-time setup. If yes, point the user to the matching section of `docs/SETUP.md`.

## Phase 4: Verify + report

1. Byte-compile a few core skills to catch a broken merge:
   `python3 -m py_compile .agent/skills/gdocs-create/gdocs_create.py .agent/skills/gdoc-surgical/gdoc_surgical.py`
2. Push the updated fork: `git push origin main`.
3. Report in 5 lines or less: how many commits came in, headline features (from commit subjects), which env vars were added, and anything the user still needs to do manually.
