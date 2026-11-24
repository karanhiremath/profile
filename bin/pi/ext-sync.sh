#!/bin/bash
# Sourced by bin/pi/install. Copies pi extension files into the agent dir.
# Requires PROFILE_DIR.

# True for the files `harness-sync apply` installs from the profile. A
# machine-local overlay (~/.pi/work-agent/extensions) must not replace them: a
# stale overlay handoff.ts once shadowed the tracked /handoff stack on every
# work-host install. Keep this list in step with bin/atop/harness-sync.
profile_owns_ext() {
    case "$1" in
        handoff.ts|compact-handoff.ts) ;;
        lib/compact-snapshot*.ts|lib/handoff-*.ts|lib/job-bus-project.ts|lib/agent-otel.ts) ;;
        subagent/pi-invocation.ts|subagent/jobs.ts|subagent/job-runner.mjs) ;;
        *) return 1 ;;
    esac
    [ -f "${PROFILE_DIR}/config/pi/extensions/$1" ]
}

# sync_ext_files <src_dir> <dst_dir> [rel_prefix]
# Copy *.ts and *.mjs from src to dst. rel_prefix is the path of src_dir under
# the extensions root ("", "lib/", "subagent/"). Symlinks and byte-identical
# files in dst are left alone (harness-sync owns the symlinked ones). For a
# profile-owned name the profile's file is installed instead of the one in src.
sync_ext_files() {
    local src_dir="$1" dst_dir="$2" rel_prefix="${3:-}" f src dst name owned
    for f in "${src_dir}"/*.ts "${src_dir}"/*.mjs; do
        [ -f "$f" ] || continue
        name="$(basename "$f")"
        src="$f"
        if profile_owns_ext "${rel_prefix}${name}"; then
            owned="${PROFILE_DIR}/config/pi/extensions/${rel_prefix}${name}"
            if ! cmp -s "$f" "$owned"; then
                echo "WARN: ignoring ${f}; the profile owns ${rel_prefix}${name} (config/pi/HANDOFF.md)" >&2
            fi
            src="$owned"
        fi
        dst="${dst_dir}/${name}"
        if [ -L "$dst" ]; then
            continue
        fi
        if [ -f "$dst" ] && cmp -s "$src" "$dst"; then
            continue
        fi
        cp "$src" "$dst"
    done
}
