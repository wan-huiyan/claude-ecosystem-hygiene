#!/usr/bin/env bash
# PostToolUse hook dispatcher for doc-freshness-reverse-lint.
# Triggered on Edit|Write. Exits silently unless the edited file is a memory
# file (lessons.md, axioms.md, or a feedback_*.md under ~/.claude/projects/).
# If the reverse-lint produces candidates, emits them as additionalContext so
# the current session sees them.

set -euo pipefail

INPUT=$(cat)
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)

[[ -z "$FILE" ]] && exit 0

# Match only the memory-file patterns.
case "$FILE" in
  "$HOME/.claude/lessons.md"|"$HOME/.claude/axioms.md") ;;
  "$HOME/.claude/projects/"*"/memory/feedback_"*.md) ;;
  *) exit 0 ;;
esac

# Run reverse-lint; JSON output.
SCRIPT="$HOME/.claude/skills/doc-freshness-reverse-lint/scripts/reverse_lint.py"
[[ ! -x "$SCRIPT" && ! -f "$SCRIPT" ]] && exit 0

OUT=$(python3 "$SCRIPT" "$FILE" 2>/dev/null || echo '{"candidates":[]}')
COUNT=$(echo "$OUT" | jq '.candidates | length' 2>/dev/null || echo 0)

# Silent on zero hits — user dislikes chatty skills.
[[ "$COUNT" == "0" || -z "$COUNT" ]] && exit 0

# Build a compact human-readable list for additionalContext.
SUMMARY=$(echo "$OUT" | jq -r '
  "doc-freshness-reverse-lint found " + (.candidates | length | tostring) +
  " candidate stale claim(s) in project docs.\n" +
  (.candidates | map(
    "  Rule " + .rule_id + " (\"" + .negated_phrase + "\"): " +
    (.matches | length | tostring) + " match(es)\n" +
    (.matches | map("    - " + .file + ":" + (.line|tostring) + ": " + .content) | join("\n"))
  ) | join("\n")) +
  "\nReview manually — no auto-edits were performed."
' 2>/dev/null)

jq -n --arg msg "$SUMMARY" '{
  hookSpecificOutput: {
    hookEventName: "PostToolUse",
    additionalContext: $msg
  },
  systemMessage: "doc-freshness-reverse-lint: candidate stale claims surfaced"
}'
