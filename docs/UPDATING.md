# Updating Your Fork

The template repo keeps improving after you fork it. This guide shows how to pull
those updates into YOUR fork without losing your personal setup.

**Your personal files are safe.** `CLAUDE.md`, `.env`, all `token*.json` files,
`journal/`, and `Dashboard.md` are gitignored - an update never touches them.

## Option A: Let your AI do it (recommended)

Your fork IS an AI harness - so make the AI do the update.

**If you already have the `/update-harness` command** (any fork synced after
July 2026): just type `/update-harness` in Claude Code. Done.

**First time updating** (the command arrives WITH the update): paste this prompt
into Claude Code inside your fork's folder:

> Update my fork from the upstream template: add the remote
> `upstream https://github.com/BrianArfi/ai-second-brain.git` if it's missing,
> fetch it, merge `upstream/main` into my branch, and push to my origin.
> If there are merge conflicts in files I haven't customized, take the upstream
> version; if I customized them, show me both and ask. Afterwards, compare
> `.env.example` against my `.env`, list any NEW variables I need to fill in,
> and help me fill them.

From the next update onward you'll have `/update-harness`.

## Option B: GitHub button + git pull

1. Open your fork on GitHub: `github.com/<your-username>/ai-second-brain`
2. You'll see "This branch is N commits behind you/ai-second-brain:main" -
   click **Sync fork → Update branch**
3. On your machine:
   ```bash
   cd ai-second-brain
   git pull
   ```

## Option C: Pure terminal

```bash
cd ai-second-brain

# One-time: register the original repo as "upstream"
git remote add upstream https://github.com/BrianArfi/ai-second-brain.git

# Every update:
git fetch upstream
git merge upstream/main
git push origin main
```

## After every update: check for new .env variables

Updates sometimes add variables to `.env.example`. Your live `.env` does NOT
update itself. Compare the two files and copy over anything new:

```bash
# Show variable names present in the template but missing from your .env
grep -oE '^[A-Z_]+=' .env.example | sort > /tmp/template_vars
grep -oE '^[A-Z_]+=' .env | sort > /tmp/my_vars
comm -23 /tmp/template_vars /tmp/my_vars
```

(Option A does this check for you automatically.)

## If a merge conflict appears

It only happens when you edited a template file that the update also changed.
Easiest fix: ask your AI - *"resolve this merge conflict, prefer the upstream
version unless I customized the file on purpose."*
