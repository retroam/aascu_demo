"""Expected answers for the SQL-agent eval, computed from the app's deterministic metrics.

Ground truth comes from analytics.py (the same functions the dashboard uses), never from a model.
"""
from __future__ import annotations

import analytics as a

CORE = set(a.CONTEXT_METRICS)
GAP_BREAKDOWN = {"race": "race", "gender": "gender", "pell": "pell"}


def scope(case):
    """UI filters, then any narrowing the question itself asks for."""
    expect = case["expect"]
    f = a.normalize_filters(dict({"cohort": "all", "population": "all", "threshold": 24}, **case.get("filters", {})))
    f = dict(f, **expect.get("scope", {}))
    if "threshold" in expect:
        f["threshold"] = expect["threshold"]
    return a.normalize_filters(f)


def value(metric, filters):
    """Percent value and eligible denominator, or None when suppressed/unavailable."""
    if metric in CORE:
        row = a.metric(a.filter_data(filters), metric, filters["threshold"])
    else:
        row = next(m for m in a.get_shared_measures(filters)["metrics"] if m["id"] == metric)
    if row.get("value") is None or row.get("status", "ok") != "ok":
        return None
    return {"value": round(float(row["value"]), 4), "numerator": row.get("numerator"), "denominator": row.get("denominator")}


def _gap_rows(metric, by, filters):
    data = a.get_gaps(dict(filters, measure=metric, breakdown=GAP_BREAKDOWN[by]))
    for row in data["rows"]:
        visible = (not row["suppressed"] and row["status"] == "ok"
                   and (row.get("denominator") or 0) >= 20 and (row.get("comparison_denominator") or 0) >= 20)
        yield " / ".join(row["group_values"]), row, visible


def expected(case):
    kind = case["expect"]["kind"]
    if kind in ("refuse", "help"):
        return {"kind": kind}
    metric = case["expect"]["metric"]
    f = scope(case)
    if kind in ("scalar", "refuse_or_true"):
        out = {"kind": kind, "metric": metric, "filters": f, "value": value(metric, f)}
        if kind == "refuse_or_true":
            out["forbid_value"] = case["expect"]["forbid_value"]
        return out
    by = case["expect"]["by"]
    groups = {}
    if kind == "groups" and by == "population":
        for population in case["expect"]["groups"]:
            groups[population] = value(metric, dict(f, population=population))
    elif kind == "groups" and by == "cohort":
        for cohort in a.COHORTS:
            groups[cohort] = value(metric, dict(f, cohort=cohort))
    elif kind == "groups":
        # get_gaps reports group rates as 0..1 fractions; the eval compares percentages.
        for label, row, visible in _gap_rows(metric, by, f):
            groups[label] = {"value": round(100 * float(row["metric_rate"]), 4), "denominator": row["denominator"]} if visible else None
    elif kind == "gaps":
        for label, row, visible in _gap_rows(metric, by, f):
            groups[label] = {"value": round(float(row["gap_pts"]), 4), "group_rate": round(100 * float(row["metric_rate"]), 4),
                             "comparison_rate": round(100 * float(row["comparison_rate"]), 4), "denominator": row["denominator"]} if visible else None
    elif kind == "diff":
        # A plain two-group difference ("how far apart are A and B"), not group-vs-everyone-else.
        rates = {label: 100 * float(row["metric_rate"]) for label, row, visible in _gap_rows(metric, by, f) if visible}
        a_label, b_label = case["expect"]["a"], case["expect"]["b"]
        return {"kind": kind, "metric": metric, "by": by, "filters": f, "a": a_label, "b": b_label,
                "rates": {a_label: round(rates[a_label], 4), b_label: round(rates[b_label], 4)},
                "value": round(abs(rates[a_label] - rates[b_label]), 4)}
    else:
        raise ValueError(f"Unknown expectation kind: {kind}")
    return {"kind": kind, "metric": metric, "by": by, "filters": f, "groups": groups}
