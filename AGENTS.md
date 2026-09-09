# CAMP - AI Agent Instructions

CAMP is a Flet desktop app that accepts CollectionBuilder metadata and prepares Azure packaging inputs for CB-Digital-Grinnell.

## Scope

- Treat `app.py` as the active runtime source.
- Keep the metadata mapping and packaging behavior deterministic.
- Do not hardcode credentials, API keys, deployment-specific URLs, or secrets.
- Keep status, logs, validation reports, and output locations visible to the user.
- Update `README.md` when the visible workflow changes.

## Change priorities

1. Define and validate the input/output contract.
2. Implement metadata mapping and deterministic package generation.
3. Add Azure integration only after local package generation is reliable.
4. Keep packaging scripts and documentation aligned with runtime behavior.

## Validation

```bash
python3 -m py_compile app.py
bash -n run.sh
```
