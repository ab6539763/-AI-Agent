# 05. Closing: Handover & Production Runbook

## 1. Local Execution
```bash
# Run tests
.venv/bin/python -m pytest projects/p04_manufacturing_ops/tests -v

# Start service locally
PYTHONPATH=projects/p04_manufacturing_ops .venv/bin/python projects/p04_manufacturing_ops/main.py
```

## 2. Container Deployment
```bash
cd projects/p04_manufacturing_ops
cp .env.example .env
docker compose up --build -d
```

## 3. Incident Response Runbook
1. **Monitor**: Poll `/metrics` for `pending_hitl_actions > 0`.
2. **Inspect**: Review incident Markdown page under `data/wiki/entities/INC-*.md` and linked `[[SOP-*]]`.
3. **Decide**: Safety officer submits `POST /api/v1/actions/approve` with `approved: true|false`, `safety_officer`, and `reason`.
4. **Audit**: Run `GET /api/v1/wiki/lint` after every SOP revision or equipment onboarding to ensure zero knowledge drift.
