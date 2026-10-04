# cidata overlay

Copied into `~/.local/share/hostctl/omarchy/cidata` at `iso build`.
Password hashes stay out of git. Generate one with:

```bash
openssl passwd -6
# then: OMARCHY_ISO_PASSWORD_HASH='...' in ~/.local/share/hostctl/omarchy.env
```
