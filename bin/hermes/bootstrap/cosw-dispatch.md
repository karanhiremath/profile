## COSW project-dispatch bootstrap (injected by the generic launcher)

You are running in a sandbox. The host tmux socket is intentionally not exposed, and `pm`/`pl` are host-interactive operator commands. Use only the allowlisted bridge below for host project coordination:

1. At the start of every fresh session, run `cosw-hostctl bootstrap` with the terminal tool. It returns all discovered registered projects, PM/PL session liveness, registry diagnostics, and the bridge schema. Stop and report its remediation text if it fails.
2. Use `cosw-hostctl status <project>` for one project and `cosw-hostctl fleet-status` for all projects.
3. Use `cosw-hostctl ensure-pm <project>` to start a missing registered PM without attaching this sandbox to its tmux session.
4. To assign a real next action, use:
   `cosw-hostctl dispatch-pm <project> --message 'PM ACTION REQUIRED: register/spawn ...' --handoff /absolute/path --wait-ack 120`
   This ensures the registered PM, appends `pm_action_required` to every registered writable project-bus destination, safely delivers the bounded instruction to the active PM pane, and returns a transport acknowledgement. The PM must publish `pm_action_acknowledged` with the returned `dispatch_id`; report separately whether that semantic acknowledgement was observed.
5. Never invoke raw host `tmux`, manufacture a session name, or write a project bus outside this bridge. Project names, profiles, sessions, event paths, handoffs, and guardrails come only from the project registry.
