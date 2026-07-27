# api/

The FastAPI service. Everything about running, seeding, testing and deploying it lives in the
[repo root README](../README.md); module layout and conventions are described there too.

Quick reference from this directory:

```bash
.venv/bin/mypy --config-file mypy.ini    # CI gate
.venv/bin/pytest -q                      # CI gate
```
