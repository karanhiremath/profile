# llm-flags.sh — shared --provider/--model/--thinking parsing for Hermes launch
# wrappers (agents, cos, cosw, dreamw, pm).
#
# Wrappers parse these flags at startup and export the launcher env overrides:
#   HERMES_AGENT_LLM_PROVIDER / HERMES_AGENT_LLM_MODEL / HERMES_AGENT_LLM_THINKING
#   (+ HERMES_INFERENCE_* / HERMES_TUI_PROVIDER / HERMES_MODEL aliases)
# These beat the profile llm block (see bin/hermes/hermes_agents.py) so any
# seat can be pinned to a scoped model at launch, e.g.:
#   cosw --model together/zai-org/GLM-5.3-Flash
#   cos  --provider openai-codex --model gpt-5.5 --thinking high
#   agents up chief-of-staff --model cursor/grok-4.6:slow
#
# --model provider/model splits when the prefix is a known provider. Model IDs
# that contain slashes (together/zai-org/GLM-5.3-Flash style) therefore work
# with a bare --model too. No secret material flows through this helper.

LLM_KNOWN_PROVIDERS="openai-codex openai anthropic anthropic-beta azure-openai-responses amazon-bedrock cursor together xai xai-oauth openrouter pi nemoclaw ollama moa google google-vertex moonshotai groq cerebras zai mistral deepseek"

llm_flags_is_known_provider() {
  local p
  for p in $LLM_KNOWN_PROVIDERS; do
    [ "$1" = "$p" ] && return 0
  done
  return 1
}

# value -> LLM_SPLIT_PROVIDER (may be empty) / LLM_SPLIT_MODEL
llm_flags_split() {
  local value="$1" head
  LLM_SPLIT_PROVIDER=""
  LLM_SPLIT_MODEL="$value"
  case "$value" in
    */*)
      head="${value%%/*}"
      if [ -n "$head" ] && llm_flags_is_known_provider "$head"; then
        LLM_SPLIT_PROVIDER="$head"
        LLM_SPLIT_MODEL="${value#*/}"
      fi
      ;;
  esac
}

# Consumes --provider/--model/--thinking (space and =value forms) out of "$@".
# Remaining args land in LLM_FLAGS_REST (bash array).
parse_llm_flags() {
  LLM_FLAGS_PROVIDER=""
  LLM_FLAGS_MODEL=""
  LLM_FLAGS_THINKING=""
  LLM_FLAGS_REST=()
  local arg next kind value
  while [ "$#" -gt 0 ]; do
    arg="$1"
    case "$arg" in
      --provider|--model|--thinking)
        kind="${arg#--}"
        next="${2:-}"
        if [ "$#" -lt 2 ] || [ -z "$next" ] || [ "${next#-}" != "$next" ]; then
          printf 'ERROR: %s needs a value (e.g. %s together/zai-org/GLM-5.3-Flash)\n' "$arg" "$arg" >&2
          return 1
        fi
        value="$next"
        shift
        ;;
      --provider=*|--model=*|--thinking=*)
        kind="${arg#--}"
        kind="${kind%%=*}"
        value="${arg#*=}"
        ;;
      *)
        LLM_FLAGS_REST+=("$arg")
        shift
        continue
        ;;
    esac
    case "$kind" in
      provider)
        LLM_FLAGS_PROVIDER="$value"
        ;;
      model)
        llm_flags_split "$value"
        # Only adopt the split provider when none was set explicitly; a
        # conflicting pair (--provider X --model Y/Z with X != Y) errors out.
        if [ -n "$LLM_SPLIT_PROVIDER" ]; then
          if [ -n "$LLM_FLAGS_PROVIDER" ] && [ "$LLM_FLAGS_PROVIDER" != "$LLM_SPLIT_PROVIDER" ]; then
            printf 'ERROR: conflicting --provider %s vs --model %s\n' "$LLM_FLAGS_PROVIDER" "$value" >&2
            return 1
          fi
          LLM_FLAGS_PROVIDER="$LLM_SPLIT_PROVIDER"
        fi
        LLM_FLAGS_MODEL="$LLM_SPLIT_MODEL"
        ;;
      thinking)
        LLM_FLAGS_THINKING="$value"
        ;;
    esac
    shift
  done
  return 0
}

# Export the resolved overrides. Only non-empty values are exported so a
# wrapper that parses flags for a subset still inherits profile defaults for
# the rest.
llm_flags_export() {
  if [ -n "${LLM_FLAGS_PROVIDER:-}" ]; then
    export HERMES_AGENT_LLM_PROVIDER="$LLM_FLAGS_PROVIDER"
    export HERMES_INFERENCE_PROVIDER="$LLM_FLAGS_PROVIDER"
    export HERMES_TUI_PROVIDER="$LLM_FLAGS_PROVIDER"
  fi
  if [ -n "${LLM_FLAGS_MODEL:-}" ]; then
    export HERMES_AGENT_LLM_MODEL="$LLM_FLAGS_MODEL"
    export HERMES_INFERENCE_MODEL="$LLM_FLAGS_MODEL"
    export HERMES_MODEL="$LLM_FLAGS_MODEL"
  fi
  if [ -n "${LLM_FLAGS_THINKING:-}" ]; then
    export HERMES_AGENT_LLM_THINKING="$LLM_FLAGS_THINKING"
  fi
}

LLM_FLAGS_USAGE_LINE='--provider <name>              launch-scoped provider (openai-codex, cursor, together, xai, ...)
  --model <provider/model>       launch-scoped model; provider/ prefix splits when known
  --thinking <level>             launch-scoped thinking level (low, medium, high, xhigh)'