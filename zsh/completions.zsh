# Completions for profile aliases, fleet, pi profiles, pi-p, cmdk.
[[ -n ${_PROFILE_ZSH_COMPLETIONS_LOADED:-} ]] && return
_PROFILE_ZSH_COMPLETIONS_LOADED=1

_profile_pi_manifest="${PROFILE_DIR:-$HOME/src/profile}/config/pi/packages/pi-profile-management/manifests/profiles.json"

_profile_pi_classes() {
  python3 - "$_profile_pi_manifest" <<'PY'
import json, sys
path = sys.argv[1]
try:
    data = json.load(open(path))
except Exception:
    raise SystemExit(0)
for name in sorted((data.get("classes") or {})):
    print(name)
PY
}

_profile_pi_agents() {
  python3 - "$_profile_pi_manifest" <<'PY'
import json, sys
path = sys.argv[1]
try:
    data = json.load(open(path))
except Exception:
    raise SystemExit(0)
for name in sorted((data.get("agents") or {})):
    print(name)
PY
}

_profile_fleet_lanes() {
  print -l ao0 ao1 ao2 ao3 ao4 infra0 infra1 infra2 infra3 infra4
}

_piclass() {
  local -a classes
  classes=(${(f)"$(_profile_pi_classes)"})
  _describe 'pi profile class' classes
}
compdef _piclass piclass

_fleet_lane_cmd() {
  local -a lanes
  lanes=(${(f)"$(_profile_fleet_lanes)"})
  if (( CURRENT == 2 )); then
    _describe 'lane' lanes
  fi
}
compdef _fleet_lane_cmd fw
compdef _fleet_lane_cmd fp
compdef _fleet_lane_cmd fdn

_fst() {
  local -a lanes
  lanes=(${(f)"$(_profile_fleet_lanes)"})
  if (( CURRENT == 2 )); then
    _describe 'target' lanes
  fi
}
compdef _fst fst

_fd() {
  local -a lanes
  lanes=(${(f)"$(_profile_fleet_lanes)"})
  if (( CURRENT == 2 )); then
    _describe 'target' lanes
  elif (( CURRENT == 3 )); then
    _files
  fi
}
compdef _fd fd

_fu() {
  local -a lanes flags
  lanes=(${(f)"$(_profile_fleet_lanes)"})
  flags=("--infra:create the infra family")
  if (( CURRENT == 2 )); then
    _describe 'flag' flags
    _describe 'lane' lanes
  else
    _describe 'lane' lanes
  fi
}
compdef _fu fu

_pi_p() {
  local -a cmds
  cmds=(
    "lookup:search cached thread titles"
    "context:print a context packet"
    "open:open library / thread"
    "tabs:list open Perplexity tabs"
    "focus:focus a tab"
    "read:read the front pane"
    "md:download markdown"
    "download:alias for md"
    "steer:type a follow-up"
    "new:new Perplexity tab"
    "search:ask via API or live tab"
    "ask:alias for search"
    "usage:API / MCP status"
    "route:show API vs Chrome split"
    "workspace:focus Projects"
    "chrome-prep:prep Chrome JS"
    "mcp-status:detect official MCP"
    "mcp-install:add official MCP"
    "export-request:open export settings"
    "ingest-export:ingest a ZIP"
    "sync:rebuild catalog"
    "install-cron:install launchd sync"
  )
  if (( CURRENT == 2 )); then
    _describe 'pi-p command' cmds
  fi
}
compdef _pi_p pi-p
compdef _pi_p pi-perplexity

_cmdk() {
  local -a cmds
  cmds=(
    "pick:fzf action bar"
    "popup:tmux display-popup"
    "status:layer / session status"
    "layer:detect current layer"
    "list:catalog + live rows"
    "run:run a catalog id"
    "inject:harness prompt buffer"
    "otel:OTEL / metrics lane"
    "classes:pi profile classes"
    "focus:pc pane nvim|pi|zsh"
  )
  if (( CURRENT == 2 )); then
    _describe 'cmdk' cmds
  elif (( CURRENT == 3 )); then
    case "${words[2]}" in
      status) _values 'format' --tmux --prompt --json ;;
      focus) _values 'role' nvim pi zsh ;;
      run)
        local -a ids
        ids=(${(f)"$(cmdk list --tsv 2>/dev/null | cut -f1)"})
        _describe 'action' ids
        ;;
    esac
  fi
}
compdef _cmdk cmdk

# pi binary completions: only install if none exist yet.
if [[ "$(whence -w _pi 2>/dev/null)" != *function* ]]; then
  _profile_pi() {
    local -a cmds flags classes
    cmds=(
      "install:install extension source"
      "remove:remove extension source"
      "uninstall:alias for remove"
      "update:update pi or extensions"
      "list:list installed extensions"
      "config:TUI package resources"
      "auth:credentials / providers"
    )
    flags=(
      "--provider:provider name"
      "--model:model pattern"
      "--mode:text|json|rpc"
      "--print:non-interactive"
      "--continue:continue previous session"
      "--resume:select a session"
      "--session:session path or id"
      "--thinking:off|minimal|low|medium|high|xhigh|max"
      "--help:show help"
    )
    classes=(${(f)"$(_profile_pi_classes)"})
    if (( CURRENT == 2 )); then
      _describe 'pi command' cmds
      _describe 'flag' flags
    fi
  }
  compdef _profile_pi pi
fi
