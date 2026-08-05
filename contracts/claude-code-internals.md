# Claude Code Internals Contract

**Contract version:** 1.1.0 · **Verified as of:** 2026-08-04

## Purpose

Every tool in this family — [`token-torch`](https://github.com/wan-huiyan/token-torch),
[`context-police`](https://github.com/wan-huiyan/context-police),
[`memory-hygiene`](https://github.com/wan-huiyan/memory-hygiene),
[`session-handoff`](https://github.com/wan-huiyan/session-handoff), and the plugins
bundled in this repo — depends on undocumented-or-semi-documented Claude Code
internals: file locations, transcript schemas, load limits, hook payloads,
settings precedence. Until now each repo hardcoded these assumptions
independently, with different staleness. This file is the **single place to
update when a Claude Code release moves the ground**. When an assumption below
drifts, fix it here first, then propagate to consumers.

Each assumption carries a **status**:

- **docs-backed** — stated in official docs (link given). Safest; drift is announced.
- **observed** — reproducibly seen in real installs but not documented. Re-verify each Claude Code major release.
- **reverse-engineered** — inferred from behavior or community sources. Treat as unverified; do not build load-bearing logic on it.

Run [`contracts/probe_internals.py`](probe_internals.py) against a live
`~/.claude` to check the locally-checkable subset (OK / DRIFT / UNKNOWN per
assumption).

## Filesystem layout

| Assumption | Value | Status | Verified as of | How to re-verify |
|---|---|---|---|---|
| Session transcript location | `~/.claude/projects/<project-dir>/<session-uuid>.jsonl`, where `<project-dir>` is the project path with `/` (and `.`) replaced by `-` (e.g. `-home-user-myrepo`) | observed | 2026-07-03 | `ls ~/.claude/projects/*/` after a session; confirm a new `<uuid>.jsonl` appears for the cwd-derived dir. `probe_internals.py` checks existence. |
| Subagent transcript layout | Per-session dir `~/.claude/projects/<project-dir>/<session-uuid>/subagents/agent-*.jsonl`; workflow-spawned agents nest as `subagents/workflows/wf_<runid>/agent-*.jsonl` | observed | 2026-07-03 | Spawn a subagent (Agent tool), then `find ~/.claude/projects -path '*subagents*' -name 'agent-*.jsonl' -mmin -10`. |
| Auto-memory path | `~/.claude/projects/<project-dir>/memory/MEMORY.md` | docs-backed ([code.claude.com/docs/en/memory](https://code.claude.com/docs/en/memory)) | 2026-07-03 | Check the memory docs page; confirm path on disk after Claude writes a memory. `probe_internals.py` checks existence. |
| Skills directory | `~/.claude/skills/<skill-name>/SKILL.md` (user-level); plugins expose skills the same way under their plugin root | docs-backed ([code.claude.com/docs/en/skills](https://code.claude.com/docs/en/skills)) | 2026-07-03 | Docs page; `probe_internals.py` parses frontmatter of installed SKILL.md files. |

## Transcript JSONL schema

| Assumption | Value | Status | Verified as of | How to re-verify |
|---|---|---|---|---|
| Usage token fields | Assistant entries carry `message.usage` with `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` (mirrors the public API usage object) | docs-backed for the API shape ([Claude API messages docs](https://docs.claude.com/en/api/messages)); its presence in local transcripts is observed | 2026-07-03 | Sample a recent session JSONL: `python3 contracts/probe_internals.py` parses one line and asserts the fields. token-torch's cost math depends on all four fields. |
| One JSON object per line | Each transcript line is a self-contained JSON object with a `type` field (`user`, `assistant`, `summary`, …) | observed | 2026-07-03 | `head -1 <session>.jsonl \| python3 -m json.tool`. |

## Memory & context limits

| Assumption | Value | Status | Verified as of | How to re-verify |
|---|---|---|---|---|
| MEMORY.md load limit | Only the **first 200 lines / 25KB** of auto-memory MEMORY.md are loaded into context; the rest is on-demand | docs-backed ([code.claude.com/docs/en/memory](https://code.claude.com/docs/en/memory)) | 2026-07-03 | Re-read the memory docs page each release. memory-hygiene's bloat threshold and ecosystem-audit's memory axis key on this. |
| CLAUDE.md size guidance | Keep CLAUDE.md ≤ ~200 lines; larger files degrade adherence | docs-backed (memory/best-practices docs) | 2026-07-03 | Re-read docs; this is guidance, not a hard truncation — do not treat as a cutoff. |

## Skills catalog & settings

| Assumption | Value | Status | Verified as of | How to re-verify |
|---|---|---|---|---|
| SKILL.md frontmatter | YAML frontmatter with `name`, `description`; `disable-model-invocation: true` removes the skill from the always-injected catalog while keeping it user-invocable | docs-backed ([code.claude.com/docs/en/skills](https://code.claude.com/docs/en/skills)) | 2026-07-03 | Docs page; flip the flag on a test skill and confirm it disappears from the catalog listing. context-police's global lever depends on this. |
| `skillOverrides` in settings | Per-project `settings.json` `skillOverrides` map can hide/expose individual skills | docs-backed ([code.claude.com/docs/en/settings](https://code.claude.com/docs/en/settings)) | 2026-07-03 | Docs page; `probe_internals.py` notes whether the key is present in a live settings.json. context-police's per-project lever depends on this. |
| Skill-listing budget defaults | `skillListingBudgetFraction` ≈ **0.01** of context window; `skillListingMaxDescChars` ≈ **1536** per skill | observed (constant names + values read out of the v2.1.221 binary; `/doctor` shows the resulting budget) — **drift-prone, re-check every release** | 2026-08-04 | Run `/doctor` in Claude Code and read the skill-listing budget section; the constant *names* come from the bundled binary, so re-grep it after a major upgrade. These are the constants context-police's token-tax math assumes **and the constants `.github/scripts/check_skill_descriptions.py` gates on in CI** — a silent default change skews every estimate and mis-sets the gate. |
| Skill-listing truncation semantics | Over `skillListingMaxDescChars` the harness keeps `full[:cap-1]` and appends an ellipsis — it does **not** summarise, it cuts mid-word, and nothing warns. So the dead tail of an over-cap description is `len(desc) - (cap - 1)` characters, one MORE than the naive `len(desc) - cap` | observed (binary; reproduced by the gate) | 2026-08-04 | `python3 .github/scripts/check_skill_descriptions.py . --triggers` on a deliberately over-cap SKILL.md and compare its "+N cut" figure against the text the model actually receives. The gate's own off-by-one here was corrected upstream in context-police v2.2.0. |
| Naming: which constant is which | Canonical name is **`skillListingMaxDescChars`** (as in the binary and in `check_skill_descriptions.py`). `maxSkillDescriptionChars` is an **older alias** used in earlier revisions of this contract and in context-police's bundled SKILL.md before upstream v2.2.0 | observed | 2026-08-04 | Grep the repo for both spellings; only `skillListingMaxDescChars` should remain. Two names for one constant is how a gate and a doc silently stop describing the same thing. |
| Settings precedence | Managed (enterprise) > CLI flags > `.claude/settings.local.json` > `.claude/settings.json` (project) > `~/.claude/settings.json` (user) | docs-backed ([code.claude.com/docs/en/settings](https://code.claude.com/docs/en/settings)) | 2026-07-03 | Docs page. Any tool that *writes* settings (context-police applier) must respect this ordering when predicting effective config. |

## Hooks

| Assumption | Value | Status | Verified as of | How to re-verify |
|---|---|---|---|---|
| Hook events | `SessionStart`, `SessionEnd`, `PreCompact`, `UserPromptSubmit`, `PostToolUse` (plus others) fire with a JSON payload on stdin | docs-backed ([code.claude.com/docs/en/hooks](https://code.claude.com/docs/en/hooks)) | 2026-07-03 | Docs page; wire a hook that dumps stdin to a file and diff the payload schema against what doc-freshness-reverse-lint and session-handoff parse. |
| `hookSpecificOutput.additionalContext` | A hook may return JSON `{"hookSpecificOutput": {"hookEventName": ..., "additionalContext": "..."}}` to inject context into the conversation | docs-backed ([code.claude.com/docs/en/hooks](https://code.claude.com/docs/en/hooks)) | 2026-07-03 | Docs page; doc-freshness-reverse-lint's event-driven surfacing uses exactly this contract. |

## Environment & runtime

| Assumption | Value | Status | Verified as of | How to re-verify |
|---|---|---|---|---|
| Session id env var | `$CLAUDE_CODE_SESSION_ID` is set in Bash-tool subprocesses and matches the transcript filename uuid | observed | 2026-07-03 | `echo $CLAUDE_CODE_SESSION_ID` from a Bash tool call; confirm a matching `<uuid>.jsonl` exists. session-handoff uses it to locate the live transcript. |
| "Auto Dream" background consolidation gates | Background memory consolidation ("dream") runs are gated on idle time / session volume before rewriting MEMORY.md | **reverse-engineered** (community sources only) — treat as unverified | 2026-07-03 | No official docs. Do NOT build load-bearing logic on this; if memory-hygiene sees MEMORY.md rewritten without user action, log it as evidence, don't assume the trigger conditions. |

## Change log

- **1.1.0** (2026-08-04) — **Skill-listing cap row updated for its first load-bearing CI consumer.** `.github/scripts/check_skill_descriptions.py` now gates every PR and push on this constant, so the row records (a) the canonical name `skillListingMaxDescChars`, retiring the `maxSkillDescriptionChars` alias this file used at 1.0.0, (b) the evidence upgrade — constant names and values read out of the v2.1.221 binary, not only inferred from `/doctor` output, and (c) two new rows: the truncation semantics (`full[:cap-1]` + ellipsis, so the dead tail is `len(desc) - (cap - 1)`) and an explicit naming row, because the same constant carrying two names in one repo is exactly how a gate and a doc stop describing the same thing. Status stays **observed** and **drift-prone**: reading a constant out of one binary build is stronger evidence than `/doctor`, but it is still not documented and can move in any release.
- **1.0.0** (2026-07-03) — Initial consolidation. Extracted from assumptions previously hardcoded independently in token-torch, context-police, memory-hygiene, session-handoff, and this bundle's plugins.
