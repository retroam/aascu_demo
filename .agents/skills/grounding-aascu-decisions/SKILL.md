---
name: grounding-aascu-decisions
description: "Grounds AASCU demo product, analysis, UI, report, and issue decisions in Adams State and IU discovery evidence. Use when proposing features, interpreting metrics, changing workflows or copy, writing reports, or prioritizing issues—even when discovery is not explicitly mentioned."
---

# Grounding AASCU decisions

Connect each recommendation to a stakeholder question, trustworthy evidence, and
an action someone has capacity to take. Do not treat this skill as a feature checklist.

## Read the relevant evidence

Sources live in `../discovery/` relative to the demo repository root, not this
skill directory. Read the relevant sections directly before making a new claim;
if the sibling folder is unavailable, disclose that limitation rather than inventing support.
Keep source records read-only. Cite filenames, sections, and dates in your work;
do not copy raw transcripts, attendee lists, or contact details into deliverables.

- **Adams State — September 16, 2026:** `Adams State - Discovery 1 Notes.md`,
  source note and sections 1 (institution), 2–3 (example/walkthrough), 4–5
  (friction/data), 6 (what great looks like), and 10 (parking lot). Human notes
  are primary. Anything tagged **Granola only — verify** remains unverified,
  including AI policy claims, precise change timelines, and some integration details.
- **Both calls — September 16, 2026:** `dev color discovery calls.md`, the dated
  Indiana University Southeast and Adams State sections under Notes, Questions,
  Walkthrough example, Friction, and What would success look like. The later
  `Granola call Adams State` section is AI-generated, not independent corroboration.
- **IU — September 16, 2026:** `IU- raw transcript dump.md`, `Transcript:` passages
  about counting every student, five regional campuses, leading/trailing summer,
  progressive disclosure, capacity to respond, common metrics, credit accumulation,
  and executive summaries. The header says Sep 16; the year comes from the dated
  companion notes. Transcription errors affect names and terms (including PDP/IPEDS);
  paraphrase cautiously, and confirm ambiguous definitions rather than normalizing
  them into an invented specification.

## Separate four kinds of claim

1. **Call evidence:** what participants reported or requested, with a source/date.
   A reported experience is not independently verified outcome data.
2. **Design implication:** our proposed response to that evidence, explicitly labeled.
3. **Unverified idea or assumption:** brainstorms, Granola-only details, missing data,
   or uncertain definitions. State what would confirm them.
4. **Later selected scope:** inspect the current relevant issues in
   [devcolor/aascu-datathon](https://github.com/devcolor/aascu-datathon/issues),
   not this demo repository's issue tracker. Cite the issue and distinguish its
   acceptance criteria from call evidence. Do not freeze issue status in this skill
   or infer that an implemented demo feature was requested or approved by a campus.

## Apply the institutional context

| Call evidence | Design implication—not a claim of approval |
| --- | --- |
| Adams has a one-person IR office; capacity, not lack of interest, limits exploration. | Prefer quick, repeatable answers and shareable reports over another workflow requiring ongoing analyst maintenance. |
| Banner-to-Workday changes broke longitudinal comparability; definitions and major codes do not map one-to-one. Untrained consumers invent metric meanings. | Show population, denominator, time window, definition, missingness, and provenance; disclose discontinuities rather than silently stitching trends. |
| Adams described a part-time graduation pattern prompting a financial-aid funding change. | Tell the observation → interpretation → policy-action story. Do not claim part-time enrollment caused noncompletion or that changed funding improved outcomes; neither is established by the call. |
| IU wants all student populations represented, not only first-time full-time students, and common metrics across five regional campuses. | Make cohort eligibility and exclusions visible; include transfer, adult, returning, and part-time populations when supported. Explain different legitimate definitions rather than manufacturing a single comparable number. |
| IU described PDP trailing summer versus institutional leading summer. | Treat the distinction as reported evidence, but obtain precise calendar boundaries, cohort assignment rules, and examples before implementing a crosswalk. |
| IU requested question-first progressive disclosure and easier natural-language access. | Start with the decision/question and a plain-language answer; reveal comparisons, definitions, and technical evidence progressively without hiding essential caveats. |
| IU separated historical PDP learning from timely operational signals and described limited capacity to respond. | Label observation dates and coverage; ask who can act, when, and on how many cases. Do not turn historical rows into current alerts or impose the illustrative caseload numbers as fixed requirements. |
| IU wanted reusable credit-momentum calculations and storytelling/executive summaries. | Reuse validated calculations and export definitions, scope, limitations, and next questions with the narrative. Avoid new report-specific versions of the same metric. |

## Work through the decision

1. Name the audience, question, proposed decision, and available action capacity.
2. Read and cite the relevant evidence; identify unresolved definitions or conflicts.
3. Check available fields, grain, eligibility, missingness, timing, and outcome coverage.
   Distinguish historical association, prediction, and causal effect. A scenario's
   assumed benefit is not an estimated treatment effect.
4. Check selected scope in the relevant current issue when scope matters. If access
   is unavailable, say scope is unverified and keep any recommendation provisional.
5. Propose the smallest useful workflow and a check that demonstrates it answers
   the question without misleading the audience. Prefer shared calculations.
6. Return a brief **evidence → implication → recommendation → validation/open question**
   explanation, plus the relevant issue reference when one was checked.

Keep raw inputs read-only and all prototype results synthetic-only. Do not infer
institutional authorization, approved AI vendors, live integrations, intervention
efficacy, or permission to expose student records from discovery or prototype use.
Predictive flags, peer matching, and integration ideas need separate data, validation,
and governance decisions; being discussed does not make them ready or selected.
