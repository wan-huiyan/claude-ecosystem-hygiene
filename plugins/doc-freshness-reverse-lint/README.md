# doc-freshness-reverse-lint

Detect stale normative guidance in project `docs/` after a correction lands in `~/.claude/lessons.md`, `~/.claude/axioms.md`, or a `feedback_*.md` memory entry.

[![license](https://img.shields.io/github/license/wan-huiyan/claude-ecosystem-hygiene)](../../LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude_Code-skill-orange)](https://claude.com/claude-code)

## Problem

You write a lesson: *"Don't sort by p-value — use effect size."* The lesson is correctly saved. But `docs/research/methodology.md` still says *"Sort top specs by p-value."* Future Claude sessions read that doc as authoritative and repeat the retracted advice.

This skill watches for new "don't X / avoid Y" entries in your memory files, greps your project `docs/`, and surfaces literal matches as **candidate stale claims** — file:line only, no auto-edits.

## Two mechanisms

1. **Reverse-lint (event-driven, primary).** PostToolUse hook fires when `lessons.md` / `axioms.md` / `feedback_*.md` is edited. Extracts the negated phrase, greps project docs, surfaces matches via `hookSpecificOutput.additionalContext`. Silent when there are no hits.
2. **Weekly cron audit (safety net).** Scans `docs/{research,decisions,findings,runbooks}/**/*.md` against all recent negation rules with stricter thresholds and a near-duplicate check for rephrased contradictions.

## Install

### Plugin (recommended)

```bash
claude plugin marketplace add wan-huiyan/claude-ecosystem-hygiene
claude plugin install doc-freshness-reverse-lint@claude-ecosystem-hygiene
```

### Hook wiring (required for event-driven mode)

A hook `command` is a literal string, and a wrong path fails **silently** — the hook just never fires. So print the real path first, then paste it.

**Step 1 — print the installed path.** A `/plugin install` unpacks to `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`, so it creates neither `~/.claude/skills/doc-freshness-reverse-lint/` nor a set `$CLAUDE_PLUGIN_ROOT`. This tries all three roots:

```bash
n=hook_dispatch.sh
s="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/scripts/$n}"
[ -f "$s" ] || s="$HOME/.claude/skills/doc-freshness-reverse-lint/scripts/$n"
# find, not a glob (zsh fails a non-matching glob before 2>/dev/null applies);
# rank on the VERSION segment alone, or aaa-mkt/2.5.0 loses to zzz-mkt/1.0.0.
[ -f "$s" ] || s="$(find -L "$HOME/.claude/plugins/cache" -mindepth 5 -maxdepth 5 \
    -path "*/doc-freshness-reverse-lint/*/scripts/$n" 2>/dev/null \
  | awk -F/ '{print $(NF-2)"\t"$0}' | sort -V -k1,1 | tail -1 | cut -f2- || true)"
[ -f "$s" ] && echo "$s" \
  || echo "$n: not found - tried \$CLAUDE_PLUGIN_ROOT/scripts/, ~/.claude/skills/doc-freshness-reverse-lint/scripts/, and the plugin cache"
```

**Step 2 — paste that absolute path** into `~/.claude/settings.json` under `hooks.PostToolUse` → the `Edit|Write` matcher's `hooks` array:

```json
{
  "type": "command",
  "command": "<absolute path printed by step 1>",
  "timeout": 10
}
```

Re-run step 1 after every plugin upgrade: the cache path carries the version segment, so an upgrade strands a pinned hook on the old directory.

## Invocation

Paths below are relative to the plugin directory. If you are not `cd`'d into it, resolve the script with the three-root snippet in [Hook wiring](#hook-wiring-required-for-event-driven-mode) (swap `hook_dispatch.sh` for the script you want) instead of hardcoding `~/.claude/skills/…`, which does not exist on a plugin install.

```bash
# Reverse-lint a specific memory file (scope inferred from path)
python3 scripts/reverse_lint.py <memory-file-path> [--project-root PATH] [--rescan] [--human]

# Weekly audit
python3 scripts/weekly_audit.py --project-root /path/to/project --human
```

## Conservative guardrails (non-negotiable)

1. **Explicit negation only** — matches `don't / do not / never / avoid / stop / no longer`. Positive rules are ignored.
2. **Multi-token phrase** — ≥ 2 tokens for event-driven, ≥ 3 tokens for weekly cron.
3. **One phrase per rule** — title-preferred. Prevents over-triggering on body rephrasings.
4. **De-dup via seen-cache** at `~/.claude/state/reverse-lint-seen.json`.
5. **Silent on zero hits.** Hook emits nothing when docs are clean.
6. **Never auto-edits.** Every candidate is a human-judgment call.

## What it does NOT do

- Does not read or interpret doc semantics — literal + stem-normalized grep only.
- Does not modify any file.
- Does not replace review — every candidate needs human judgment about whether it's stale.
- Does not scan code, only `.md` under specified doc roots + project `MEMORY.md`.

## Validation

The skill ships with a validation case under `evals/`:
- **No-false-positive test**: a synthetic "don't sort by p-value" rule against a fixed doc that now says "Sorting by p-value is acceptable provided permutation validation confirms..." → returns empty (conservative guardrails prevent over-triggering on qualified/rephrased content).
- **True-positive test**: same rule against a fixture containing the literal phrase → fires correctly.

## Related plugins in this marketplace

- **[ecosystem-audit](../ecosystem-audit/)** — full ecosystem health scan.
- **[memory-hygiene](../memory-hygiene/)** — prune the memory files that this skill watches.
- **[ab-harness](../ab-harness/)** — measure whether artifacts improve outcomes.

## License

MIT
