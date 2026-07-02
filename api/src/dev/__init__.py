"""Dev-only tooling. NEVER imported by the running app — no wiring in main.py,
no `if ENVIRONMENT == "dev"` branches in production code. Everything here is a
standalone CLI that calls into the real ingestion/settlement functions from the
outside. See `seed.py`.
"""
