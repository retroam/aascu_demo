# AASCU: Institutional analytics

A local institutional analytics workspace using the shared foundations in `../pdp-datathon-starter/`. The demo keeps its plain HTML/CSS/JavaScript frontend and Python server, with a Playground-style neutral shell. Analytics read a normalized SQLite database; original data files are never modified.

## Run

Install the Workbench dependencies below once. From this directory, prepare the disposable
database and production Workbench build, then start the whole app:

```sh
npm run data:prepare
npm run workbench:build
npm run dev
```

Or, without npm:

```sh
../.venv/bin/python server.py --port 8080
```

Open **http://localhost:8080** and keep the server running. Opening `index.html` directly or using a static server will not provide the APIs. The dashboard has no frontend build; the embedded Workbench uses the sibling Playground production build.

After updating Python code, stop and restart the server with `npm run dev`; a browser refresh only reloads frontend files. In particular, an older running process will not have the new `/api/students` and `/api/student` routes.

### Workbench

Choose **Workbench** in the left sidebar to use the actual Playground UI: upload cohort and
course CSVs, load them, explore students, and browse the field guide. It runs with the main
app locally and on the server. **Synthetic data only**; this is not an institutional data service.

Install the sibling Playground's pinned dependencies once:

```sh
(cd ../pdp-datathon-starter/playground/server_application && uvx --from uv==0.13.0 uv sync --python 3.14.0)
(cd ../pdp-datathon-starter/playground/client_application && npx --yes bun@1.4.3 install --frozen-lockfile)
```

Run `npm run workbench:build` after installation and whenever the Playground UI changes.
Then `npm start` (or `npm run dev`) starts all three services: the main app, production Next
on `127.0.0.1:3100`, and the restricted pipeline/dictionary API on `127.0.0.1:8100`.
Node must meet Playground's Next.js requirements (Node 24 recommended). The main app proxies
`/workbench-ui/` and `/api/workbench-proxy/`, so browsers only contact its own origin.
Do not expose ports 3100 or 8100. No second terminal or separate systemd unit is needed.
Shutdown stops both children; a child failure stops the app so systemd can restart all three.
An occupied private port or missing build fails startup instead of silently sharing another dataset.

Remote access requires HTTPS and `WORKBENCH_ADMIN_TOKEN`, a random secret of at least 32
characters in the server process environment. The sidebar prompts for it; a successful login
sets a one-day Secure, HttpOnly, SameSite=Strict cookie. Rotate the token to revoke sessions.
Direct loopback access needs no login. Public-host requests require authentication even when
Caddy forwards them from loopback. Without the secret, remote Workbench access stays locked.
The credential protects Workbench reads, uploads, preview, and sync; the existing synthetic
dashboard remains public. Requests are capped at 105 MB; the shared API caps each file at 100 MB.

The Workbench database, uploaded files, and exported tables live under `.data/workbench/`.
Uploads never write `.data/pdp.sqlite`, the dashboard database. Staging rows and validation
logs also stay under `.data/workbench/`. Loading new files replaces only Workbench data;
if you leave one file out, the existing Playground behavior uses the mock file for that source.
Upload both files to explore a complete replacement dataset. The embedded page stays mounted
while you use other sidebar pages, so returning preserves its upload and exploration state.
A full browser reload resets the page's progress tracking; the server's load continues.

**Sync to dashboards…** previews the completed Workbench load and the dashboard it will replace.
Confirm that the files are synthetic, then choose **Replace dashboard data**. All normalized
tables are replaced together after validation. A busy load or stale confirmation is refused;
an analysis failure restores the previous dashboard. `.data/pdp.previous.sqlite` keeps the last
dashboard backup after a successful sync. Uploading alone never updates the dashboard.

The page reloads after sync to clear filters, chat, student detail, model, and report state.
Saved views and browser-local follow-ups are scoped by dataset; previous ones are retained but
not attached to the new records. Other tabs detect the change on their next health check.
Metrics, source filenames, checksums, and available cohorts come from the new database.
Modeling requires at least three cohorts and 50 known outcomes with both classes in each split;
otherwise it explicitly reports unavailable. These are synthetic demonstrations, not findings
about real students or institutions.

`npm test` now builds a disposable baseline, so testing never depends on or rewrites your
active dashboard data. `PDP_DEMO_DATABASE` can select a disposable database for a test server.
To restore the full starter data, stop the demo, run `npm run data:prepare`, and restart it.
Keep one main app process per dashboard database: sync coordination is process-local. The
deployment below uses that model. Back up `.data/`; a service restart retains both datasets.

### Connect the assistant

The assistant uses DigitalOcean inference to route PDP questions to read-only SQL, scoped synthetic record browsing, or catalog-grounded explanations. A **different model** reviews SQL before execution and reviews explanations before release. Unrelated general-knowledge questions are declined. Set `DO_MODEL_INFERENCE_KEY` in `demo/.env` or the **server process environment**, then restart the server. `SANDBOX_CHAT_MODEL` selects the generator (default `deepseek-v4-pro`); `SANDBOX_VERIFY_MODEL` selects the verifier (default `qwen3.8-max`). The two model IDs must be from different families, and OpenAI, Anthropic, Fal, and Arcee models are rejected. Keep credentials out of source files, browser storage, and chat. On startup the server loads only the chat key and `SANDBOX_CHAT_MODEL`, `SANDBOX_VERIFY_MODEL`, `SANDBOX_CHAT_MAX_ATTEMPTS`, and `SANDBOX_CHAT_TIMEOUT` from its own `demo/.env`. Existing process variables take precedence. It does not load unrelated credentials or search parent or sibling directories. Values are single-line, optionally quoted; shell commands and variable interpolation are never evaluated.

Without a key, dashboards, filters, modeling, and reports still work, but chat returns an explicit configuration error. There is no silent rule-based fallback. A configured key is not proof that the provider is reachable or the account has credit.

Only the user's question, bounded query context, schema and allowed values, analysis definitions, proposed SQL, validation feedback, and selected filters go to the provider. Student records and calculated result tables stay local. Questions themselves may contain sensitive information: do not enter real student identifiers or confidential information. This prototype is for synthetic data only.

The workspace environment already has the needed Python packages. On a fresh environment, install `requirements.txt` into `../.venv` (for example, `uv pip install --python ../.venv/bin/python -r requirements.txt`). Keep the sibling starter checkout in place: helpers and metadata are imported from it rather than copied.

`npm run data:prepare` invokes the shared loader and replaces only the demo's disposable `.data/pdp.sqlite` and `.data/tables/`. The loader also creates new ignored staging and audit-log directories in the starter. It does not replace the starter's default database. Stop the demo before rebuilding, then restart it to clear cached data and metadata. Rebuild after changing source files or shared mappings. The server never runs the loader from an HTTP request and opens the database read-only.

## Deploy on DigitalOcean

The public site is this same Python server, bound to loopback, behind Caddy. Allow additional
memory for the Workbench's Node process and CSV normalization; size the server against your
synthetic uploads rather than assuming the dashboard-only footprint. Prepare `.data/pdp.sqlite`
once and install/build Workbench on the target platform before starting the systemd unit.

The droplet layout mirrors this checkout. `demo/` and `pdp-datathon-starter/` stay siblings:

```text
/opt/aascu/demo/                          # this directory, including .data/pdp.sqlite
/opt/aascu/.venv/                         # Python 3.13
/opt/aascu/pdp-datathon-starter/measures/
/opt/aascu/pdp-datathon-starter/gap_finder/
/opt/aascu/pdp-datathon-starter/normalized-data-model/{src,pdp_model,config}
/opt/aascu/pdp-datathon-starter/normalized-data-model/{README.md,normalized-data-model.mmd}
/opt/aascu/pdp-datathon-starter/mcp/pdp_mcp/
/opt/aascu/pdp-datathon-starter/data/dictionaries/column_lookup.csv
/opt/aascu/pdp-datathon-starter/data/raw/pdp_cohort_data.csv
/opt/aascu/pdp-datathon-starter/data/raw/pdp_course_data.csv
/opt/aascu/pdp-datathon-starter/data/quality/findings.csv
/opt/aascu/pdp-datathon-starter/playground/client_application/  # source, installed dependencies, .next/demo build
/opt/aascu/pdp-datathon-starter/playground/server_application/  # source and its Python 3.14 environment
```

Create a sudo user (these steps use `aascu`), add your SSH public key, and install Caddy from the [official stable repository](https://caddyserver.com/docs/install#debian-ubuntu-raspbian). Install `uv`, then Python 3.13 and the demo packages:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.13
uv venv --python 3.13 /opt/aascu/.venv
uv pip install --python /opt/aascu/.venv/bin/python -r /opt/aascu/demo/requirements.txt
```

Install Node 24 on the server, then run the pinned Workbench installation commands above and
`npm run workbench:build` from `/opt/aascu/demo`. Keep the complete sibling starter source;
do not copy macOS `node_modules` or virtual environments to Linux.

On the server, `/opt/aascu/demo/.env` holds the app settings below. Mode `600`, owned by `aascu`.
Do not commit it or copy `DO_ACCESS_TOKEN` there. Generate the Workbench secret with
`openssl rand -hex 32` and put it in the environment file, not source control.

```sh
DO_MODEL_INFERENCE_KEY=doo_v1_...
SANDBOX_CHAT_MODEL=deepseek-v4-pro
SANDBOX_VERIFY_MODEL=qwen3.8-max
SANDBOX_PUBLIC_HOST=aascu.203-0-113-10.sslip.io
WORKBENCH_ADMIN_TOKEN=<replace-with-generated-secret>
```

`SANDBOX_PUBLIC_HOST` is the hostname browsers send. The server rejects every other public `Host` header. Replace the example address with the droplet's public IPv4, dots changed to dashes. `sslip.io` resolves that name to the address, so no DNS account is required. systemd's `EnvironmentFile` loads this file, including `SANDBOX_PUBLIC_HOST` and `WORKBENCH_ADMIN_TOKEN`. The app's own `.env` loader imports only chat settings, so a hand-started process must export both hosting variables.

`/etc/systemd/system/aascu-demo.service`:

```ini
[Unit]
Description=AASCU institutional analytics demo
After=network.target

[Service]
WorkingDirectory=/opt/aascu/demo
EnvironmentFile=/opt/aascu/demo/.env
ExecStart=/opt/aascu/.venv/bin/python server.py --host 127.0.0.1 --port 8080
Restart=on-failure
RestartSec=3
User=aascu
Group=aascu
TimeoutStartSec=180

[Install]
WantedBy=multi-user.target
```

`/etc/caddy/Caddyfile`, with the same hostname:

```caddy
aascu.203-0-113-10.sslip.io {
    reverse_proxy 127.0.0.1:8080
}
```

Enable both, then check health. Caddy obtains the certificate once the hostname points at the droplet.

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now aascu-demo
sudo systemctl reload caddy || sudo systemctl restart caddy
curl -fsS https://aascu.203-0-113-10.sslip.io/api/health
```

A healthy chat block has `"configured": true`, `"provider": "digitalocean"`, and the two model IDs. Open the `https://` hostname in a browser. The process itself is not reachable from the network.

To publish a later copy, preserve the server's `.env` and entire `.data/` directory. Sync app
and sibling starter source, install dependencies and rebuild Workbench on Linux when changed,
then restart. Do not replace uploaded or synced server data with your local demo database:

```sh
rsync -az --delete \
  --exclude '__pycache__/' \
  --exclude '.data/' \
  --exclude '.env' \
  --exclude 'artifacts/' \
  demo/ aascu@203.0.113.10:/opt/aascu/demo/
sudo systemctl restart aascu-demo
```

Repeat that `rsync` for the starter directories and files listed above when those change, including the metadata reader, schema README, ER diagram, and column lookup. The metadata reader needs every mapping named in `config/pipeline.yaml`. Confirm `https://…/api/health` returns 200 after the restart.

## What works

- **Guided review:** a plain-language finding, interpretation, and next step lead into population comparisons and historical student records. Filters remain visible; changing the population to enable a comparison is explicit.
- **Synthetic student records:** the Students page provides a bounded, searchable roster and profiles with available cohort, credit, gateway, and course history. Observed indicators are not current alerts or individual model predictions. The assistant can also return explicitly requested synthetic rows, including student IDs, within the active UI scope. Aggregate queries retain distinct-student support checks.
- **Demonstration follow-up:** a profile can record a responsible team, next step, status, and review result in this browser's local storage. No message is sent, no institutional task is assigned, and no intervention effect is measured. These demo records are not included in aggregate exports and are not shared across browsers.
- **Evidence overview:** cohort and population filters; 24/30-credit momentum; retention, documented gateway math completion, persistence elsewhere; cohort charts; subgroup comparisons; definitions, denominators, missingness, and confidence intervals.
- **Playground-style shell:** floating collapsible navigation, light/dark themes, and an assistant available on every page. On wide screens it docks and resizes; on smaller screens it overlays the page. Toggle navigation with Cmd/Ctrl+B and the assistant with Cmd/Ctrl+J.
- **Additional shared measures:** English gateway completion, average credit completion ratio, and course DFW rate. Chat can display these measures; saved dashboards and evidence exports retain their four-metric contract. Units and limitations are displayed with each result.
- **Equity gaps:** shared `find_gaps` results, selected cohort/population, one-way and selected two-way breakdowns, group-versus-everyone-else intervals, q-values and noise flags. First-generation breakdowns remain unavailable because their codes are unresolved.
- **Verified SQL exploration:** generate new aggregations, formulas, filters, and groupings rather than selecting from fixed answer templates. Schema/domain checks run first; a different model then reviews the question, SQL, and display specification. Rejected proposals can be revised within a bounded loop. Only the approved, validated query executes; the server builds result tables and charts from its output. Turn on **Analysis details** in chat to inspect SQL, model names, references, and check history; it is off by default. Two-model approval is not proof of semantic correctness.
- **Saved dashboards:** existing saved views retain their four-core-metric contract and browser-local storage. Exports preserve their chosen metrics and filters. Flexible SQL charts live in chat and are not silently converted into that narrower saved-dashboard format.
- **Modeling studio:** actual regularized logistic regression, chronological train/validation/test split, repeated-student exclusion, train-only imputation, AUC, Brier, calibration, support bands, and inspectable coefficients.
- **Scenario planning:** budget- and capacity-constrained outreach arithmetic using explicit assumed cost and retention lift. The data does not estimate intervention efficacy. Changed inputs keep the previous result marked stale until the scenario is rerun.
- **Trend explorer:** adjacent-cohort changes and intervals; raw versus stratified adjusted enrollment-intensity associations; overlap diagnostics; hypothesized causal graph; an evaluation checklist. No causal effect is claimed.
- **Reports:** selected evidence CSV and printable HTML leadership brief; model/scenario and trend investigation briefs. Export opens a report preview. Choose **Download HTML**, **Download CSV**, or **Print / Save as PDF**. The app checks the response before offering a file and displays a retry action when an export fails. No binary PDF engine is required.
- **Data & definitions:** source counts and SHA-256 checksums, shared column dictionary, normalized load timestamp, filtered quality indicators, and the published dataset-wide quality inventory. Published raw-file issues are not presented as remaining normalized-data errors.

### Chart exports and evidence

Reviewed SQL charts have **Export CSV**, **Print / PDF**, and **Where this came from** controls, including when Analysis details is off. Exports contain the displayed points (at most 24), units, the original response scope, exact SQL, model identities and source references. Suppressed numeric fields remain unavailable; CSV text is escaped and formula-prefixed strings are neutralized. Printable HTML includes its own chart styles and exact-value table; use the existing print action to save a PDF. This is not a PNG/SVG image-export feature.

The evidence view explains scoped views → custom SQL → plotted values. It distinguishes credit-threshold context from enforced cohort/population filters and discloses result/chart truncation and withheld groups. It is not a complete lineage audit: SQL hashes are not source-data hashes, and no execution-time data fingerprint is attached to these responses. Old responses lacking completeness metadata say it was not captured. No current dashboard metadata is substituted for an older answer.

These interactions adapt ideas from `codebenders-datathon` without importing its React/Postgres stack. Forecasting remains separate: the current retention field is year-two retention, not a four-year outcome. A validated projection requires outcome-specific coverage dates, point-in-time predictors and mature temporal holdouts. The mock credit cutoff does not establish retention or credential follow-up; no forecast line is generated from it.

## Starter resources reused

The app already loaded the database described by [`normalized-data-model.mmd`](../pdp-datathon-starter/normalized-data-model/normalized-data-model.mmd). The Mermaid file is the ER diagram, not executable database configuration: [`destination_schema.yaml`](../pdp-datathon-starter/normalized-data-model/config/destination_schema.yaml) owns the types, keys and rules. The starter tests keep them aligned. **Data & definitions** now exposes all ten tables, composite relationships, the original diagram source and the full field dictionary. Chat receives the same metadata, with definitions clearly separated from query permissions.

| Resource | Use in this app |
| --- | --- |
| `normalized-data-model/pdp_model` | Existing public loader, normalized database, dictionary and field API; no copied ETL. |
| `config/pipeline.yaml`, mappings, fixer and validator | Existing data preparation applies normalization/corrections and records provenance. |
| `config/destination_schema.yaml`, `value_sets.yaml` | Stored types, nullability, valid codes and rules. SQL catalog includes original rules; two-sided error ranges feed numeric checks. Conditional and warning rules remain descriptive, not blanket predicate prohibitions. |
| `mcp/pdp_mcp/metadata.py` | **New direct reuse** of table descriptions, keys, relationships, source-column lineage, schema rules and source fingerprints. No MCP server or additional framework needed. |
| `normalized-data-model.mmd` and model README | Exact ER source and schema explorer; table grains come from the shared metadata reader. |
| `config/column_dictionary.yaml`, `data/dictionaries/column_lookup.csv` | Full-model definitions and mappings, including course/enrichment fields rather than only student/cohort fields. |
| `student_attribute` and housing enrichment | **New scoped `attribute_records` view** for housing counts and synthetic examples. It preserves optional term metadata; absence is not false. Cohort outcomes are deliberately excluded to avoid weighting them by attribute rows. |
| `term` and `course` | **Expanded `course_records`** includes academic year, academic term, term order and course number. Course joins still use student + cohort. |
| `measures/run_measures.py` and calculations | Existing retention, persistence, math/English gateway, credit-completion and DFW calculations. Canonical semantics also guide SQL review. |
| `gap_finder/find_gaps.py` | Existing group/complement comparisons, intervals, q-values and ranking. Use real calculations, not the sample stub. |
| `data/quality/findings.csv`, `run_checks.py`, `data_fixes.yaml` | Published issue inventory, independent raw-data checks and existing loader corrections. Raw issues are not labeled as remaining normalized errors. |
| `data/manifest.json`, `data_provider`, `load_run` | Source checksums and load provenance; original files remain unchanged. |
| Sample inputs/outputs and foundation tests | Fixtures/reference contracts; do not substitute unvalidated sample output for the loaded dataset. |

Resources reviewed but **not blindly imported**: Playground's Next.js/FastAPI components require a different application stack; its SQL helper is weaker than the current guard. MCP's aggregate query mode is not exposed upstream. Notebook plotting targets Matplotlib rather than this browser UI. Metadata Advisor guidance is useful for join/eligibility cautions but is not a canonical measure implementation and uses a lower suppression threshold. Registration holds has only an unverified source spec/sample and no loader integration; financial-aid data is absent. Institution events remain documented contextual data, not evidence of intervention effects. These are candidates for deliberate follow-up, not working features claimed here.

## Try these questions

```text
Chart retention across entry cohorts
Compare mean year-one earned credits by enrollment intensity
Show retention by race and gender for Pell recipients
Compare gateway English completion by cohort
How many records have unknown first-generation status?
Show average credits attempted and earned by cohort
Count distinct students with recorded on-campus housing by academic year
Show course attempts by academic year and academic term
How do course enrollments join to cohort membership?
```

The active UI cohort/population is enforced in trusted database views, not left to a model instruction. SQL can narrow that scope further; change the UI filters to broaden it. Available entry cohorts come from the active normalized dataset. The schema catalog supplies actual column names, types, and categorical codes. Custom averages, formulas, and combinations of available dimensions are allowed. Unknown columns, impossible categorical values, incompatible literals, and prohibited operations are rejected with feedback for another generation attempt. The assistant retains bounded prior-query context, not an unrestricted transcript. Manual filter changes reset it.

The SQL language supports either one nonaggregate `SELECT` for explicitly requested synthetic rows (up to 200 rows and 16 named columns), or one aggregate `SELECT` over a prejoined `cohort_records`, `course_records`, or `attribute_records` view, including expressions, `CASE`, filters, grouping, `HAVING`, and ordering. It does not support arbitrary joins, CTEs, subqueries, window functions, or writes. These are SQL validation limits, not a fixed metric menu. Preset model evaluation, outreach scenarios, and statistical gap intervals remain available in their dedicated pages; generated SQL must not invent model predictions, causal effects, or uncomputed statistical intervals.

## Data definitions and limitations

The cohort grain is student × entry cohort: **10,313 records and 10,311 distinct student IDs**. The course source contains **100,951 records**; the shared DFW measure uses classified course enrollments. Course/cohort joins use both normalized `student_id` and `cohort`.

- Retention is the supplied year-two cohort-institution flag, including qualifying credentials.
- Persistence means enrollment or qualifying credentials **elsewhere** by year two; it is not an overall persistence rate and is not added to retention.
- Momentum excludes missing year-one earned credits; zero is a valid value.
- Gateway math now follows the shared measure: known C/D outcomes excluding students marked not required. Its full-dataset denominator is **4,407**, not the old all-required denominator of 4,452. The 2,382 exclusions include unknown requirement/outcome values, not just the 45 required students without outcomes. Definitions and exports disclose this change.
- Preset metric rates below 20 eligible records are suppressed. Aggregate SQL additionally requires a real distinct-student support count and suppresses groups below 20; that population count does not establish eligibility for every custom metric. This is not a comprehensive privacy system.
- Shared foundations hide groups below 10; the demo additionally hides below 20. Gap results check both the group and its complement. DFW suppression uses distinct students, not enrollment counts.
- Credit completion is the average of individual earned/attempted ratios, not 24/30-credit momentum. The shared measure caps ratios above 1. DFW currently uses numeric grades below 2.0; that cutoff is still an open shared-definition decision.
- The loader applies shared normalization and corrections. Student-level demographics come from the shared `student` table, whose latest-cohort values win when a student has multiple entry records.
- The source contains no institution identifier, financial-aid file, intervention assignments, support exposure, or verified extraction timestamp. Follow-up completeness is not established.

The model trains on 2021–22/2022–23, selects regularization on 2023–24, and evaluates on 2024–25. It uses entry characteristics and first-term GPA, excluding later outcomes. Its roughly 0.702 held-out AUC coexists with substantial calibration drift (predicted retention exceeds recorded retention by roughly 14.1 percentage points). It is **not ready for real student decisions**.

Adjusted associations standardize over shared entry-cohort × age-band × entry-type strata, with seeded bootstrap intervals and explicit overlap requirements. Adjustment does not resolve unmeasured confounding, differing follow-up, or the lack of intervention records. Raw and adjusted populations differ when strata lack overlap.

All results describe **synthetic data, not real students or institutions**. This is a local prototype without institutional authentication, authorization, live ingestion, scheduled alerts, or a production audit store.

## Checks

```sh
npm test
# equivalent:
../.venv/bin/python -m unittest discover -p 'test_*.py' -v
node --test test_*.mjs
node --check app.js
```

Tests cover independent CSV ground truth, missingness and denominators, low-cell suppression, SQL schema/value/safety checks, two-model orchestration and revision, chart rendering, selected-metric exports, model leakage, feature timing, score calculations, and adjusted-association overlap. Older parser tests cover the retained legacy analytical helper, not the live LLM's interpretation quality.

After configuring a real key and starting the server, run `npm run eval:llm -- --runs 3` for a small live interpretation evaluation. Each repetition asks eight questions, with up to six paid model calls per question: retention, selected-scope retention, gateway English, mean credits, a grouped follow-up, gender groups, an injection attempt, and an unsupported causal request. It reports per-case outcomes and latency; any failed check exits nonzero. The fixed expected fractions are independent synthetic-data reference values. Re-run before changing either provider model or prompt. This sample is not a general accuracy or safety certification.

## Files

- `students.py`, `students.js`, `students.css`: scoped synthetic rosters and profiles, historical academic observations, and browser-local demonstration follow-up.
- `test_students.py`, `test_students.mjs`: scoped record retrieval and HTTP dispatch, asynchronous UI state, escaping, follow-up storage, and keyboard focus checks.
- `review.css`: guided review and plain-language analysis presentation.
- `server.py`: standard-library HTTP server and validated API endpoints; listens on loopback by default.
- `analytics.py`: source loading, shared metrics, legacy constrained parser, signals, and evidence reports.
- `foundations.py`: normalized-model projection, shared measures, gap finder, dictionary and quality integration.
- `prepare_data.py`: explicit local database preparation with the shared loader.
- `modeling.py`: historical logistic model, model evaluation, scenario calculations, adjusted associations.
- `llm_chat.py`: SQL generation, independent model verification, bounded revision, and result-to-chart mapping.
- `sql_guard.py`: scoped analytical views, schema/domain validation, and restricted SQLite execution.
- `chat_charts.js`: escaped declarative chart rendering and exact-value tables.
- `evaluate_llm.py`: opt-in paid live-provider interpretation checks, separate from mocked regression tests.
- `app.js`, `index.html`, `styles.css`, `secondary.css`, `playground.css`: interface, local saved views, charts, report rendering, and Playground theme/layout tokens.
- `test_evidence.py`, `test_chat.py`, `test_llm_chat.py`, `test_modeling.py`, `test_transport.mjs`, `test_chat_charts.mjs`: data, conversation, provider-boundary, chart, model, and request checks.
- `transport.js`: request timeouts, response validation, and report download validation.
- `PLAN.md`: discovery-informed scope and acceptance criteria.

### Hallucination and injection boundaries

- Provider output is untrusted: validate exact JSON fields and bounds, then parse the complete SQL AST against allowed views, columns, values, expressions, and functions.
- Query proposals can be revised after guardrail/verifier failures, but a changed query never inherits approval. Each revision passes all checks again; exhaustion fails closed.
- The independent verifier sees the question, schema, active scope, exact SQL, and display references—not the generator's rationale. It cannot authorize writes or bypass code-level checks.
- SQL execution uses a dedicated read-only connection, authorizer, query/time/size limits, and support checks. Models have no filesystem, browser, extension-loading, or arbitrary Python/JavaScript tool.
- Chart points and displayed result cells come from the executed SQL, never from model-supplied numbers or chart code. Missing results are not zero. A query can still calculate the wrong thing; inspect definitions, SQL, and scope.
- Group suppression does not stop inference across overlapping queries or guarantee adequate support for every conditional aggregate. Real institutional data requires additional disclosure controls and authorization.
- Provider refusals, malformed proposals, invalid SQL, rejected verification, and exhausted revisions do not become successful analytical answers. Mocked tests cannot establish live-model accuracy; two models can share the same mistake.
- There is no institutional authentication, rate limiting, or comprehensive privacy guarantee. Keep the default loopback binding; do not expose this development server to a network.

## Connection errors

The app checks the server connection while the page is open. If it stops, the page labels the connection loss and keeps the last displayed results. Start the server again, then select **Reconnect**. Failed chat requests offer **Retry question**. Report failures offer **Retry export** and do not report a successful download.

PDP schema, field/feature definitions, categorical codes, measure semantics and analysis-planning questions use the live catalog. Explanation references must resolve to catalog entries, and a separate model must approve the proposed text. These explanations do not invent numerical findings. Off-topic requests receive a PDP-only redirect. Row browsing is for this synthetic demo; connecting real institutional data requires a separate authorization policy.

Schema replies retain validated catalog references for follow-ups such as “What are some example rows from them?” A sample request can return up to five illustrative rows from each of the two scoped views, with representative columns. The server builds and validates each read-only query, a separate model reviews the whole request, and the UI renders labeled tables alongside Markdown and charts. Client context never supplies result rows or approval.


Chat caching is process-local and bounded: checked full responses (128 entries, 5 minutes), successful structured planning/review steps (256 entries, 30 minutes), read-only SQL results (128 entries, 5 minutes), and metric semantics (8 entries, 30 minutes). Each cache has an 8 MB payload budget; values are copied on read. Errors and unchecked answers are never cached. Identical simultaneous chat requests share work. Keys include question/context, filters, model settings, credential fingerprint, database/WAL revision and relevant policy/definition revisions; SQL keys also distinguish records from aggregates. SQL safety validation still runs before SQL-result cache lookup. Restart clears all caches; no chat caches are persisted to disk. Browser static assets use ETags with revalidation; API responses remain `no-store`. Analysis details identifies reused responses/planning steps. These caches accelerate repeats, not novel two-model requests.

The chat catalog supplies the current date and actual observed entry-cohort coverage. Five-year enrollment requests must distinguish unique students represented in entry cohorts from annual enrollment snapshots and clarify unavailable periods. The live eval includes this coverage question and reports cache metadata with request timings.

**Concise responses** defaults on and controls future model-generated explanations and clarifications: direct answers in everyday language for nontechnical institutional stakeholders, typically 2–4 sentences or up to three short bullets. Necessary coverage and uncertainty caveats remain. Turning it off asks for fuller explanations, not more jargon. This is independent of Analysis details; charts and result tables remain visible. The `concise` API boolean defaults to true and is part of the response/plan cache configuration.

The Student success trend summary and guided actions are collapsed under **Start with a question**, leaving the chart uncluttered. **Quick tour** in the top bar opens a seven-step walkthrough with Back, Next, Finish and close controls. Escape dismisses the tour. It covers filters, guided questions, student records, comparisons, definitions, chat and reports; `artifacts/quick-tour.gif` is the recorded walkthrough.
