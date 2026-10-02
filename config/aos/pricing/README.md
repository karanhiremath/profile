# AOS spend / Cursor token fee

CAI-AOS spend pipeline: classify → partition → price → compose windows → gate.

| File | Role |
|---|---|
| `cursor-token-fee.v1.json` | Grok Fast `$1.45/M`, Grok `$0.68/M`, fee-pct table |
| `together-api.v1.json` | Together API buckets; DeepSeek V4 Flash 0731 `$0.14/$0.28/$0.03` |
| `usage-windows.v1.json` | optional session/weekly caps |
| `cursor_usage_events.py` | Cursor dashboard usage-events CSV parser |
| `../elixir/cai_aos` | BEAM `CaiAos.Spend` |

Dashboard `Kind=Free` / `Cost=Free` is included quota, not $0.

```
aos-spend ingest-cursor-csv --csv <export.csv>
aos-spend ledger
aos-spend eval --model cursor-grok-4.6-xhigh-fast --input 500000 --output 250000 --cache-read 200000
aos-spend eval --model together/deepseek-ai/DeepSeek-V4-Flash-0731 --input 1000000 --output 1000000 --cache-read 1000000
```

Export URL shape (auth cookie, team id via env):

`https://cursor.com/api/dashboard/export-usage-events-csv?teamId=${CURSOR_TEAM_ID:?}&isEnterprise=true&startDate=<ms>&endDate=<ms>&strategy=tokens`
