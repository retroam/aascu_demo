"""Read-only, reproducible evidence over the synthetic PDP starter extract.

No language model supplies values or SQL. The dashboard, constrained assistant,
trend detector, and downloads call the same metric functions.
"""
from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import math
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import pandas as pd
import foundations

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "pdp-datathon-starter" / "data"
SOURCE = "Normalized PDP model · cohort_membership + student · shared measures"
SYNTHETIC = "These results describe mock data, not real students or institutions."
COHORTS = ("2021-22", "2022-23", "2023-24", "2024-25")
POPULATIONS = {"all": "All students", "full-time": "Full-time students", "part-time": "Part-time students", "pell": "Pell recipients", "adult": "Students older than 24"}
MIN_CELL = 20


@lru_cache(maxsize=1)
def load_data():
    """Shared read-only source frame. Callers must not modify this object."""
    return foundations.cohort_frame()


@lru_cache(maxsize=1)
def cohorts():
    """Available entry cohorts in chronological order for the current dataset."""
    return tuple(sorted(load_data().Cohort.unique()))


@lru_cache(maxsize=1)
def provenance():
    """Describe the files actually loaded, without exposing local upload paths."""
    with foundations.connection() as db:
        return [{"file": Path(name).name, "rows": rows, "sha256": checksum}
                for name, rows, checksum in db.execute(
                    "SELECT source_file, row_count, file_sha256 FROM data_provider ORDER BY provider_id")]


def normalize_filters(filters=None):
    filters = {} if filters is None else filters
    if not isinstance(filters, dict):
        raise ValueError("Filters must be an object.")
    if set(filters) - {"cohort", "population", "threshold"}:
        raise ValueError("Only cohort, population, and threshold filters are supported.")
    cohort = str(filters.get("cohort", "all"))
    population = str(filters.get("population", "all"))
    threshold = str(filters.get("threshold", "24"))
    if cohort not in ("all", *cohorts()):
        raise ValueError("Choose an available cohort: all, " + ", ".join(cohorts()) + ".")
    if population not in POPULATIONS:
        raise ValueError("Choose an available population: all, full-time, part-time, pell, or adult.")
    if threshold not in ("24", "30"):
        raise ValueError("Credit momentum threshold must be 24 or 30.")
    return {"cohort": cohort, "population": population, "threshold": int(threshold)}


def filter_data(filters=None):
    f = normalize_filters(filters)
    df = load_data()
    mask = pd.Series(True, index=df.index)
    if f["cohort"] != "all":
        mask &= df["Cohort"].eq(f["cohort"])
    p = f["population"]
    if p in ("full-time", "part-time"):
        mask &= df["Enrollment_Intensity_First_Term"].eq("Full-Time" if p == "full-time" else "Part-Time")
    elif p == "pell":
        mask &= df["Pell_Status_First_Year"].eq("Y")
    elif p == "adult":
        mask &= df["Student_Age"].eq("Older than 24")
    return df.loc[mask]


def wilson(k, n):
    if not n:
        return [None, None]
    z = 1.959963984540054
    p = k / n
    center = (p + z*z/(2*n)) / (1 + z*z/n)
    spread = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / (1 + z*z/n)
    return [round(100*max(0, center-spread), 2), round(100*min(1, center+spread), 2)]


def metric(df, metric_id, threshold=24):
    """Return counts and an auditable denominator; unknown values never become 0."""
    status = "ok"
    if metric_id in ("retention", "persistence", "gateway_math", "gateway_english", "credit_completion"):
        result = foundations.measure(df, metric_id)
        denominator, numerator, missing = result.denominator, result.numerator, result.n_excluded
        column = {
            "retention": "cohort_membership.retention", "persistence": "cohort_membership.persistence",
            "gateway_math": "cohort_membership.gateway_math_status + cohort_membership.completed_gateway_math_year1",
            "gateway_english": "cohort_membership.gateway_english_status + cohort_membership.completed_gateway_english_year1",
            "credit_completion": "cohort_membership.number_of_credits_earned_yr_1 + cohort_membership.number_of_credits_attempted_yr_1",
        }[metric_id]
        status = result.status.value
        label = {"retention": "Year-two retention", "persistence": "Persistence elsewhere",
                 "gateway_math": "Gateway math completion", "gateway_english": "Gateway English completion",
                 "credit_completion": "Credit completion ratio"}[metric_id]
        definition = result.note
        if metric_id == "persistence":
            definition += " Enrollment or credentials at another institution; retention and persistence must not be added."
        if metric_id.startswith("gateway_"):
            definition += " Shared denominator: known C/D outcomes, excluding unknown outcomes (unlike the previous all-required denominator)."
    elif metric_id == "momentum":
        column = "Number_of_Credits_Earned_Yr_1"
        credits = pd.to_numeric(df[column], errors="coerce")
        known = credits.notna() & credits.ge(0)
        denominator = int(known.sum())
        numerator = int((known & credits.ge(threshold)).sum())
        missing = len(df) - denominator
        label = f"{threshold}-credit momentum"
        definition = f"Students with at least {threshold} credits earned in year one, divided by students with valid credit totals. Missing and invalid totals are excluded; zero counts as valid."
    else:
        raise ValueError("Unsupported metric.")
    suppressed = denominator is None or denominator < MIN_CELL
    return {"id": metric_id, "label": label, "value": round(100*numerator/denominator, 2) if denominator and not suppressed else None,
            "numerator": numerator if not suppressed else None, "denominator": denominator if not suppressed else None, "missing": missing if not suppressed else None,
            "definition": definition, "column": column, "unit": "%", "interval": wilson(numerator, denominator) if not suppressed and metric_id != "credit_completion" else [None, None],
            "suppressed": suppressed, "status": "suppressed" if suppressed and status == "ok" else status, "source": SOURCE}


def _metrics(df, threshold):
    return [metric(df, name, threshold) for name in ("retention", "momentum", "gateway_math", "persistence")]


def _summary_row(df, threshold):
    result = {"n": len(df)}
    for m in _metrics(df, threshold):
        result[m["id"]] = m["value"]
        result[m["id"]+"_denominator"] = m["denominator"]
        result[m["id"]+"_interval"] = m["interval"]
    return result


def _timeline(filters):
    f = dict(filters, cohort="all")
    df = filter_data(f)
    return [{"cohort": c, **_summary_row(df[df.Cohort.eq(c)], f["threshold"])} for c in cohorts()]


def _segments(df, threshold):
    return [{"name": label, "population": pop, **_summary_row(df[df.Enrollment_Intensity_First_Term.eq(value)], threshold)}
            for value, label, pop in [("Full-Time", "Full-time", "full-time"), ("Part-Time", "Part-time", "part-time"), ("Unknown", "Unknown intensity", "unknown")]]


def _quality(df):
    credits = pd.to_numeric(df["Number_of_Credits_Earned_Yr_1"], errors="coerce")
    required = df["Gateway_Math_Status"].eq("R")
    return [
        {"label": "Missing year-one credits", "count": int(credits.isna().sum()), "detail": "Excluded from the credit-momentum denominator, never treated as zero.", "severity": "note"},
        {"label": "Unknown enrollment intensity", "count": int((~df.Enrollment_Intensity_First_Term.isin(["Full-Time", "Part-Time"])).sum()), "detail": "Kept in overall metrics and shown as a separate group.", "severity": "note"},
        {"label": "Required math: no completion code", "count": int((required & ~df.CompletedGatewayMathYear1.isin(["C", "D"])).sum()), "detail": "Excluded by the shared gateway measure, never assumed to have failed.", "severity": "warning"},
        {"label": "Unknown first-generation status", "count": int((~df.First_Gen.isin(["Y", "N"])).sum()), "detail": "Legacy coding is unresolved; first-generation comparisons are not offered.", "severity": "warning"},
        {"label": "Students in multiple cohorts", "count": int((df.groupby("Student_GUID").size() > 1).sum()), "detail": "Student-cohort records are the metric grain. Course joins require both Student_GUID and Cohort.", "severity": "note"},
    ]


def _change(current, previous):
    if current["value"] is None or previous["value"] is None:
        return None, [None, None]
    a = current["numerator"] / current["denominator"]
    b = previous["numerator"] / previous["denominator"]
    delta = 100*(a-b)
    se = 100*math.sqrt(a*(1-a)/current["denominator"] + b*(1-b)/previous["denominator"])
    return round(delta, 2), [round(delta-1.96*se, 2), round(delta+1.96*se, 2)]


def get_signals(filters=None):
    f = normalize_filters(filters)
    available = cohorts()
    if not available:
        return []
    cohort = available[-1] if f["cohort"] == "all" else f["cohort"]
    position = available.index(cohort)
    if position == 0:
        return []
    previous = available[position-1]
    a = filter_data(dict(f, cohort=cohort))
    b = filter_data(dict(f, cohort=previous))
    signals = []
    for key in ("retention", "momentum", "gateway_math", "persistence"):
        cm, pm = metric(a, key, f["threshold"]), metric(b, key, f["threshold"])
        delta, ci = _change(cm, pm)
        if delta is None:
            continue
        direction = "down" if delta < 0 else "up"
        caution = "Newer cohorts may have less follow-up. Confirm outcome completeness before interpreting the difference."
        signals.append({"id": key, "title": f"{cm['label']} {'fell' if delta < 0 else 'rose'} {abs(delta):.1f} points",
                        "detail": f"{previous} → {cohort}: {pm['value']:.1f}% → {cm['value']:.1f}% for {POPULATIONS[f['population']].lower()}.",
                        "value": delta, "unit": "pp", "direction": direction, "category": "Observed change",
                        "metric": key, "current": cm["value"], "previous": pm["value"], "current_cohort": cohort, "previous_cohort": previous,
                        "n": cm["denominator"], "previous_n": pm["denominator"], "interval": ci,
                        "evidence": "Exploratory comparison", "caution": caution, "source": SOURCE})
    return sorted(signals, key=lambda x: abs(x["value"]), reverse=True)


def get_dashboard(filters=None):
    import dataset
    f = normalize_filters(filters)
    df, all_df = filter_data(f), load_data()
    prov = provenance()
    current = dataset.identity()
    return {"meta": {"cohort_rows": len(all_df), "unique_students": int(all_df.Student_GUID.nunique()), "course_rows": current["course_rows"],
                     "cohorts": list(cohorts()), "dataset": current, "source": SOURCE, "synthetic": True, "filtered_rows": len(df),
                     "filtered_unique_students": int(df.Student_GUID.nunique()), "grain": "Student × entry cohort", "provenance": prov,
                     "follow_up": "No source extraction date is supplied; outcome maturity is unverified."},
            "filters": f, "metrics": _metrics(df, f["threshold"]), "timeline": _timeline(f),
            "timeline_scope": "All entry cohorts for the selected population; the cohort filter applies to summary cards and segments.",
            "segments": _segments(df, f["threshold"]), "quality": _quality(df), "signals": get_signals(f),
            "notice": SYNTHETIC}


def get_trends(filters=None):
    from modeling import get_association
    f = normalize_filters(filters)
    return {"filters": f, "signals": get_signals(f), "timeline": _timeline(f), "association": get_association(f),
            "methodology": ["Adjacent entry-cohort rate differences; latest versus previous available cohort, respecting the selected population.",
                            "Intervals are approximate 95% normal intervals for a difference in proportions; metric intervals use Wilson's method.",
                            "Rankings are exploratory, not adjusted for multiple comparisons. Students may enter multiple cohorts; simple intervals do not model that dependence.",
                            "Follow-up maturity is unverified. Differences do not establish causation. Adjusted associations require assumptions about unmeasured confounding."],
            "notice": SYNTHETIC}


def get_gaps(query=None):
    """Return shared group comparisons for a validated cohort, population and breakdown."""
    query = dict(query or {})
    measure_name = query.pop("measure", "retention")
    breakdown = query.pop("breakdown", "race")
    if measure_name not in ("retention", "persistence", "gateway_math", "gateway_english"):
        raise ValueError("Choose retention, persistence, gateway_math or gateway_english.")
    if breakdown not in ("race", "gender", "pell", "age_band", "enrollment_intensity", "race,gender", "pell,enrollment_intensity"):
        raise ValueError("Unsupported gap breakdown.")
    f = normalize_filters(query)
    years = list(cohorts()) if f["cohort"] == "all" else [f["cohort"]]
    return {"filters": f, "measure": measure_name, "breakdown": breakdown,
            "rows": foundations.equity_gaps(filter_data(f), years, measure_name, tuple(breakdown.split(","))),
            "notice": SYNTHETIC,
            "method": "Group minus everyone else within the selected population. Newcombe 95% intervals; Benjamini–Hochberg q-values across this breakdown. Hidden when either side has fewer than 20 eligible records. Ranks and q-values depend on the requested breakdown. Differences are not causes; follow-up maturity is unverified."}


def get_shared_measures(filters=None):
    """Return English gateway, credit completion and course DFW from shared calculations."""
    f = normalize_filters(filters)
    years = list(cohorts()) if f["cohort"] == "all" else [f["cohort"]]
    return {"filters": f, "metrics": foundations.additional_measures(filter_data(f), years), "notice": SYNTHETIC}


SUGGESTIONS = ["What is the retention rate?", "Compare full-time and part-time retention", "How many students earn 24 credits?", "How does retention change across cohorts?", "What data quality issues should I know about?"]


def _unsupported(reason, filters):
    return {"status": "unsupported", "answer": reason + " " + SYNTHETIC, "citations": [],
            "plan": {"intent": "unsupported", "filters": filters},
            "validation": {"passed": False, "checks": ["Scope gate blocked an unsupported or ambiguous request", "No numerical answer generated"]},
            "suggestions": SUGGESTIONS[:3], "notice": SYNTHETIC}


def _citation(m, f, label=None):
    return {"label": label or m["label"], "source": SOURCE, "columns": m["column"].split(" + "),
            "numerator": m["numerator"], "denominator": m["denominator"], "missing": m["missing"], "filters": f,
            "definition": m["definition"], "interval": m["interval"]}


CONTEXT_METRICS = ("retention", "momentum", "gateway_math", "persistence")
CONTEXT_INTENTS = {"metric", "summary", "dashboard", "cohort_trend", "compare_intensity", "definition"}
METRIC_TERMS = {"retention": "retention", "momentum": "credit momentum", "gateway_math": "gateway math", "persistence": "persistence elsewhere"}


def _question_text(question):
    text = re.sub(r"\s+", " ", question.lower().strip().replace("–", "-").replace("—", "-"))
    text = text.replace("’", "'")
    text = re.sub(r"\bwhat's\b", "what is", text)
    text = re.sub(r"\bhow's\b", "how is", text)
    return text.strip(" .?!")


def _chat_context(context):
    """Accept only the bounded result context that the assistant returns."""
    if context is None:
        return None
    if not isinstance(context, dict) or set(context) != {"metrics", "filters", "intent"}:
        raise ValueError("Chat context must contain metrics, filters, and intent.")
    metrics = context["metrics"]
    if (not isinstance(metrics, list) or not 1 <= len(metrics) <= 4
            or any(not isinstance(m, str) or m not in CONTEXT_METRICS for m in metrics)
            or len(set(metrics)) != len(metrics)):
        raise ValueError("Chat context contains unsupported metrics.")
    if not isinstance(context["intent"], str) or context["intent"] not in CONTEXT_INTENTS:
        raise ValueError("Chat context contains an unsupported intent.")
    if context["intent"] in ("metric", "cohort_trend", "compare_intensity") and len(metrics) != 1:
        raise ValueError("This chat intent requires one metric.")
    return {"metrics": metrics.copy(), "filters": normalize_filters(context["filters"]), "intent": context["intent"]}


def _help_answer(filters, answer=None):
    return {"status": "help", "answer": answer or (
        "Ask about retention, credit momentum, gateway math, persistence elsewhere, or data quality. "
        "You can compare full-time and part-time students, view cohort trends, or create a dashboard. "
        "Try: 'Build a dashboard with retention and credit momentum for Pell recipients'."),
        "citations": [], "rows": [], "context": None,
        "plan": {"intent": "help", "filters": filters},
        "validation": {"passed": True, "checks": ["Supported question guidance; no numerical claims"]},
        "suggestions": ["What is the retention rate?", "Show retention across cohorts",
                        "What does credit momentum mean?", "Build a dashboard for Pell recipients"],
        "notice": SYNTHETIC}


def _follow_up(q, context):
    """Translate a full-match follow-up grammar into a validated query."""
    population = re.fullmatch(r"(?:now |and |what about |show (?:me )?(?:that |this )?)?(?:for )?(all students|full[ -]time(?: students)?|part[ -]time(?: students)?|pell(?: recipients| students)?|adult(?: students)?|adults|students older than 24)(?: instead)?", q)
    cohort = re.fullmatch(r"(?:now |and |what about |show (?:me )?(?:that |this )?)?(?:for |in )?(the )?(latest cohort|previous cohort|all cohorts|202[1-4]-2[2-5])(?: instead)?", q)
    threshold = re.fullmatch(r"(?:make (?:that|it)|change (?:that|it|the threshold) to|use|now use|and) (24|30)[ -]credits?(?: instead)?", q)
    add = re.fullmatch(r"(?:add|include) (retention|(?:credit )?momentum|gateway math(?: completion)?|persistence(?: elsewhere)?)(?: (?:to|in) (?:the |this |that )?dashboard)?", q)
    create = re.fullmatch(r"(?:make|build|create) (?:this|that) (?:into )?(?:a )?dashboard", q)
    if not any((population, cohort, threshold, add, create)):
        return None
    if context is None:
        return {"help": "Choose a metric or create a dashboard first. Then you can change the population, cohort, or credit threshold in a follow-up."}
    updated = {"metrics": context["metrics"].copy(), "filters": context["filters"].copy(), "intent": context["intent"]}
    suffix = ""
    if population:
        group = population[1]
        updated["filters"]["population"] = ("all" if group == "all students"
            else "full-time" if re.match(r"full[ -]time", group)
            else "part-time" if re.match(r"part[ -]time", group)
            else "pell" if group.startswith("pell") else "adult")
    if cohort:
        suffix = " for " + cohort[2]
    if threshold:
        if "momentum" not in updated["metrics"]:
            return {"help": "The credit threshold applies to credit momentum. Ask for credit momentum or add it to a dashboard first."}
        updated["filters"]["threshold"] = int(threshold[1])
    if add:
        if updated["intent"] != "dashboard":
            return {"help": "Adding a metric requires a dashboard. Ask 'Make that a dashboard', then add the metric."}
        term = add[1]
        key = ("retention" if term == "retention" else "momentum" if "momentum" in term
               else "gateway_math" if "math" in term else "persistence")
        if key not in updated["metrics"]:
            updated["metrics"].append(key)
    if create:
        updated["intent"] = "dashboard"
    terms = " and ".join(METRIC_TERMS[m] for m in updated["metrics"])
    if updated["intent"] == "dashboard":
        query = "Create a dashboard with " + terms
    elif updated["intent"] == "cohort_trend":
        query = "Show " + terms + (" across cohorts" if not cohort or cohort[2] == "all cohorts" else "")
        if cohort and cohort[2] == "all cohorts":
            suffix = ""
    elif updated["intent"] == "compare_intensity":
        single_intensity = population and re.search(r"(?:full|part)[ -]time", population[1])
        query = ("Show " if single_intensity else "Compare full-time and part-time ") + terms
    elif updated["intent"] == "definition":
        query = "Define " + terms
    else:
        query = "Show " + terms
    return {"question": query + suffix, "filters": updated["filters"]}


def answer_question(question, filters=None, context=None):
    filters = normalize_filters(filters)
    prior = _chat_context(context)
    if not isinstance(question, str) or not question.strip() or len(question) > 1200:
        return _unsupported("Enter a question about retention, credit momentum, gateway math, or data quality. Questions can contain up to 1,200 characters.", filters)
    q = _question_text(question)
    if re.fullmatch(r"(?:hi|hello|hey)(?: there)?|help|what can (?:i ask|you do)|how (?:do i use|does) (?:this|the chat|the assistant)(?: work)?", q):
        return _help_answer(filters)
    follow_up = _follow_up(q, prior)
    if follow_up:
        if "help" in follow_up:
            result = _help_answer(filters, follow_up["help"])
            result["context"] = prior
            return result
        q, filters = follow_up["question"], follow_up["filters"]
    if re.fullmatch(r"(?:how is|show(?: me)?|summarize) (?:our )?student success", q):
        q = "Summarize the evidence"
    if re.fullmatch(r"(?:what (?:are|have been)|show(?: me)?|summarize) (?:the )?(?:main |key )?trends", q):
        return _help_answer(filters, "Choose a metric for the cohort trend: retention, credit momentum, gateway math, or persistence elsewhere. Try 'Show retention across cohorts'.")
    result = _answer_question(q, filters)
    if result["status"] == "verified":
        plan = result["plan"]
        metrics = plan.get("metrics") or list(dict.fromkeys(r["id"] for r in result.get("rows", []) if "id" in r))
        if metrics and plan["intent"] in CONTEXT_INTENTS:
            result["context"] = {"metrics": metrics, "filters": plan["filters"].copy(), "intent": plan["intent"]}
    elif prior:
        result["context"] = prior
    return result


def _answer_question(question, filters=None):
    f = normalize_filters(filters)
    if not isinstance(question, str) or not question.strip() or len(question) > 1200:
        return _unsupported("Ask a question about retention, credit momentum, gateway math, or data quality (up to 1,200 characters).", f)
    q = _question_text(question)
    dashboard_request = bool(re.search(r"\b(build|create|make)\b.*\bdashboard\b", q))
    # The assistant intentionally never falls back to arbitrary SQL or model-authored facts.
    blocked = r"\b(caus(?:e|es|ed|al|ation)|why|effect|impact|scholarship|aid|tuition|revenue|cost|budget|salary|income|financial|forecast|predict|prediction|next year|official|ipeds|benchmark|peer|campus|adams|indiana|university|college name|individual|student id|email|phone|ignore|instructions|pretend|fabricate|invent|sql|select\s+\*|drop\s+table|graduation|graduate|credential|race|ethnic|hispanic|black|white|asian|gender|women|men|female|male|first.gen|major|program|athlet|housing|disability|veteran|international|transfer|gpa|course pass|english)\b"
    if re.search(blocked, q):
        return _unsupported("That request needs data or an analysis this assistant does not support. Ask about retention, credit momentum, gateway math, persistence, or data quality. Use Modeling for prediction and scenario planning.", f)
    if "%" in q or re.search(r"\b(?:set|change|say|assume)\b.*\d", q):
        return _unsupported("I can report calculated values, but cannot accept a supplied percentage as evidence or alter a result.", f)
    years = re.findall(r"\b20\d{2}(?:-\d{2})?\b", q)
    if any(y not in cohorts() for y in years):
        return _unsupported("That cohort is not available. Available cohorts: " + ", ".join(cohorts()) + ".", f)
    if len(set(years)) > 1:
        return _unsupported("For a multi-year comparison, ask how a metric changes across cohorts. For one cohort, specify a single available cohort.", f)
    all_cohorts = bool(re.search(r"\b(all (?:entry )?cohorts|across cohorts|by cohorts?|over time|(?:across|over|through) (?:the )?years)\b", q))
    latest = bool(re.search(r"\b(latest|most recent)\b", q))
    previous_cohort = bool(re.search(r"\bprevious cohort\b", q))
    if all_cohorts and (years or latest or previous_cohort):
        return _unsupported("The request mixes all cohorts with a single cohort. Choose one time scope, or ask for an unfiltered cohort trend.", f)
    if latest and previous_cohort or previous_cohort and years:
        return _unsupported("Choose one cohort reference: latest, previous, or an explicit cohort label.", f)
    if years:
        f["cohort"] = years[0]
    if latest:
        if years and years[0] != cohorts()[-1]:
            return _unsupported("The explicit cohort conflicts with the latest-cohort request. Choose one cohort.", f)
        f["cohort"] = cohorts()[-1]
    elif previous_cohort:
        selected_index = cohorts().index(f["cohort"]) if f["cohort"] != "all" else len(cohorts())-1
        if selected_index == 0:
            return _unsupported("No earlier cohort is supplied for this selection.", f)
        f["cohort"] = cohorts()[selected_index-1]
    credits = re.findall(r"\b(\d+)\s*[- ]?credits?", q)
    if any(c not in ("24", "30") for c in credits) or len(set(credits)) > 1:
        return _unsupported("Credit momentum supports one threshold at a time: 24 or 30 year-one credits.", f)
    if credits:
        f["threshold"] = int(credits[0])
    if re.search(r"\b(over|above|under|below|exactly|more than|greater than|less than)\s+\d+\s*[- ]?credits?", q):
        return _unsupported("Momentum means at least 24 or at least 30 year-one credits. Strict inequalities or exact-credit counts need a different validated measure.", f)
    age_cutoffs = re.findall(r"\b(?:older than|over|under|younger than)\s+(\d+)\b", q)
    if any(age != "24" for age in age_cutoffs):
        return _unsupported("The supported adult population is older than 24. Other age cutoffs cannot be reconstructed from these age bands.", f)
    numeric_scope = re.sub(r"\b20\d{2}-\d{2}\b|\b(?:24|30)\s*[- ]?credits?\b|\b(?:older than|over) 24\b", "", q)
    if re.search(r"\d", numeric_scope):
        return _unsupported("I could not validate that numeric condition. Use a full available cohort label, 24/30-credit momentum, or adults older than 24.", f)
    full, part = bool(re.search(r"full[ -]?time", q)), bool(re.search(r"part[ -]?time", q))
    pell, adult = bool(re.search(r"\bpell\b", q)), bool(re.search(r"\b(adults?|older than 24|over 24)\b", q))
    if re.search(r"\b(non[ -]?pell|not pell|under \d|younger|20[ -]24|20 to 24|aged \d)\b", q):
        return _unsupported("That subgroup is outside the assistant's supported filters. Use all students, full-time, part-time, Pell recipients, or students older than 24.", f)
    compare_intensity = full and part or bool(re.search(r"\bby enrollment intensity\b", q))
    if re.search(r"\bby enrollment intensity\b", q) and (full != part):
        return _unsupported("The request selects one intensity and also asks to compare intensities. Choose the single population, or compare full-time and part-time students.", f)
    if re.search(r"\b(each|every) populations?\b", q):
        return _unsupported("A dashboard uses one population filter. Choose all students, full-time, part-time, Pell recipients, or adults; a population-by-population layout is not supported.", f)
    if sum([full or part, pell, adult]) > 1:
        return _unsupported("This assistant supports one population filter at a time. Select full-time, part-time, Pell recipients, or adult students; intersecting populations need an additional validated query.", f)
    if full and not part:
        f["population"] = "full-time"
    elif part and not full:
        f["population"] = "part-time"
    elif pell:
        f["population"] = "pell"
    elif adult:
        f["population"] = "adult"
    if compare_intensity and f["population"] in ("full-time", "part-time"):
        # A comparison explicitly requests both groups; make the change auditable.
        f["population"] = "all"
    if re.search(r"\b(all students|all populations)\b", q):
        if full or part or pell or adult:
            return _unsupported("Choose one population, or explicitly compare full-time and part-time students.", f)
        f["population"] = "all"
    if all_cohorts:
        f["cohort"] = "all"
    quality = bool(re.search(r"\b(quality|missing|validation|reliable|trust|limitations)\b", q))
    summary = bool(re.search(r"\b(summarize|summary|overview|stand[s]? out|key metrics|key findings|evidence brief)\b", q))
    trend = bool(re.search(r"\b(trends?|across cohorts|by cohorts?|over time|(?:across|over|through) (?:the )?years|change across|changed|changing)\b", q))
    if trend and (years or latest or previous_cohort):
        return _unsupported("A cohort trend needs multiple cohorts. Ask for the trend without a single-cohort constraint, or request a dashboard for that cohort.", f)
    if re.search(r"\bby\b", q) and not re.search(r"\bby (cohorts?|enrollment intensity)\b", q):
        return _unsupported("Supported breakdowns are by cohort or enrollment intensity. Other grouping dimensions need a validated query.", f)
    if not dashboard_request and sum([quality, summary, compare_intensity, trend]) > 1:
        return _unsupported("That request combines multiple analyses. Ask for one metric, one full-time/part-time comparison, a cohort trend, or a summary at a time; alternatively create a dashboard.", f)
    if dashboard_request and quality:
        return _unsupported("Dashboard plans currently support retention, momentum, gateway math, and persistence. Ask about data quality separately.", f)
    if re.search(r"\b(returning|return|first[ -]time|term (one|two)|first[ -]term|second[ -]term)\b", q):
        return _unsupported("That student group or term window is not supported. Retention uses the supplied year-two flag; use first-term enrollment intensity only as a full-time/part-time grouping.", f)
    if dashboard_request and re.search(r"\b(?:retention|momentum|math|persistence|elsewhere) only\b|\bonly (?:retention|credit momentum|gateway math|persistence elsewhere)\b", q) and not re.search(r"\bretained students\b", q):
        q = re.sub(r"\bonly\b", "", q)
    if re.search(r"\b(not|no|without|below|less than|more than|greater than|exactly|only|failed|failure|fall|fell|decline|declined|increase|increased|decrease|decreased)\b", q):
        return _unsupported("That wording requests an inverse, restricted, or directional measure I cannot safely infer. Ask for the metric directly or its trend across cohorts.", f)
    keys = []
    if re.search(r"\b(retention|retained|returning|return)\b", q): keys.append("retention")
    if re.search(r"\b(momentum|credits?)\b", q): keys.append("momentum")
    if re.search(r"\b(gateway|math)\b", q): keys.append("gateway_math")
    if re.search(r"\b(persistence|persisted|elsewhere)\b", q): keys.append("persistence")
    comparison_requested = bool(re.search(r"\b(gap|difference|compare|comparison|comparing|vs|versus)\b", q))
    if comparison_requested and not compare_intensity and not trend and not (dashboard_request and len(keys) > 1):
        return _unsupported("Supported comparisons are full-time versus part-time or a metric across cohorts. A dashboard can also display multiple named metrics; comparisons with all students or other population groups are not supported.", f)
    remaining_scope = re.sub(r"\ball (?:entry )?cohorts\b", "", q)
    if comparison_requested and (full or part or pell or adult) and re.search(r"\ball\b", remaining_scope):
        return _unsupported("A selected population versus all students requires two validated scopes. This dashboard supports one population at a time; choose a single group or compare full-time and part-time.", f)
    if "momentum" in keys and not credits and not re.search(r"\bmomentum\b", q):
        return _unsupported("I cannot infer a credit total from the momentum metric. Ask for 24-credit or 30-credit momentum, or how many students reach that threshold.", f)
    if compare_intensity and trend:
        return _unsupported("The current view supports a cohort trend and an overall intensity comparison separately, not an intensity-by-cohort series. Choose one analysis at a time.", f)
    definition = bool(re.search(r"\b(define|definition|definitions|mean|means|meaning|formula)\b", q)
                      or re.search(r"\bhow\b.*\b(calculate|calculated|calculation)\b", q))
    if re.search(r"\b(?:students|records|cohorts) (?:with|who|that)|\b(?:for|among) (?:students )?(?:retained|completed|earned|persisted)\b", q):
        return _unsupported("That condition needs an additional filter. Available populations are all students, full-time, part-time, Pell recipients, and adults older than 24.", f)
    if len(keys) > 1 and not dashboard_request:
        if compare_intensity or trend or quality:
            return _unsupported("Use one metric for a cohort trend or intensity comparison. A dashboard can show multiple metrics.", f)
        if not summary and not re.search(r"\band\b|,|&", q):
            return _unsupported("List the metrics with 'and' to request a summary, or ask about one metric. A conditional population requires a supported filter.", f)
        summary = not definition
    if (any(k in ("retention", "persistence") for k in keys) and re.search(r"\b(first[ -]year|year[ -]one|first[ -]term|second[ -]term)\b", q)) or (any(k in ("momentum", "gateway_math") for k in keys) and re.search(r"\b(second[ -]year|year[ -]two|first[ -]term|second[ -]term)\b", q)):
        return _unsupported("That time window does not match the defined measure. Retention and persistence use the supplied year-two flags; credit momentum and gateway completion use year-one fields.", f)
    if re.search(r"\bprevious\b", q) and not re.search(r"\bprevious cohort\b", q):
        return _unsupported("Specify 'previous cohort' to move one cohort earlier, or ask for a trend across cohorts.", f)
    if re.search(r"\brecent\b", q) and not re.search(r"\bmost recent\b", q):
        return _unsupported("Use 'latest cohort' or one available cohort label to make the time window explicit.", f)
    if not keys and not quality and not summary and not dashboard_request:
        return _unsupported("I did not find a supported metric in that question. Try retention, credit momentum, gateway math, persistence elsewhere, or data quality.", f)
    # Reject unrecognized scope modifiers instead of dropping an unfamiliar noun.
    safe_words = set("what is are the a an my our we you i can could would please tell show me us give explain about of for in at on to from and or vs versus between by with do does how many much rate rates student students cohort cohorts entry all population populations selected current filter filters data evidence recorded documented year years one two first second term full time part fulltime parttime enrollment intensity pell recipient recipients adult adults older than over retention retained returning return momentum credit credits earned earn earning complete completed completion gateway math persistence persisted elsewhere compare comparison compares gap difference change changes changed changing across trend trends compare summary summarize overview key metrics metric findings stand stands out quality missing validation reliable trust limitations should know issues help there this that each has have had their during which who not below achieve achieved reach reached total count percentage percent breakdown been more less most recent latest previous look like number 24 30 2021 2022 2023 2024 21 22 23 25".split())
    safe_words.update("define definition definitions mean means meaning calculate calculated calculation formula showing main through".split())
    if dashboard_request:
        safe_words.update("build create make dashboard showing comparing include includes including using track display displaying visualize visualise focused focus".split())
    unknown = [word for word in re.findall(r"[a-z0-9]+", q) if word not in safe_words]
    if unknown:
        return _unsupported("I could not map part of that question to the available metrics or filters. Try a suggested question, or name retention, credit momentum, gateway math, or persistence and one population.", f)
    df = filter_data(f)
    scope = f"{POPULATIONS[f['population']].lower()}, {'all entry cohorts' if f['cohort'] == 'all' else f['cohort']}"
    citations, rows = [], []
    if dashboard_request:
        selected = keys or ["retention", "momentum", "gateway_math", "persistence"]
        # Only a bounded data configuration leaves this boundary: never HTML,
        # executable code, a file path, SQL, or an unvalidated filter.
        rows = [metric(df, key, f["threshold"]) for key in selected]
        title_metrics = {"retention": "Retention", "momentum": f"{f['threshold']}-credit momentum", "gateway_math": "Gateway math", "persistence": "Persistence elsewhere"}
        title = f"{POPULATIONS[f['population']]} · " + ("Student success" if len(selected) > 2 else " & ".join(title_metrics[k] for k in selected))
        dashboard = {"title": title, "metrics": selected, "filters": f.copy(), "sections": ["timeline", "segments"],
                     "description": f"{', '.join(title_metrics[k] for k in selected)} for {scope}. Cards use the selected cohort; the trend chart provides all-cohort context for the selected population. Enrollment-intensity segments use the selected scope."}
        answer = f"Dashboard for {scope}: " + " ".join(_metric_sentence(m) for m in rows)
        return {"status": "verified", "answer": answer + " " + SYNTHETIC, "dashboard": dashboard, "citations": [_citation(m, f.copy()) for m in rows], "rows": rows,
                "plan": {"intent": "dashboard", "metrics": selected, "filters": f.copy(), "planner": "Constrained local parser; no generative model"},
                "validation": {"passed": True, "checks": ["Dashboard schema validated", "Only allowlisted metrics, filters, and sections", "All requested supported metrics included", "Values computed from source records", "Denominators and citations attached", "No generated SQL or executable code"]},
                "suggestions": ["Build a dashboard showing retention and credit momentum for Pell recipients", "Create a dashboard for part-time students"], "notice": SYNTHETIC}
    if definition and keys:
        rows = [metric(df, key, f["threshold"]) for key in keys]
        answer = " ".join(f"{m['label']}: {m['definition']}" for m in rows)
        citations = [_citation(m, f) for m in rows]
        intent = "definition"
    elif quality and keys:
        return _unsupported("Ask for data quality issues to inspect missingness, or ask for the metric directly. I cannot infer a new metric denominator from that wording.", f)
    elif quality and not keys:
        rows = _quality(df)
        answer = "Data quality in " + scope + ": " + " ".join(f"{x['label']}: {x['count']:,}. {x['detail']}" for x in rows)
        citations = [{"label": "Source quality checks", "source": SOURCE, "columns": ["Number_of_Credits_Earned_Yr_1", "Enrollment_Intensity_First_Term", "First_Gen", "Student_GUID", "Cohort"], "filters": f, "denominator": len(df)}]
        intent = "quality"
    elif summary:
        ms = [metric(df, key, f["threshold"]) for key in keys] if keys else _metrics(df, f["threshold"])
        answer = f"Evidence summary for {scope}: " + " ".join(_metric_sentence(m) for m in ms)
        citations = [_citation(m, f) for m in ms]
        rows, intent = ms, "summary"
    elif compare_intensity:
        key = keys[0]
        for value, name in (("Full-Time", "Full-time"), ("Part-Time", "Part-time")):
            m = metric(df[df.Enrollment_Intensity_First_Term.eq(value)], key, f["threshold"])
            rows.append({"name": name, **m})
            citation = _citation(m, f.copy(), name)
            citation["group"] = {"Enrollment_Intensity_First_Term": value}
            citation["columns"].append("Enrollment_Intensity_First_Term")
            citations.append(citation)
        if any(m["suppressed"] for m in rows):
            return _unsupported("One comparison group has fewer than 20 eligible records, so its rate is suppressed.", f)
        delta = rows[0]["value"] - rows[1]["value"]
        answer = (f"For {scope}, full-time {rows[0]['label'].lower()} is {rows[0]['value']:.1f}% ({rows[0]['numerator']:,}/{rows[0]['denominator']:,}); "
                  f"part-time is {rows[1]['value']:.1f}% ({rows[1]['numerator']:,}/{rows[1]['denominator']:,}). "
                  f"The full-time minus part-time difference is {delta:+.1f} percentage points. Unmeasured differences between the groups can explain part of this association.")
        intent = "compare_intensity"
    elif trend:
        key = keys[0]
        f["cohort"] = "all"
        for c in cohorts():
            cf = dict(f, cohort=c)
            m = metric(filter_data(cf), key, f["threshold"])
            rows.append({"cohort": c, **m})
            citations.append(_citation(m, cf, c))
        answer = f"{rows[0]['label']} for {POPULATIONS[f['population']].lower()}: " + "; ".join(f"{m['cohort']}: {m['value']:.1f}% ({m['numerator']:,}/{m['denominator']:,})" if m['value'] is not None else f"{m['cohort']}: suppressed" for m in rows) + ". Follow-up completeness is unverified, and newer cohorts can have shorter observation windows."
        intent = "cohort_trend"
    else:
        m = metric(df, keys[0], f["threshold"])
        if m["suppressed"]:
            return _unsupported("Fewer than 20 eligible records remain; the rate is suppressed.", f)
        answer = f"For {scope}, " + _metric_sentence(m) + " " + m["definition"]
        citations, rows, intent = [_citation(m, f)], [m], "metric"
    return {"status": "verified", "answer": answer + " " + SYNTHETIC, "citations": citations, "rows": rows,
            "plan": {"intent": intent, "metric": keys[0] if keys else None, "filters": f, "planner": "Constrained local parser; no generative model"},
            "validation": {"passed": True, "checks": ["Recognized metric and scope", "Allowlisted filters only", "Computed directly from source records", "Denominators and source columns attached", "Small-cell rule applied"]},
            "suggestions": SUGGESTIONS[:3], "notice": SYNTHETIC}


def _metric_sentence(m):
    if m["value"] is None:
        if m.get("status") == "not_yet_observable":
            return f"{m['label']}: unavailable because a selected cohort has no known outcomes in scope."
        return f"{m['label']}: suppressed (fewer than {MIN_CELL} eligible records)."
    missing = f" {m['missing']:,} missing values disclosed." if m["missing"] else ""
    return f"{m['label']}: {m['value']:.1f}% ({m['numerator']:,} of {m['denominator']:,} eligible student-cohort records)." + missing


def report_metrics(metrics=None):
    allowed = ("retention", "momentum", "gateway_math", "persistence")
    if metrics is None:
        return list(allowed)
    selected = metrics.split(",") if isinstance(metrics, str) else metrics
    if not isinstance(selected, (list, tuple)) or not selected or any(not isinstance(k, str) or k not in allowed for k in selected):
        raise ValueError("Report metrics must be a nonempty list of retention, momentum, gateway_math, or persistence.")
    if len(set(selected)) != len(selected):
        raise ValueError("Report metric IDs must be unique.")
    return list(selected)


def _report_dashboard(filters, metrics):
    selected = report_metrics(metrics)
    d = get_dashboard(filters)
    by_id = {m["id"]: m for m in d["metrics"]}
    d["metrics"] = [by_id[key] for key in selected]
    d["signals"] = [s for s in d["signals"] if s["metric"] in selected]
    return d


def report_csv(filters=None, metrics=None):
    d = _report_dashboard(filters, metrics)
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["metric", "value_percent", "numerator", "denominator", "missing", "ci95_low", "ci95_high", "cohort", "population", "credit_threshold", "definition", "source", "synthetic"])
    for m in d["metrics"]:
        writer.writerow([m["label"], m["value"], m["numerator"], m["denominator"], m["missing"], *m["interval"], d["filters"]["cohort"], d["filters"]["population"], d["filters"]["threshold"], m["definition"], SOURCE, "true"])
    return stream.getvalue()


def report_html(filters=None, metrics=None):
    d = _report_dashboard(filters, metrics)
    f = d["filters"]
    escape = html.escape
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    cohort_label = "All entry cohorts" if f["cohort"] == "all" else f"{f['cohort']} entry cohort"
    title = f"Institutional evidence brief · {cohort_label} · {POPULATIONS[f['population']]}"
    cards = "".join(f"<article><small>{escape(m['label'])}</small><h2>{m['value']:.1f}%</h2><p>{m['numerator']:,} / {m['denominator']:,} eligible records</p><p>{m['missing']:,} missing · 95% interval {m['interval'][0]:.1f}–{m['interval'][1]:.1f}%</p></article>" if m['value'] is not None else f"<article><h2>{escape(m['label'])}</h2><p>Suppressed: fewer than 20 eligible records.</p></article>" for m in d['metrics'])
    signal_rows = "".join(f"<tr><td>{escape(s['title'])}</td><td>{escape(s['detail'])}</td><td>{s['n']:,}</td></tr>" for s in d['signals']) or "<tr><td colspan='3'>No previous cohort is available for this selection.</td></tr>"
    definitions = "".join(f"<li><b>{escape(m['label'])}.</b> {escape(m['definition'])} <code>{escape(m['column'])}</code></li>" for m in d['metrics'])
    quality = "".join(f"<li><b>{q['count']:,} {escape(q['label'].lower())}.</b> {escape(q['detail'])}</li>" for q in d['quality'])
    sources = "".join(f"<li>{escape(p['file'])} · {p['rows']:,} records<br><code>SHA-256 {p['sha256']}</code></li>" for p in d['meta']['provenance'])
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{escape(title)}</title><style>
body{{font:15px/1.65 system-ui,sans-serif;color:#171717;background:#fafafa;margin:0;padding:40px}}main{{max-width:1000px;margin:auto;background:white;padding:48px;border:1px solid #e5e5e5;border-radius:10px}}h1{{font-size:36px;line-height:1.2;letter-spacing:-1px}}h2{{font-size:28px;margin:8px 0}}small{{color:#666}}.tag{{color:#525252;background:#f5f5f5;padding:7px 12px;display:inline-block;border-radius:6px}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:28px 0}}article{{border:1px solid #e5e5e5;padding:18px;border-radius:10px}}article p{{font-size:12px;margin:4px 0}}section{{margin:30px 0}}table{{width:100%;border-collapse:collapse}}th,td{{padding:12px;border-bottom:1px solid #e5e5e5;text-align:left}}li{{margin:12px 0}}code{{font-size:11px;overflow-wrap:anywhere}}button{{background:#171717;color:#fff;border:0;padding:12px 20px;border-radius:7px;cursor:pointer}}.notice{{padding:16px;background:#fffbeb;border-radius:8px}}@media print{{body{{padding:0;background:white;font-size:11px}}main{{padding:0;border:0}}button{{display:none}}article,li{{break-inside:avoid}}h1{{font-size:28px}}h2{{font-size:20px}}.cards{{gap:8px}}}}@media(max-width:700px){{body{{padding:12px}}main{{padding:24px}}.cards{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><main><span class='tag'>PDP / SYNTHETIC DEMO</span><h1>Student success report</h1><p>{escape(title)}<br><small>Generated {generated} · {d['meta']['filtered_rows']:,} student-cohort records · {d['meta']['filtered_unique_students']:,} unique students</small></p><button onclick='window.print()'>Print / save as PDF</button><div class='cards'>{cards}</div>
<section><h2>Cohort changes</h2><table><thead><tr><th>Observed signal</th><th>Comparison</th><th>Current denominator</th></tr></thead><tbody>{signal_rows}</tbody></table><p class='notice'>Outcome maturity is unverified. Newer cohorts can have less follow-up. These exploratory comparisons do not establish causation and have not been adjusted for multiple comparisons.</p></section>
<section><h2>Turn this finding into a review</h2><ol><li><b>Confirm the finding with institutional research.</b> Check the cohort definition, missing values, and whether each cohort has had enough time for its outcomes to be recorded. A change in recorded retention does not by itself explain why students left.</li><li><b>Review the records with the student-success team.</b> In the demo, open Students with the same cohort and population selection to inspect the available academic history. These are historical synthetic records, not a current outreach list.</li><li><b>Agree on a next step and an owner.</b> Record a demo follow-up in a student profile to illustrate the workflow. These entries stay in that browser, are not included in this report, and do not contact anyone or update an institutional system. A completed review does not establish that an intervention improved retention.</li></ol><p>The Modeling page can illustrate budget and capacity assumptions for a hypothetical pilot. Its historical predictions are not ready for individual student decisions; the extract does not measure intervention effectiveness.</p></section>
<section><h2>Definitions and denominator rules</h2><ul>{definitions}</ul></section><section><h2>Quality checks for this selection</h2><ul>{quality}</ul></section>
<section><h2>Provenance and limits</h2><ul>{sources}</ul><p>Metric grain: student × entry cohort. The full source has {d['meta']['cohort_rows']:,} cohort records and {d['meta']['unique_students']:,} unique student IDs. Course joins require Student_GUID + Cohort. No institution identifier, intervention assignments, costs, or financial-aid file is supplied. These are extract measures, not official institutional or IPEDS statistics.</p><p><b>{SYNTHETIC}</b></p></section></main></body></html>"""
