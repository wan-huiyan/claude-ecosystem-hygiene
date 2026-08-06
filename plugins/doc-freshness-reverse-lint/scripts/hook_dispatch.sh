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

# Locate reverse_lint.py. It is a sibling of this script, so the directory this
# file lives in is tried first and is correct under every install method. The
# three install roots below are the fallback for the case where this dispatcher
# was copied somewhere else: a plugin install creates NEITHER
# $CLAUDE_PLUGIN_ROOT (unset outside the plugin's own hook runner) NOR
# ~/.claude/skills/ — it unpacks under
# ~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/.
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

SCRIPT="$SELF_DIR/reverse_lint.py"
[[ -f "$SCRIPT" ]] || SCRIPT="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/scripts/reverse_lint.py}"
[[ -f "$SCRIPT" ]] || SCRIPT="$HOME/.claude/skills/doc-freshness-reverse-lint/scripts/reverse_lint.py"
# find, not a glob: under zsh a non-matching glob fails at expansion time, before
# 2>/dev/null can suppress anything. Rank on the VERSION segment alone — the
# marketplace name precedes it in the path, so a plain `sort -V` over whole paths
# would let aaa-mkt/2.5.0 lose to zzz-mkt/1.0.0.
[[ -f "$SCRIPT" ]] || SCRIPT="$(find -L "$HOME/.claude/plugins/cache" -mindepth 5 -maxdepth 5 \
    -path '*/doc-freshness-reverse-lint/*/scripts/reverse_lint.py' 2>/dev/null \
  | awk -F/ '{print $(NF-2)"\t"$0}' | sort -V -k1,1 | tail -1 | cut -f2- || true)"

if [[ ! -f "$SCRIPT" ]]; then
  # Stay silent to the user (this is a PostToolUse hook), but say what was tried
  # on stderr so `claude --debug` shows the real reason. A failed lookup is not
  # evidence that the skill is uninstalled.
  echo "reverse_lint.py: not found - tried $SELF_DIR/, \$CLAUDE_PLUGIN_ROOT/scripts/, ~/.claude/skills/doc-freshness-reverse-lint/scripts/, and the plugin cache" >&2
  exit 0
fi

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
