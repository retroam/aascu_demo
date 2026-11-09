# AASCU demo

Build a local institutional decision workspace using the shared PDP foundations. Keep application code in `demo`; use the workspace Python environment and local Inter font assets. Never modify shared source data. Required Python dependencies are pinned in `requirements.txt`.

## Playground redesign and shared backend

Keep the framework-free frontend and Python server. Use Playground's white/gray surfaces, near-black controls, Inter type, floating navigation, compact header, and docked/overlay assistant. Keep blue/teal analytical charts and amber cautions. Themes cover every existing page; no new frontend framework is required.

Load a disposable demo SQLite database with `pdp_model.run_load`, then read it for dashboard, model and trend inputs. Use shared measures for retention, persistence and gateway completion, preserving 24/30-credit momentum and the stricter 20-record display threshold. Expose remaining shared measures separately and use `find_gaps` for group-versus-complement comparisons. Definitions and published quality findings come from the starter.

Validate with independent CSV expectations, 19/20-record suppression boundaries on both sides of a gap, filtered course metrics, the existing chat/model/export tests, and browser checks across desktop, dark theme and mobile. Explicitly disclose the gateway denominator migration and dataset-wide scope of published quality findings.

## Product flow

1. Evidence: all-student metrics, cohort and population filters, 24/30-credit momentum, transparent denominators, and a constrained evidence assistant.
2. Modeling: a genuine retrospective retention model with a later-cohort holdout, calibration and baseline comparison; budget/capacity scenarios with explicit assumed benefits.
3. Trends: cohort changes and subgroup comparisons, raw versus adjusted associations, uncertainty and causal identification limitations.
4. Reports: downloadable leadership brief and aggregate CSV with definitions, active filters, provenance and limitations.

Discovery priorities: reduce the burden on small IR teams; count all student populations; agree on metric definitions; connect a signal to a concrete next step; let institution leaders share an understandable report.

## Grounded LLM and chat charts

The generator produces flexible aggregate SQL, not a fixed operation enum. Code validates the schema, categorical values, types, supported AST, and safety rules. A different model independently verifies the exact proposal before execution. Rejected proposals can be revised up to a bounded attempt limit; every revision must pass again. Read-only scoped views enforce UI filters and correct source joins. The local server renders actual result cells and chart values, not model-invented evidence. Ordinary dashboard/report endpoints remain deterministic and independent of provider availability.

Verification cases: known retention and English results; a novel average and multi-dimension grouping; active-scope enforcement; wrong column/value rejection and successful revision; independent verifier rejection and revision; exhausted retries without execution; prohibited SQL and identifier output; suppression, resource limits, provider failures, and same-model configuration rejection; charts, dynamic result tables, and visible SQL/check history across desktop, dark theme, and mobile. Keep the saved-dashboard four-metric schema unchanged. Separate scripted-provider integration checks from live-model interpretation evaluations, which require a configured key.

Use independent Claude CLI and Codex reviews after implementation and initial verification. Assess findings against the code, fix concrete defects, and rerun affected checks. Do not claim model interpretation is hallucination-free merely because its output matches a schema.

## Acceptance checks

- Source cohort rows = 10,313; distinct student IDs = 10,311; course rows = 100,951.
- Rates use explicit eligible denominators and handle missing numeric markers without treating them as zero.
- Preset dashboard/report calculations retain their shared measures. Generated SQL is checked against the same metric definitions but can express new analyses. Unsupported questions must not silently substitute a different analysis; model review is not a guarantee of understanding.
- Model evaluation is chronological, excludes overlapping students, and excludes later outcomes from predictors.
- Scenarios never imply a learned treatment effect. Adjusted associations never claim proven causation.
- Every route works, filters update the evidence, chat returns citations, downloads contain the chosen scope, and the interface works on mobile and desktop.
- Run Python unit tests and a browser walkthrough; inspect screenshots and console errors.

All displayed findings describe synthetic data, not actual students or institutions.

## Embedded Workbench

Reuse the actual Playground frontend and pipeline/dictionary routes, not copies of their UI.
Add Workbench to the left navigation with a full-height iframe, the existing Inter/neutral
styles, a separate-data notice, and an actionable unavailable state. Run the frontend on
loopback port 3100 and the restricted API on 8100. Store uploads, tables, and its SQLite
database beneath `demo/.data/workbench`; never point it at the dashboard database.

Checks: upload both sample CSVs, load them, browse students and the field guide, and verify
the dashboard database fingerprint stays unchanged. Exercise unavailable, desktop, and mobile
states. Run the demo tests. Request Claude CLI advice after implementation, apply concrete
fixes, then request Codex at its highest reasoning effort for the final review.

Claude Opus 5.5 reviewed the sync design. Validate a SQLite backup, confirm both run IDs,
then replace every dashboard table atomically while holding an exclusive dataset lock.
Keep a previous-file backup and restore it if analysis fails. Reader locks cover complete
API responses, including chat. Clear all data-dependent caches. Derive cohorts and provenance
from the new database, with explicit unavailable modeling for inadequate chronological splits.
Require an authenticated same-origin request and synthetic-data attestation. Reload the client after
sync; namespace browser follow-ups and saved views by dataset instead of deleting them.
Run tests on disposable baseline data, and test stale confirmations, invalid schemas, busy
readers, rollback, arbitrary cohorts, CSRF rejection, and browser sync end to end.

Server deployment: build the same Playground UI with `/workbench-ui` as its base path and a
relative API URL. The main app starts production Next and the restricted API on private ports,
proxies both under its own origin, and closes them on shutdown. Fail startup on missing build
or occupied ports; stop on child failure for systemd restart. Gate remote Workbench access with
a high-entropy admin credential and signed Secure/HttpOnly session; retain loopback convenience.
Checks: a single main-app command starts all services; browser upload, exploration and sync use
only that origin; remote unauthenticated and cross-origin writes fail; SIGTERM closes both
children. Preserve live dashboard data during tests and keep `.data/` out of deployment rsync.
