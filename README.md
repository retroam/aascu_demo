# AASCU institutional analytics demo

Explore student outcomes, check the evidence, and share reports using synthetic
Postsecondary Data Partnership (PDP) data. Discovery calls with Adams State and
Indiana University regional-campus teams guide the demo's design.

**Use synthetic data only.** Keep real student records and confidential information
out of uploads and chat. Institutional use requires separate approval and data
controls. Predictions and claims about intervention effects require validation
with appropriate data.

## What you can try

- Compare retention, credit momentum, and gateway completion across student groups.
- Check definitions, denominators, missing data, and sources alongside results.
- Browse synthetic student histories and save follow-up notes in your browser.
- Ask the assistant about the data and inspect its reviewed SQL.
- Examine historical models and test scenarios with stated assumptions.
- Export evidence as CSV or a printable leadership brief.
- Load synthetic files in Workbench, then preview and confirm which data will
  replace the dashboard's current dataset.

Try “Chart retention across entry cohorts” or “Compare gateway English completion
by cohort.” Results describe historical patterns; current alerts would require
timely data and a reviewed workflow.

## Run locally

Follow the [setup instructions](docs/technical-guide.md#first-time-setup) to install
the sibling starter repository and the Python and Workbench dependencies.

Then run these commands from this repository's root:

```sh
npm run data:prepare
npm run workbench:build
npm run dev
```

Open **http://localhost:8080** and keep the server running. The app's APIs require
the Python server.

On later visits, run `npm run dev`. Stop the server before running `data:prepare`
again: it replaces the dashboard database. Raw source files stay unchanged.

Chat requires a provider key. Follow [assistant configuration](docs/technical-guide.md#connect-the-assistant)
and keep credentials out of Git. Dashboards, modeling, and reports work without a key.

## Check your changes

```sh
npm test
```

Tests use a temporary database and leave your active dashboard data unchanged.
See [checks](docs/technical-guide.md#checks) for test coverage and an optional
live-model evaluation that makes paid provider calls.

## Where things live

| Folder | Contents |
| --- | --- |
| `backend/` | Python API, analytics, chat and startup tools |
| `web/` | Browser interface, styles and assets |
| `tests/` | Python and JavaScript tests |
| `population_enrichments/` | Synthetic data generators and examples |
| `docs/`, `evals/`, `.agents/skills/` | Technical details, evaluation cases and agent guidance |

## Guides

- [Technical guide](docs/technical-guide.md): setup, data definitions, limitations,
  Workbench behavior, security boundaries, and troubleshooting.
- [Deployment guide](docs/technical-guide.md#deploy-on-digitalocean): the server,
  HTTPS proxy, secrets, and persistent data.
- [Discovery-grounding skill](.agents/skills/grounding-aascu-decisions/SKILL.md):
  use the discovery calls to guide features, analysis, reports, and issue decisions.
  Distinguish what participants said from proposed designs and agreed scope.
