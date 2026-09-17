# aos-policy

Source-of-truth evaluator for `aos.policy.v1`.

```
aos policy list
aos policy eval --surface catalog.tools --wrapper herm-tui --provider cursor
aos policy filter --surface stream.outbound
aos policy compile --adapter cursor --stdout
aos policy apply
aos policy put --file overlay.yaml
aos policy grant --agent worker --capability policy.write --ttl 2h
```

Install: `just aos-policy`. Tests: `bin/aos-policy/test.sh`.
