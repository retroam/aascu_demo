# AASCU institutional analytics demo

A place to explore student-success questions, understand the evidence, and share
a useful next step—not another dashboard to learn before you can ask a question.
This prototype draws on discovery conversations with Adams State and Indiana
University regional-campus teams about making PDP data easier to use.

**Synthetic data only.** Results describe mock records, not real students or
institutions. The prototype does not establish institutional approval, predict
real students' outcomes, or prove that an intervention works. Please do not
upload real student data or put confidential information into chat.

## What you can try

- Start with a guided question and explore retention, credit momentum, gateway
  completion, and population differences.
- See definitions, denominators, missing data, and source context alongside results.
- Browse synthetic student histories and try browser-local follow-up notes.
- Ask the assistant questions about the data and inspect its reviewed SQL.
- Explore historical modeling and scenarios with their assumptions made explicit.
- Share evidence as CSV or a printable leadership brief.
- Use the embedded Workbench to load synthetic files and explicitly preview and
  confirm a dashboard-data replacement.

Try “Chart retention across entry cohorts” or “Compare gateway English completion
by cohort.” Historical patterns are starting points for investigation, not live alerts.

## Run locally

First time here? Follow the [setup instructions](docs/technical-guide.md#first-time-setup).
You will need the sibling starter repository, Python dependencies, and Workbench
dependencies; this repository is not a standalone install.

Once setup is complete, run these commands from this repository:

```sh
npm run data:prepare
npm run workbench:build
npm run dev
```

Open **http://localhost:8080**. Keep the server running; opening an HTML file
directly will not provide the app's APIs. Stop the server before preparing data
again: preparation replaces the disposable dashboard database, not the raw sources.
On later visits, just run `npm run dev`; you do not need to rebuild or reset the data.

The assistant needs a provider key. See [assistant configuration](docs/technical-guide.md#connect-the-assistant).
Without a key, the dashboards, modeling, and reports still work; chat explains
that it is not configured. Never commit credentials.

## Check your changes

```sh
npm test
```

The test command uses a disposable baseline, not your active dashboard database.
See [checks](docs/technical-guide.md#checks) for coverage and the separate,
optional paid live-model evaluation.

## Where things live

| Folder | Contents |
| --- | --- |
| `backend/` | Python API, analytics, chat and startup tools |
| `web/` | Browser interface, styles and assets |
| `tests/` | Python and JavaScript tests |
| `population_enrichments/` | Synthetic data generators and examples |
| `docs/`, `evals/`, `.agents/skills/` | Technical details, evaluation cases and agent guidance |

## Go deeper

- [Technical guide](docs/technical-guide.md): setup, data definitions, limitations,
  Workbench behavior, security boundaries, and troubleshooting.
- [Deployment guide](docs/technical-guide.md#deploy-on-digitalocean): the server,
  HTTPS proxy, secrets, and persistent data.
- [Discovery-grounding skill](.agents/skills/grounding-aascu-decisions/SKILL.md):
  how to ground product, analysis, UI, reports, and issue decisions in the calls
  without confusing evidence, ideas, and selected scope.

Raw source data stays unchanged. Exports and demonstrations remain synthetic;
using institutional data would require a separately approved service and controls.
