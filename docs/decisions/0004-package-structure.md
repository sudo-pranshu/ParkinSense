# ADR-0004 — One `parkinsense` package; dead code removed

**Status:** Accepted · **Date:** 2026-10-31

## Problem

Live Python code lived under `dashboard/python/` next to ~25 abandoned modules (three BLE
receivers, tremor detectors v2–v4, two fusion engines, ML placeholders, a backup runtime,
empty `replay_v2.py`/`build_dataset.py`). The README described several of them as live.
Nothing marked which implementation was authoritative.

## Decision

A single importable package `parkinsense/` (`pip install -e .`), one module per live
responsibility (see `docs/architecture/ARCHITECTURE.md`). The brief suggested a top-level
`python/` directory; a package named `python` shadows nothing in practice but is a poor import
name, so the package carries the project name instead. Modules were moved with `git mv` so
`git log --follow` still works.

Removal criterion: a module was deleted only if an import-graph search found no importer other
than other dead modules or print-script "tests". Everything removed remains in history at
commit `cc7b9df` (path `dashboard/python/...`).

## Compatibility

`python dashboard/python/runtime/runtime_v2.py` no longer exists; the replacement is
`python -m parkinsense.runtime.app` (or `parkinsense-live`). The `/metrics` endpoint, port,
JSON filename and its keys are preserved (keys only added), so the mobile app and dashboard
need no change.
