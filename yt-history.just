#!/usr/bin/env just --justfile
# yt-history.just — YouTube watch-history archive.
# Import from the main Justfile:  import? 'yt-history.just'
# Every recipe is zsh. Live sync uses Chrome cookies; never writes a cookie file.

YTH := "$(pwd)/bin/yt-history/yt-history"

# Pull new :ythistory metadata + English subs (no video)
yth-sync *FLAGS:
    #!/usr/bin/env zsh
    set -euo pipefail
    {{YTH}} sync {{FLAGS}}

# Download one video as mp4:  just yth-get ID --height 1080
yth-get ID *FLAGS:
    #!/usr/bin/env zsh
    set -euo pipefail
    {{YTH}} get {{ID}} {{FLAGS}}

# Tag an item:  just yth-tag ID krop
yth-tag ID LABEL:
    #!/usr/bin/env zsh
    set -euo pipefail
    {{YTH}} tag {{ID}} {{LABEL}}

# Item count, tag counts, last sync, Drive path
yth-status:
    #!/usr/bin/env zsh
    set -euo pipefail
    {{YTH}} status
