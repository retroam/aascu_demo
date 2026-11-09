# Population enrichments

Four synthetic enrichment files for the normalized data model in
[`pdp-datathon-starter/normalized-data-model`](../../pdp-datathon-starter/normalized-data-model/README.md).
Each one models a student population or signal that institutions described in discovery calls
(Adams State University and IU regional campuses). Each loads into `student_attribute` through
the model's enrichment pipeline.

**The data is synthetic, and every relationship in it was planted by these scripts.** None is a
finding about real students. The parameters are below, in each module's docstring, and in each
row's `Source` (`synthetic: population_enrichments/<script>.py, seed 2026, planted effects`).

Unlike the starter's on-campus housing generator, which picks students uniformly at random, these
generators condition on cohort- and course-file columns, so the data shows plausible relationships.

## What's here

| File | What it is |
|---|---|
| `student_athlete.py` | One row per student and key: `is_student_athlete` (`true`/`false`) for everyone, `athlete_sport` for athletes. |
| `registration_holds.py` | One row per hold, per student and enrolled term: `registration_hold` = the hold type. |
| `lms_activity_band.py` | One row per student per enrolled term: `lms_activity_band` = `low`, `medium` or `high`. |
| `instruction_site.py` | One row per student: `instruction_site` = `on_campus`, `online` or `cdoc_facility`. |
| `_common.py` | Shared reading of the raw files, term order and writing. |
| `data/*.csv` | The generated files, seed 2026. |
| `config/*_mapping.yaml` | One mapping config per file, in the model's format. |
| `config/destination_schema_rules.yaml` | The `enum` rules for the five new keys, to add under `student_attribute.attribute_value.rules` in the model's `config/destination_schema.yaml`. |
| `config/pipeline_populations.yaml` | The model's `config/pipeline.yaml` plus the four files, with its own database (`output/pdp_populations.sqlite`) and table files (`output/tables_populations`). The model's default pipeline is unchanged, so other squads' loads aren't affected. |
| `test_*.py` | One test file per generator. |

An "enrolled term" is a term in which the student has course-file rows with a non-blank
`Academic_Year` and `Academic_Term`. That includes terms where the student was only enrolled at
another institution (rows with a blank `Grade`).

## Planted effects

Defaults; each is a function argument and a CLI flag.

- **Student athletes.** Logistic model with the intercept solved for a 45% share (`--share`):
  +0.6 log-odds for First-Time Full-Time, +0.5 for `20 and younger`, -0.8 for `Older than 24`,
  +0.2 for `Retention` = 1. Younger, full-time students already retain better in the mock data, so
  most of the gap comes from that skew. Sports: football and wrestling for `Gender` = M only.
  Coach change: in the 2023-24 cohort, football's weight is tripled for non-retained students
  (`--coach-change-cohort`, `--coach-change-factor`). `Retention` is the ARF's year-2 measure, the
  closest the mock data has to fall-to-spring retention.
- **Registration holds.** Each hold type is drawn on its own each enrolled term, so a student can
  have several in one term. Base rates: financial 0.06, advising 0.05, sap 0.03, immunization
  0.015, disciplinary 0.005. Financial holds x2.0 for `Pell_Status_First_Year` = Y
  (`--pell-factor`). Every type x1.6 in a term with no course rows by the next fall or spring term
  (`--not-enrolled-factor`); not applied when that term is past the end of the course file.
  `Hold_Status`, `Placed_Date` and `Resolved_Date` are made up with no planted effect.
- **LMS activity band.** `score = gauss(0, 1) - 1.5 * (dfw_share - 0.25)`; below -0.6 is low, above
  0.6 high (`--dfw-weight`, `--low-cut`, `--high-cut`). `dfw_share` is that term's share of
  gradeable courses (a number 0-4, P, F, W, UW) graded below 2.0, F, W or UW. With no gradeable
  course the share is unknown and the score isn't shifted.
- **Instruction site.** `cdoc_facility` first, by age: 0.012 for `Older than 24`, 0.005 for
  `>20 - 24`, 0.001 for `20 and younger` (`--cdoc-scale`), about 50 students: small on purpose, to
  exercise the rule that suppresses groups under 10. Then `online` by the share of the student's
  courses with `Delivery_Method` = O: 0.70 at 75%+ online, 0.40 at 50-75%, 0.15 at 25-50%, 0.03
  below, 0.15 with no delivery method. Everyone else is `on_campus`.

Measured on a full load (seed 2026):

| Effect | Result |
|---|---|
| Athlete share | 45.5% (4,689 of 10,311) |
| Retention, athletes vs others | 55.0% vs 45.1% |
| 2023-24 cohort retention, football vs other athletes | 45.7% (256) vs 61.3% (932); other cohorts' football is at or above other athletes |
| Financial hold per enrolled term, Pell Y vs N | 14.2% vs 6.7% |
| Enrolled by next fall/spring, terms with a hold vs without | 67.2% vs 78.2% |
| Mean D/F/W share, low / medium / high band | 0.50 / 0.19 / 0.07 |
| Mean online share, online vs on_campus students | 0.81 vs 0.30 |
| `cdoc_facility` students | 46, 70% `Older than 24` |

## Things to know before you query

- **Registration holds keep only the hold type.** `student_attribute` holds one value per fact, so
  `Hold_Status`, `Placed_Date` and `Resolved_Date` are `dropped:` in the mapping. They stay in the
  CSV for joins outside the model.
- **A student can have several `registration_hold` rows in one term**, one per type. Pre-aggregate
  to one row per student and term before joining to cohorts.
- **`athlete_sport` exists only for athletes.** Non-athletes have no row, not a blank one.
- **A student in two cohorts** (2 students) is modelled on their earlier cohort row.
- **Every group under 10 students must be suppressed**, including `cdoc_facility` broken out by anything.
- **These files generalize the draft** in the model's `sources/registration_holds/`. Its
  `source.yaml` still describes the hand-written sample; pointing it at this file is left for when
  these move into the starter.

## Rebuild and test

From `demo/`. The generators read `../pdp-datathon-starter/data/raw/`, found from their own
location, so they run from any folder. Standard library only.

```bash
python3 population_enrichments/student_athlete.py      # data/student_athlete.csv
python3 population_enrichments/registration_holds.py   # data/registration_holds.csv
python3 population_enrichments/lms_activity_band.py    # data/lms_activity_band.csv
python3 population_enrichments/instruction_site.py     # data/instruction_site.csv
cd population_enrichments && ../../.venv/bin/python -m unittest discover -p 'test_*.py' -v
```

The tests need no packages, take a few seconds, and skip the full-data checks if the raw files
aren't there.

## Load them into the model

1. Copy `config/*_mapping.yaml` and `config/pipeline_populations.yaml` into
   `pdp-datathon-starter/normalized-data-model/config/`.
2. Add the rules in `config/destination_schema_rules.yaml` under
   `student_attribute.attribute_value.rules` in that folder's `destination_schema.yaml`.
3. From `normalized-data-model/`:

```bash
python3 -m src.loader.load --config config/pipeline_populations.yaml
```

This writes `output/pdp_populations.sqlite` and `output/tables_populations/`. The pipeline's
paths for the four files assume this folder sits at `demo/population_enrichments/`, next to
`pdp-datathon-starter/`.
