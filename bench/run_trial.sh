#!/bin/bash
# One real agent trial (single concurrency). Usage: run_trial.sh <task> <trial_id>
# Requires: HARBOR (path to harbor CLI), DEEPSEEK_API_KEY in the environment. Never commit credentials.
set -uo pipefail
B=$(cd "$(dirname "$0")/.." && pwd); T=$1; ID=$2; cd "$B"
: "${HARBOR:=harbor}"; : "${DEEPSEEK_API_KEY:?set DEEPSEEK_API_KEY}"
pgrep -f "harbor run" >/dev/null && { echo "another harbor run active"; exit 4; }
[ -e jobs_agent/$ID ] && { echo "trial $ID already exists - inspect, do not resubmit"; exit 5; }
export ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic ANTHROPIC_API_KEY="$DEEPSEEK_API_KEY"
export CLAUDE_CODE_MAX_OUTPUT_TOKENS=16000 FESE_INSTALL_AGENT=1 PYTHONPATH=$B
MODEL=deepseek-v4-pro
timeout 2400 "$HARBOR" run -p tasks/$T --agent-import-path bench.harbor_agents.preinstalled_claude:PreinstalledClaudeCode -m $MODEL \
  --ak max_turns=120 --ak 'disallowed_tools=WebFetch WebSearch' \
  --ae ANTHROPIC_SMALL_FAST_MODEL=$MODEL --ae ANTHROPIC_DEFAULT_HAIKU_MODEL=$MODEL \
  -e docker -o jobs_agent --job-name $ID -n 1 -k 1 -r 0 -y
