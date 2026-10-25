# Workflow safety limits

Active values for the demo workspace and the hard caps in `safety/limits.py`. The chair can change a value in Analytics & Safety; it is clamped to [minimum, hard cap], audited, and logged as a security event.

| Limit | Active | Minimum | Hard cap |
|---|---|---|---|
| Spending limit per workflow (USD) | $0.50 | $0.01 | $2.00 |
| Daily AI spending limit (USD) | $5.00 | $0.05 | $20.00 |
| Model calls per workflow | 20 | 1 | 40 |
| Orchestrator steps (handoffs) per workflow | 16 | 2 | 20 |
| Tool calls per workflow | 120 | 5 | 200 |
| Retries per model step | 2 | 0 | 3 |
| Output tokens per model call | 12,000 | 500 | 16,000 |
| Workflow duration (seconds) | 480 | 30 | 900 |
| Revision rounds per plan | 1 | 0 | 2 |
| Web searches per workflow | 4 | 0 | 10 |
| Page fetches per workflow | 10 | 0 | 25 |
