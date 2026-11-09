"""Reproducible historical models and scenario arithmetic for the PDP demo.

Uses the workspace's existing NumPy / pandas / SciPy installation. No network,
LLM, credentials, student-level outputs, or source-data writes are involved.
All estimates describe synthetic records, not real students or institutions.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import math

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit
from scipy.stats import rankdata


RAW = Path(__file__).resolve().parents[2] / "pdp-datathon-starter/data/raw/pdp_cohort_data.csv"
SYNTHETIC_NOTE = "These results describe mock data, not real students or institutions."
TARGET = "Retention"
PREDICTOR_COLUMNS = (
    "Enrollment_Intensity_First_Term", "Enrollment_Type", "Math_Placement",
    "English_Placement", "GPA_Group_Term_1",
)
COHORTS = ("2021-22", "2022-23", "2023-24", "2024-25")
POPULATIONS = ("all", "full-time", "part-time", "pell", "adult")
# Categories are defined from the supplied dictionary, never learned on the test set.
CATEGORIES = {
    "Enrollment_Intensity_First_Term": ("Part-Time", "Full-Time", "Unknown"),
    "Enrollment_Type": ("First-Time", "Transfer-In", "Re-admit", "Unknown"),
    "Math_Placement": ("C", "N", "UK"),
    "English_Placement": ("C", "N", "UK"),
}
DISPLAY = {
    "Enrollment_Intensity_First_Term": "First-term enrollment",
    "Enrollment_Type": "Entry type",
    "Math_Placement": "Math placement",
    "English_Placement": "English placement",
}
PLACEMENT = {"C": "college ready", "N": "not college ready", "UK": "unknown"}


@lru_cache(maxsize=1)
def _raw_data():
    """Use the same normalized cohort records as the dashboard."""
    from foundations import cohort_frame
    return cohort_frame()


def _split_data(data):
    """Keep each student's latest entry record, then split by entry cohort."""
    cohorts = sorted(data.Cohort.unique())
    known = data[data[TARGET].isin(["0", "1"])].copy()
    distinct = known.sort_values("Cohort", kind="stable").drop_duplicates("Student_GUID", keep="last")
    train = distinct[distinct.Cohort.isin(cohorts[:-2])].copy()
    validation = distinct[distinct.Cohort.isin(cohorts[-2:-1])].copy()
    test = distinct[distinct.Cohort.isin(cohorts[-1:])].copy()
    return train, validation, test, len(known) - len(distinct)


def _gpa(data):
    gpa = pd.to_numeric(data["GPA_Group_Term_1"], errors="coerce")
    return gpa.where(gpa.between(0, 4))


def _preprocessor(train):
    gpa = _gpa(train)
    median = float(gpa.median()) if gpa.notna().any() else 2.0
    filled = gpa.fillna(median)
    return {"gpa_median": median, "gpa_mean": float(filled.mean()),
            "gpa_std": max(float(filled.std(ddof=0)), 1e-8)}


def _matrix(data, preprocessor):
    columns = [np.ones(len(data))]
    names = [{"name": "Intercept", "column": None, "reference": None}]
    for column, levels in CATEGORIES.items():
        values = data[column].where(data[column].isin(levels), levels[-1])
        reference = PLACEMENT.get(levels[0], levels[0])
        for level in levels[1:]:
            columns.append(values.eq(level).to_numpy(dtype=float))
            names.append({"name": f"{DISPLAY[column]}: {PLACEMENT.get(level, level)}",
                          "column": column, "reference": reference})
    gpa = _gpa(data)
    columns.append(((gpa.fillna(preprocessor["gpa_median"]) - preprocessor["gpa_mean"])
                    / preprocessor["gpa_std"]).to_numpy(dtype=float))
    names.append({"name": "First-term GPA (+1 training standard deviation)",
                  "column": "GPA_Group_Term_1", "reference": "continuous, training-standardized"})
    columns.append(gpa.isna().to_numpy(dtype=float))
    names.append({"name": "First-term GPA: missing", "column": "GPA_Group_Term_1",
                  "reference": "reported GPA"})
    return np.column_stack(columns), names


def _fit_logistic(x, y, penalty):
    """L2-regularized binary log loss; the intercept is unpenalized."""
    regularization = np.ones(x.shape[1]) * penalty
    regularization[0] = 0.0

    def objective(beta):
        z = x @ beta
        loss = np.logaddexp(0, z).sum() - np.dot(y, z) + 0.5 * np.dot(regularization, beta * beta)
        gradient = x.T @ (expit(z) - y) + regularization * beta
        return loss, gradient

    result = minimize(objective, np.zeros(x.shape[1]), jac=True, method="L-BFGS-B",
                      options={"maxiter": 400, "ftol": 1e-11, "gtol": 1e-6})
    if not result.success or not np.isfinite(result.x).all():
        raise RuntimeError("The historical model did not converge; no scores are available.")
    return result.x


def _auc(y, probability):
    positives = y == 1
    n_pos = int(positives.sum())
    n_neg = len(y) - n_pos
    if not n_pos or not n_neg:
        return None
    # Average ranks correctly handle equal predictions.
    value = (rankdata(probability)[positives].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
    return float(value)


def _scores(y, probability, baseline):
    return {
        "rows": int(len(y)), "auc": _auc(y, probability),
        "brier": float(np.mean((probability - y) ** 2)),
        "baseline_brier": float(np.mean((baseline - y) ** 2)),
        "observed_retention": float(y.mean() * 100),
        "predicted_retention": float(probability.mean() * 100),
        "calibration_gap": float((probability.mean() - y.mean()) * 100),
    }


@lru_cache(maxsize=1)
def _model_bundle():
    """Fit only when chronological splits support a meaningful held-out evaluation."""
    cohorts = sorted(_raw_data().Cohort.unique())
    train, validation, test, removed = _split_data(_raw_data())
    if len(cohorts) < 3 or any(len(part) < 50 or part[TARGET].nunique() < 2 for part in (train, validation, test)):
        return ({"available": False, "reason": "Modeling needs at least three entry cohorts, with 50 known outcomes and both retention classes in each training, validation, and test split. This dataset does not meet those requirements.", "cohorts": cohorts}, None)
    preprocessor = _preprocessor(train)
    x_train, names = _matrix(train, preprocessor)
    x_validation, _ = _matrix(validation, preprocessor)
    x_test, _ = _matrix(test, preprocessor)
    y_train = train[TARGET].to_numpy(dtype=float)
    y_validation = validation[TARGET].to_numpy(dtype=float)
    y_test = test[TARGET].to_numpy(dtype=float)
    choices = []
    for penalty in (0.1, 1.0, 10.0, 100.0):
        try:
            beta = _fit_logistic(x_train, y_train, penalty)
        except RuntimeError:
            return ({"available": False, "reason": "The model did not converge for this dataset. No model or scenario result is available.", "cohorts": cohorts}, None)
        validation_predictions = expit(x_validation @ beta)
        choices.append((float(np.mean((validation_predictions - y_validation) ** 2)), penalty, beta))
    _, penalty, beta = min(choices, key=lambda item: item[0])
    prediction = expit(x_test @ beta)
    validation_prediction = expit(x_validation @ beta)
    baseline = float(y_train.mean())
    features = []
    for name, coefficient in zip(names[1:], beta[1:]):
        features.append({**name, "coefficient": float(coefficient),
                         "odds_ratio": float(np.exp(coefficient)),
                         "interpretation": "Conditional association with retention."})
    features.sort(key=lambda feature: abs(feature["coefficient"]), reverse=True)

    risk = 1 - prediction
    risk_bands = []
    for band_id, label, lo, hi in (("high", "Higher support priority", .65, 1.01),
                                 ("medium", "Moderate support priority", .35, .65),
                                 ("low", "Lower support priority", 0, .35)):
        mask = (risk >= lo) & (risk < hi)
        n = int(mask.sum())
        risk_bands.append({"id": band_id, "label": label, "n": n,
                           "share": n / len(test) * 100, "risk_min": lo * 100,
                           "risk_max": min(hi * 100, 100),
                           "mean_risk": float(risk[mask].mean() * 100) if n >= 20 else None,
                           "observed_retention": float(y_test[mask].mean() * 100) if n >= 20 else None,
                           "suppressed": 0 < n < 20})

    calibration = []
    for i in range(5):
        mask = (prediction >= i / 5) & (prediction < (i + 1) / 5)
        n = int(mask.sum())
        calibration.append({"bin": f"{i * 20}–{(i + 1) * 20}%", "n": n,
                            "predicted": float(prediction[mask].mean() * 100) if n >= 20 else None,
                            "observed": float(y_test[mask].mean() * 100) if n >= 20 else None,
                            "suppressed": n < 20})

    # Descriptive held-out subgroup checks. These are not claims of fairness.
    subgroup_checks = []
    for column in ("Enrollment_Intensity_First_Term", "Student_Age", "Pell_Status_First_Year"):
        for value in sorted(test[column].unique()):
            mask = test[column].eq(value).to_numpy()
            n = int(mask.sum())
            subgroup_checks.append({"column": column, "group": value, "n": n,
                                    "brier": float(np.mean((prediction[mask] - y_test[mask]) ** 2)) if n >= 20 else None,
                                    "predicted_retention": float(prediction[mask].mean() * 100) if n >= 20 else None,
                                    "observed_retention": float(y_test[mask].mean() * 100) if n >= 20 else None,
                                    "suppressed": n < 20})

    output = {
        "available": True,
        "name": "First-term retention model", "status": "Historical evaluation", "deployment_ready": False,
        "description": "Regularized logistic regression evaluated on a later, untouched cohort.",
        "target": "Recorded retention at the cohort institution by year two (including qualifying credentials).",
        "prediction_time": "Prediction point: end of first term.",
        "training": {"cohorts": cohorts[:-2], "rows": len(train), "retention_rate": baseline * 100},
        "validation": {"cohorts": cohorts[-2:-1], **_scores(y_validation, validation_prediction, baseline)},
        "test": {"cohort": cohorts[-1], **_scores(y_test, prediction, baseline)},
        "split": {"train_n": len(train), "validation_n": len(validation), "test_n": len(test),
                  "removed_overlap_rows": removed, "student_overlap": 0,
                  "rule": "Keep each Student_GUID's latest cohort record before splitting chronologically."},
        "features": features, "predictor_columns": list(PREDICTOR_COLUMNS),
        "risk_bands": risk_bands, "calibration": calibration, "subgroup_checks": subgroup_checks,
        "parameters": {"l2_penalty": penalty, **preprocessor,
                       "selection": "Lowest validation Brier score among penalties 0.1, 1, 10, 100."},
        "methodology": [
            f"Train on {', '.join(cohorts[:-2])}; select regularization on {cohorts[-2]}; evaluate once on {cohorts[-1]}.",
            "Fit GPA imputation and scaling only on training rows. Preserve unknown categories explicitly.",
            "Exclude year-one GPA, year-one credits, credentials, and later outcomes from the predictors.",
            "AUC measures ranking (0.5 is random); Brier measures probability error (lower is better).",
            "Baseline Brier uses one probability: the retention rate of the training cohorts.",
            "Support bands use predicted nonretention: high ≥65%, medium 35–65%, low <35%.",
        ],
        "limitations": [
            "This model uses a synthetic extract and requires validation before use with real students.",
            "The extract does not establish outcome completeness for the latest cohort; observed labels may be immature.",
            "A static extract cannot verify when each predictor was available; a deployment requires point-in-time data validation.",
            "Probabilities describe the historical test cohort.",
            "Model coefficients describe conditional associations. Intervention effects require separate evaluation.",
            "Subgroup diagnostics measure prediction error. Deployment requires a broader review of fairness and model suitability.",
        ],
        "synthetic": True, "disclaimer": SYNTHETIC_NOTE,
    }
    return output, prediction


def get_model():
    """Return aggregate evaluation only. Never return identifiers or individual scores."""
    return _model_bundle()[0]


def _number(payload, key, default, minimum, maximum, integer=False):
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{key} must be a finite number.")
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be a finite number.") from None
    if not math.isfinite(value) or value < minimum or value > maximum:
        raise ValueError(f"{key} must be between {minimum:g} and {maximum:g}.")
    if integer and not value.is_integer():
        raise ValueError(f"{key} must be a whole number.")
    return int(value) if integer else value


def get_scenario(payload):
    """Budget-constrained outreach arithmetic with an explicitly assumed lift.

    This is a planning tool: it does not learn treatment efficacy from the model.
    The higher-risk eligible group is ranked by predicted nonretention.
    """
    if not isinstance(payload, dict):
        raise ValueError("Scenario input must be an object.")
    allowed = {"capacity", "budget", "cost_per_student", "assumed_lift", "target"}
    if set(payload) - allowed:
        raise ValueError("Unsupported scenario field: " + ", ".join(sorted(set(payload) - allowed)))
    capacity = _number(payload, "capacity", 250, 0, 1_000_000, integer=True)
    budget = _number(payload, "budget", 25000, 0, 1_000_000_000)
    cost_per_student = _number(payload, "cost_per_student", 100, .01, 1_000_000)
    assumed_lift = _number(payload, "assumed_lift", 8, 0, 100)
    target = payload.get("target", "high")
    if target not in ("high", "all"):
        raise ValueError("target must be 'high' or 'all'.")
    model, prediction = _model_bundle()
    if not model["available"]:
        return {"available": False, "reason": model["reason"]}
    eligible = prediction[(1 - prediction) >= .65] if target == "high" else prediction
    ranked = np.sort(eligible)  # Highest predicted nonretention first.
    affordable = math.floor((budget + 1e-9) / cost_per_student)
    reach = min(capacity, affordable, len(ranked))
    selected = ranked[:reach]
    baseline_retained = float(selected.sum())
    additional = reach * assumed_lift / 100
    if additional + baseline_retained > reach + 1e-9:
        raise ValueError("The assumed lift would exceed 100% expected retention for the selected group; reduce it.")
    cost = reach * cost_per_student
    return {
        "target": target, "target_label": "Higher support priority" if target == "high" else "All held-out students",
        "eligible_students": len(ranked), "capacity": capacity, "budget": budget,
        "cost_per_student": cost_per_student, "assumed_lift": assumed_lift,
        "reach": reach, "cost": round(cost, 2), "budget_remaining": round(budget - cost, 2),
        "expected_additional_retained": additional,
        "baseline_expected_retained": baseline_retained,
        "scenario_expected_retained": baseline_retained + additional,
        "baseline_retention_rate": baseline_retained / reach * 100 if reach else None,
        "scenario_retention_rate": (baseline_retained + additional) / reach * 100 if reach else None,
        "binding_constraint": "No eligible students" if not len(ranked) else min(
            ((capacity, "Staff capacity"), (affordable, "Available budget"), (len(ranked), "Eligible population"))
        )[1],
        "recommendation": "Start with a small, evaluated outreach pilot; choose the support with institutional staff and student input.",
        "assumptions": [
            "You supply the assumed effect size and cost per student.",
            "Assumes every reached student participates and the same average percentage-point lift applies.",
            "Expected additional retained = reached students × assumed lift / 100; fractional counts are expectations.",
            f"Uses the fixed {model['test']['cohort']} held-out cohort, independently of dashboard filters.",
            "The ranking illustrates capacity allocation and requires validation before use with real students.",
        ],
        "cohort": model["test"]["cohort"], "synthetic": True, "disclaimer": SYNTHETIC_NOTE,
    }


ASSOCIATION_LIMITATIONS = [
    "The comparison describes observed enrollment groups. Causal effects require an evaluation design.",
    "No intervention assignment, support exposure, treatment dates, finances, or employment constraints are available.",
    "Adjustment uses entry cohort, age band, and entry type; it cannot remove unmeasured confounding.",
    "First-term GPA is excluded from adjustment because it may follow enrollment intensity.",
    "Only strata with at least 20 full-time and 20 part-time records enter the adjusted estimate; its population differs from the raw comparison.",
    "95% intervals use 2,000 seeded binomial bootstrap draws with fixed stratum counts to quantify sampling variability.",
    "Latest-cohort outcome completeness is unverified; synthetic patterns are not institutional findings.",
]


def _association_population(filters):
    filters = filters or {}
    cohort = filters.get("cohort", "all")
    population = filters.get("population", "all")
    if cohort not in ("all", *_raw_data().Cohort.unique()):
        raise ValueError("Unsupported cohort.")
    if population not in POPULATIONS:
        raise ValueError("Unsupported population.")
    data = _raw_data()
    if cohort != "all":
        data = data[data.Cohort.eq(cohort)]
    if population == "full-time":
        data = data[data.Enrollment_Intensity_First_Term.eq("Full-Time")]
    elif population == "part-time":
        data = data[data.Enrollment_Intensity_First_Term.eq("Part-Time")]
    elif population == "pell":
        data = data[data.Pell_Status_First_Year.eq("Y")]
    elif population == "adult":
        data = data[data.Student_Age.eq("Older than 24")]
    known = data[data.Retention.isin(["0", "1"]) & data.Enrollment_Intensity_First_Term.isin(["Full-Time", "Part-Time"])].copy()
    independent = known.sort_values("Cohort", kind="stable").drop_duplicates("Student_GUID", keep="last")
    return independent, len(known) - len(independent), len(data) - len(known)


@lru_cache(maxsize=32)
def _association_cached(cohort, population):
    data, removed_duplicates, excluded_unknown = _association_population({"cohort": cohort, "population": population})
    output = {
        "available": False, "raw_gap": None, "adjusted_gap": None, "raw_ci": None, "adjusted_ci": None,
        "full_time_rate": None, "part_time_rate": None, "n": len(data), "overlap_n": 0,
        "coverage_pct": 0.0, "strata": 0, "full_time_n": 0, "part_time_n": 0,
        "removed_duplicate_students": removed_duplicates, "excluded_unknown": excluded_unknown,
        "comparison": "Full-time minus part-time retention, in percentage points.",
        "method": "Direct standardization within shared cohort × age-band × entry-type strata.",
        "adjustment_columns": ["Cohort", "Student_Age", "Enrollment_Type"],
        "limitations": ASSOCIATION_LIMITATIONS,
        "dag": {
            "nodes": [
                {"id": "baseline", "label": "Entry background", "kind": "observed"},
                {"id": "intensity", "label": "Enrollment intensity", "kind": "exposure"},
                {"id": "gpa", "label": "First-term GPA", "kind": "mediator"},
                {"id": "retention", "label": "Retention", "kind": "outcome"},
                {"id": "unmeasured", "label": "Work, finances & support", "kind": "unmeasured"},
            ],
            "edges": [["baseline", "intensity"], ["baseline", "retention"],
                      ["intensity", "gpa"], ["gpa", "retention"], ["intensity", "retention"],
                      ["unmeasured", "intensity"], ["unmeasured", "retention"]],
            "caption": "Hypothesized relationships to guide study design.",
        },
        "causal_readiness": "Not identified",
        "next_step": "Define a support intervention and outcome window; collect exposure, eligibility, timing, and key confounders before evaluating its effect.",
        "synthetic": True, "disclaimer": SYNTHETIC_NOTE,
    }
    full = data[data.Enrollment_Intensity_First_Term.eq("Full-Time")]
    part = data[data.Enrollment_Intensity_First_Term.eq("Part-Time")]
    output.update(full_time_n=len(full), part_time_n=len(part))
    if len(full) < 20 or len(part) < 20:
        output["reason"] = "Both enrollment groups need at least 20 records. Choose all students, Pell recipients, or adult learners to compare groups."
        return output
    full_rate = full.Retention.astype(float).mean()
    part_rate = part.Retention.astype(float).mean()
    rng = np.random.default_rng(20261102)
    draws = 2000
    raw_draws = (rng.binomial(len(full), full_rate, draws) / len(full)
                 - rng.binomial(len(part), part_rate, draws) / len(part)) * 100
    output.update(raw_gap=float((full_rate - part_rate) * 100),
                  raw_ci=np.quantile(raw_draws, [.025, .975]).tolist(),
                  full_time_rate=float(full_rate * 100), part_time_rate=float(part_rate * 100))
    supported = []
    for _, stratum in data.groupby(["Cohort", "Student_Age", "Enrollment_Type"], sort=True):
        f = stratum[stratum.Enrollment_Intensity_First_Term.eq("Full-Time")]
        p = stratum[stratum.Enrollment_Intensity_First_Term.eq("Part-Time")]
        if len(f) >= 20 and len(p) >= 20:
            supported.append((len(f), len(p), float(f.Retention.astype(float).mean()),
                              float(p.Retention.astype(float).mean())))
    overlap_n = sum(nf + npart for nf, npart, _, _ in supported)
    if not overlap_n:
        output["reason"] = "No shared stratum contains at least 20 records in each enrollment group; adjustment is unavailable."
        return output
    adjusted_draws = np.zeros(draws)
    adjusted_full = 0.0
    adjusted_part = 0.0
    for nf, npart, pf, pp in supported:
        weight = (nf + npart) / overlap_n
        adjusted_full += weight * pf
        adjusted_part += weight * pp
        adjusted_draws += weight * (rng.binomial(nf, pf, draws) / nf - rng.binomial(npart, pp, draws) / npart) * 100
    output.update(available=True, adjusted_gap=float((adjusted_full - adjusted_part) * 100),
                  adjusted_ci=np.quantile(adjusted_draws, [.025, .975]).tolist(),
                  adjusted_full_time_rate=adjusted_full * 100, adjusted_part_time_rate=adjusted_part * 100,
                  overlap_n=overlap_n, coverage_pct=overlap_n / len(data) * 100, strata=len(supported))
    return output


def get_association(filters=None):
    filters = filters or {}
    # Validate even cached requests, and retain only supported dimensions in cache keys.
    cohort = filters.get("cohort", "all")
    population = filters.get("population", "all")
    if cohort not in ("all", *_raw_data().Cohort.unique()) or population not in POPULATIONS:
        raise ValueError("Unsupported cohort or population.")
    return _association_cached(cohort, population)
