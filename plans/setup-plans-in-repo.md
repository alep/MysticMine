# Plan: Store plan files inside the repo

## Context

Claude Code writes plan files to `~/.claude/plans/` (outside the repo), so they're never version-controlled. The goal is to automatically mirror every plan file into a `plans/` directory at the repo root whenever one is created or updated, using a project-level PostToolUse hook.

---

## Step 1 — Create `plans/` directory

Copy the existing plan file into the repo to seed the directory:

```
plans/python3-migration.md   ← copy of the current plan
```

The filename is given a human-readable name rather than the auto-generated slug.

---

## Step 2 — Create `.claude/settings.json` with a PostToolUse hook

The hook fires after every Write tool call. If the file written is inside `~/.claude/plans/`, it copies it into `./plans/` (relative to the project root, which is the CWD for project-level hooks).

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "python3 -c \"\nimport sys, json, os, shutil\ndata = json.load(sys.stdin)\nfp = data.get('tool_input', {}).get('file_path', '')\nif os.path.expanduser('~/.claude/plans') in fp:\n    os.makedirs('plans', exist_ok=True)\n    shutil.copy(fp, os.path.join('plans', os.path.basename(fp)))\n\""
          }
        ]
      }
    ]
  }
}
```

---

## Files changed

| File | Change |
|------|--------|
| `plans/python3-migration.md` | NEW — copy of the migration plan |
| `.claude/settings.json` | NEW — project hook config |

---

## Verification

1. Approve and implement this plan — the hook becomes active immediately.
2. Next time a plan is created or updated, check that `plans/<slug>.md` appears in the repo.
3. Confirm with `git status` that the file is tracked.
