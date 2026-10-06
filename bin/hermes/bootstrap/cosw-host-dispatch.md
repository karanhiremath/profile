## COSW host-native dispatch

You are running on the host (not the Docker/Podman sandbox). This pane has a
normal local terminal: `pm <project>` and `pl <project>` work here. The
allowlisted `cosw-hostctl` bridge is still available for registered-project
coordination.

1. Use host `pm` / `pl` / `agents` directly when the operator asks for an
   in-pane PM or project-lead session.
2. `cosw-hostctl bootstrap` still works for registry status, ensure-pm/pl,
   and `dispatch-pm`.
3. Do not start a nested CoS-W sandbox unless the operator explicitly asked
   for `cosw --sandbox`. That path persist-attaches to the work-devboxes
   compose service `cosw-sandbox-default`.
4. Seats: default is `moa/default`. `cosw --grok` starts timeout-free
   `cursor/grok-4.6` (non-fast). `cosw --oai` / `cosw --codex` starts
   `openai-codex/gpt-6.1-sol`. `cosw --sonnet`, `--opus`, and `--fable`
   start the corresponding Anthropic Claude 5 seats.
