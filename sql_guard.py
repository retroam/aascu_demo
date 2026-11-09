"""Bounded analytical SQL, not an arbitrary SQL runtime.

One aggregate or synthetic-record SELECT over one server-scoped view; no joins, CTEs, subqueries,
windows, casts or text transforms. New formulas, CASEs, groups and filters are
supported. The caller must obtain independent model approval before execute_sql;
both public SQL entry points independently enforce this deterministic boundary.
Explicit rows mode permits synthetic record browsing without aggregate suppression.
Small-cell suppression is NOT a comprehensive privacy boundary: eligible
denominators, differencing and inference still require analytical review.
"""
from contextlib import contextmanager
from functools import lru_cache
import math
import re
import sqlite3
import time

import sqlglot
from sqlglot import exp

import analytics
import foundations
import runtime_cache as cache

RESULT_CACHE = cache.TTLCache(capacity=128, ttl=300)

DATABASE = foundations.DATABASE
MAX_ROWS = 200
MAX_COLUMNS = 16
MAX_STRING = 200
MAX_SQL = 12000
MAX_NODES = 500
TIMEOUT_SECONDS = 2.0
INSTRUCTION_BUDGET = 20_000_000
SOURCE = "Synthetic normalized PDP · scoped cohort_records / course_records / attribute_records"
VIEWS = {
    "cohort_records": "student × entry cohort",
    "course_records": "course enrollment × student × entry cohort (joined on both keys); academic_year/academic_term describe the course term",
    "attribute_records": "student attribute × entry cohort; academic_year/academic_term describe the optional attribute term, not entry cohort. Attributes repeat across a student's entry cohorts. COUNT(DISTINCT student_id) counts students; COUNT(*) counts attribute/cohort records. Absent attributes are unreported, not false.",
}
FUNCTIONS = {"COUNT", "SUM", "AVG", "MIN", "MAX", "ROUND", "ABS", "COALESCE", "NULLIF"}
STUDENT = "student_age race ethnicity gender first_gen naspa_first_generation".split()
COHORT = ("cohort cohort_term enrollment_type enrollment_intensity_first_term math_placement "
          "english_placement dual_and_summer_enrollment pell_status_first_year attendance_status_term_1 "
          "credential_type_sought_year_1 gpa_group_term_1 gpa_group_year_1 credit_years_observed "
          "gateway_math_status gateway_english_status attempted_gateway_math_year1 "
          "attempted_gateway_english_year1 completed_gateway_math_year1 completed_gateway_english_year1 "
          "gateway_math_grade_y1 gateway_english_grade_y1 attempted_dev_math_y1 attempted_dev_english_y1 "
          "completed_dev_math_y1 completed_dev_english_y1 retention persistence time_to_credential").split()
COHORT += [f"number_of_credits_{kind}_yr_{year}" for year in range(1, 5) for kind in ("attempted", "earned")]
COURSE = ("attempt_number course_type math_or_english_gateway co_requisite_course grade "
          "number_of_credits_attempted number_of_credits_earned delivery_method core_course "
          "core_course_type core_competency_completed").split()
# Only these declared categorical columns may have observed domains enumerated.
CATEGORICAL = set(STUDENT + [c for c in COHORT if not c.startswith(("number_", "gpa_"))
                            and c not in {"credit_years_observed", "retention", "persistence", "time_to_credential"}]
                  + [c for c in COURSE if c not in {"attempt_number", "number_of_credits_attempted", "number_of_credits_earned"}]
                  + ["course_prefix", "academic_year", "academic_term", "attribute_key", "attribute_value"])


class SQLValidationError(ValueError):
    """A safe, actionable error suitable for a bounded model correction loop."""


def _filters(filters):
    """Use exactly the dashboard's filter validation."""
    try:
        return analytics.normalize_filters(filters)
    except (ValueError, TypeError) as error:
        raise SQLValidationError(str(error)) from None


def _origins(view):
    """Return the fixed analytical projection without free text or hidden IDs."""
    result = {"student_id": ("cohort_membership", "cm")}
    result.update({c: ("student", "s") for c in STUDENT})
    result.update({c: ("cohort_membership", "cm") for c in (COHORT if view != "attribute_records" else ["cohort"])})
    if view == "course_records":
        result.update({c: ("course_enrollment", "ce") for c in COURSE})
        result["course_prefix"] = ("course", "c")
        result["course_number"] = ("course", "c")
    if view == "attribute_records":
        result.update({c: ("student_attribute", "sa") for c in ("attribute_key", "attribute_value", "source")})
    if view != "cohort_records":
        result.update({c: ("term", "t") for c in ("academic_year", "academic_term", "sort_order")})
    return result


@contextmanager
def _connection(filters):
    """Build trusted views on a read-only file before locking down SQLite."""
    f = _filters(filters)
    db = sqlite3.connect(f"{DATABASE.resolve().as_uri()}?mode=ro", uri=True)
    try:
        conditions = []
        if f["cohort"] != "all":
            conditions.append("cm.cohort = '" + f["cohort"].replace("'", "''") + "'")
        population = {"full-time": "cm.enrollment_intensity_first_term = 'Full-Time'",
                      "part-time": "cm.enrollment_intensity_first_term = 'Part-Time'",
                      "pell": "cm.pell_status_first_year = 'Y'", "adult": "s.student_age = 'Older than 24'"}
        if f["population"] in population:
            conditions.append(population[f["population"]])
        for view in VIEWS:
            fields = ", ".join(f'{alias}."{name}" AS "{name}"' for name, (_, alias) in _origins(view).items())
            joins = "cohort_membership cm JOIN student s ON s.student_id = cm.student_id"
            if view == "course_records":
                joins += (" JOIN course_enrollment ce ON ce.student_id = cm.student_id AND ce.cohort = cm.cohort"
                          " LEFT JOIN course c ON c.course_id = ce.course_id"
                          " LEFT JOIN term t ON t.term_id = ce.term_id")
            elif view == "attribute_records":
                joins += " JOIN student_attribute sa ON sa.student_id = cm.student_id LEFT JOIN term t ON t.term_id = sa.term_id"
            where = " WHERE " + " AND ".join(conditions) if conditions else ""
            # Prevent flattening from moving COUNT(*) reads outside view provenance.
            db.execute(f"CREATE TEMP VIEW {view} AS SELECT {fields} FROM {joins}{where} LIMIT -1")
        db.execute("PRAGMA query_only = ON")
        yield db
    finally:
        db.close()


@lru_cache(maxsize=4)
def _metadata(path, modified, revision=None):
    """Read safe domains globally, so an empty UI scope is not an invalid code."""
    dictionary = {(x["table"], x["column"]): x for x in foundations.column_dictionary()}
    result = {}
    with _connection(None) as db:
        for view in VIEWS:
            columns = {}
            for name, (table, _) in _origins(view).items():
                field = foundations.schema_field(table, name)
                info = {"type": field["type"], "nullable": field["nullable"],
                        "semantics": dictionary.get((table, name), {}).get("description") or name,
                        "unknown_value": field["unknown_value"], "origin": {"table": table, "column": name}}
                definition = foundations.model_metadata().normalized_column(table, name)
                info.update(rules=definition["rules"], sources=definition["sources"])
                if name == "student_id":
                    info["semantics"] = "Synthetic student identifier. In aggregate mode use only COUNT(DISTINCT student_id); row browsing may select/filter it."
                if name in CATEGORICAL:
                    observed = [r[0] for r in db.execute(f'SELECT DISTINCT "{name}" FROM {view} WHERE "{name}" IS NOT NULL ORDER BY 1')]
                    declared = field["allowed_values"] or []
                    if field["unknown_value"] is not None:
                        declared = declared + [field["unknown_value"]]
                    info.update(observed_values=observed, dictionary_values=declared,
                                allowed_values=sorted(set(observed + declared)))
                if field["type"] == "bool":
                    info["range"] = [0, 1]
                for rule in definition["rules"]:
                    if "when" not in rule and rule.get("severity") == "error" and "minimum" in rule and "maximum" in rule:
                        info["range"] = [rule["minimum"], rule["maximum"]]
                columns[name] = info
            result[view] = {"grain": VIEWS[view],
                            "columns": columns}
    return result


def schema_catalog(filters=None):
    """Return JSON-safe schema, normalized domains and the SQL language contract."""
    import copy
    return {"filters": _filters(filters), "views": copy.deepcopy(_metadata(str(DATABASE), DATABASE.stat().st_mtime_ns, cache.key(cache.data_revision(DATABASE), cache.definition_revision()))),
            "normalized_model": foundations.normalized_model(),
            "allowed_functions": sorted(FUNCTIONS), "mandatory_n": "Aggregate mode only: COUNT(DISTINCT student_id) AS n",
            "max_result_columns": MAX_COLUMNS, "max_result_rows": MAX_ROWS, "min_group_size": analytics.MIN_CELL,
            "row_browsing": "Synthetic demo row browsing permits a nonaggregate SELECT with explicit fields, student_id, filters and ORDER BY; no n needed. Same views, scope, limits and read-only checks. Do not use row mode to answer aggregate questions or bypass suppression.",
            "language": "For aggregate mode: one aggregate SELECT from one approved view. No joins, CTEs, subqueries, windows, casts, text transforms, SELECT *, or identifiers outside distinct COUNT. Output expressions need unique aliases. GROUP BY expressions, CASE, arithmetic, WHERE, HAVING, ORDER BY and LIMIT are supported. Use exact normalized categorical codes; NULL is missing, UNKNOWN is a separate stored code. Dictionary codes are allowed even when absent from this extract; observed values are not numeric bounds.",
            "scope": "Views enforce selected cohort and population; SQL can only narrow them. threshold is context, not a row filter.",
            "privacy": "n < 20 rows are suppressed. This is not a comprehensive privacy boundary; eligible denominators and differencing/inference need independent review.",
            "source": SOURCE}


def _literal(node):
    """Decode a finite literal without SQLite coercions."""
    if isinstance(node, exp.Null):
        return None
    if isinstance(node, exp.Boolean):
        return int(node.this)
    if isinstance(node, exp.Neg) and isinstance(node.this, exp.Literal) and not node.this.is_string:
        return -_literal(node.this)
    if isinstance(node, exp.Literal):
        if node.is_string:
            return node.this
        value = float(node.this)
        if math.isfinite(value):
            return value
    raise SQLValidationError("Use literal values in categorical/boolean predicates; expressions and transforms cannot bypass domain checks.")


def _check_value(column, value, columns):
    """Validate a predicate literal against stored types and declared domains."""
    info = columns[column]
    if value is None:
        return
    if info["type"] == "str":
        if not isinstance(value, str):
            raise SQLValidationError(f"{column} needs a quoted text code.")
        if "allowed_values" in info and value not in info["allowed_values"]:
            choices = ", ".join(repr(v) for v in info["allowed_values"][:30])
            raise SQLValidationError(f"Unknown value for {column}. Use an exact normalized code: {choices}; use IS NULL for missing data.")
    elif isinstance(value, str):
        raise SQLValidationError(f"{column} needs a numeric literal, not quoted text (boolean codes are 0/1).")
    elif "range" in info and not info["range"][0] <= value <= info["range"][1]:
        raise SQLValidationError(f"{column} must be in {info['range']}.")
    elif info["type"] in {"bool", "int"} and value != int(value):
        raise SQLValidationError(f"{column} needs an integer code.")


def _type(node, columns):
    """Reject implicit text-to-number coercion in formulas and comparisons."""
    if isinstance(node, exp.Column):
        return "text" if columns[node.name]["type"] == "str" else "number"
    if isinstance(node, exp.Literal):
        _literal(node)
        return "text" if node.is_string else "number"
    if isinstance(node, exp.Null):
        return "null"
    if isinstance(node, exp.Boolean):
        return "number"
    if isinstance(node, (exp.Alias, exp.Paren, exp.Ordered)):
        return _type(node.this, columns)
    if isinstance(node, exp.Distinct):
        types = {_type(x, columns) for x in node.expressions} - {"null"}
        if len(types) > 1:
            raise SQLValidationError("DISTINCT arguments must have compatible types.")
        return next(iter(types), "null")
    if isinstance(node, exp.Count):
        return "number"
    if isinstance(node, exp.Case):
        outputs = [i.args["true"] for i in node.args["ifs"]]
        if node.args.get("default") is not None:
            outputs.append(node.args["default"])
        types = {_type(x, columns) for x in outputs} - {"null"}
        if len(types) > 1:
            raise SQLValidationError("CASE branches must have compatible types.")
        return next(iter(types), "null")
    if isinstance(node, (exp.Add, exp.Sub, exp.Mul, exp.Div, exp.Mod, exp.Neg, exp.Sum, exp.Avg, exp.Abs, exp.Round)):
        if any(_type(x, columns) == "text" for x in node.iter_expressions()):
            raise SQLValidationError("Arithmetic and numeric functions require numeric columns, not categorical text.")
        return "number"
    if isinstance(node, (exp.Min, exp.Max, exp.Coalesce, exp.Nullif)):
        types = {_type(x, columns) for x in node.iter_expressions()} - {"null"}
        if len(types) > 1:
            raise SQLValidationError("Function arguments must have compatible types.")
        return next(iter(types), "null")
    if isinstance(node, (exp.Where, exp.Having, exp.And, exp.Or, exp.Not, exp.If)):
        operands = [node.this] if isinstance(node, (exp.Where, exp.Having, exp.Not, exp.If)) else list(node.iter_expressions())
        if any(_type(x, columns) == "text" for x in operands):
            raise SQLValidationError("Conditions require comparisons, not implicit categorical-text truth values.")
    return "number"


def _predicates(tree, columns):
    """Check CASE/WHERE/HAVING predicates including reversed comparisons."""
    comparisons = (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Is, exp.Nullif)
    for case in tree.find_all(exp.Case):
        if case.this is not None:
            raise SQLValidationError("Use searched CASE WHEN column = value THEN ... END, not simple CASE.")
    for node in tree.walk():
        if isinstance(node, comparisons):
            sides = [node.this, node.expression]
        elif isinstance(node, exp.In):
            sides = [node.this, *node.expressions]
        elif isinstance(node, exp.Between):
            sides = [node.this, node.args["low"], node.args["high"]]
        else:
            continue
        for side in sides:
            # Aggregated expressions may be compared with numeric thresholds in HAVING.
            if any(isinstance(x, exp.AggFunc) for x in side.walk()):
                if _type(side, columns) == "text":
                    raise SQLValidationError("Compare categorical columns directly, not through MIN/MAX or other transforms.")
                continue
            cols = list(side.find_all(exp.Column))
            protected = [c for c in cols if columns[c.name]["type"] in {"str", "bool"} or "range" in columns[c.name]]
            if protected and not isinstance(side, exp.Column):
                raise SQLValidationError("Compare categorical/boolean columns directly to literal codes; casts and transformed predicates are not supported.")
            if isinstance(side, exp.Column):
                for other in sides:
                    if other is side:
                        continue
                    if isinstance(other, exp.Column):
                        if protected:
                            raise SQLValidationError("Compare categorical/boolean columns to literal codes, not other columns.")
                        if _type(side, columns) != _type(other, columns):
                            raise SQLValidationError("Compared columns must have compatible types.")
                    elif not list(other.find_all(exp.Column)) and not isinstance(other, exp.AggFunc):
                        _check_value(side.name, _literal(other), columns)
                    elif protected:
                        raise SQLValidationError("Compare categorical/boolean columns directly to literal codes.")
        types = {_type(side, columns) for side in sides} - {"null"}
        if len(types) > 1:
            raise SQLValidationError("Comparison operands must have compatible types; numeric codes must not be quoted.")


def validate_sql(sql, filters=None, *, rows=False):
    """Return validated original SQL, without executing the proposed SELECT."""
    catalog = schema_catalog(filters)
    if not isinstance(sql, str) or not sql.strip() or len(sql) > MAX_SQL:
        raise SQLValidationError(f"Provide one SELECT of at most {MAX_SQL} characters.")
    try:
        statements = sqlglot.parse(sql, read="sqlite")
    except (sqlglot.errors.SqlglotError, RecursionError):
        raise SQLValidationError("SQL could not be parsed; use one simple aggregate SELECT.") from None
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise SQLValidationError("Only one aggregate SELECT is allowed.")
    tree = statements[0]
    if len(tree.expressions) > MAX_COLUMNS:
        raise SQLValidationError(f"Return at most {MAX_COLUMNS} columns, including n.")
    nodes = list(tree.walk())
    if len(nodes) > MAX_NODES or any(n.depth > 50 for n in nodes):
        raise SQLValidationError("SQL is too complex; simplify the expressions.")
    allowed_nodes = (exp.Select, exp.From, exp.Table, exp.TableAlias, exp.Identifier, exp.Column,
                     exp.Alias, exp.Literal, exp.Null, exp.Boolean, exp.Distinct, exp.Star,
                     exp.Where, exp.Group, exp.Having, exp.Order, exp.Ordered, exp.Limit,
                     exp.Paren, exp.Add, exp.Sub, exp.Mul, exp.Div, exp.Mod, exp.Neg,
                     exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Is, exp.In,
                     exp.Between, exp.And, exp.Or, exp.Not, exp.Case, exp.If,
                     exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max, exp.Round, exp.Abs,
                     exp.Coalesce, exp.Nullif)
    if any(type(n) not in allowed_nodes for n in nodes) or len(list(tree.find_all(exp.Select))) != 1:
        raise SQLValidationError("Use one view and no joins, CTEs, subqueries, windows, casts, text transforms or unsupported functions.")
    if any(isinstance(n, exp.If) and not isinstance(n.parent, exp.Case) for n in nodes):
        raise SQLValidationError("Use searched CASE WHEN rather than IF/IIF.")
    tables = list(tree.find_all(exp.Table))
    if len(tables) != 1 or tables[0].name not in catalog["views"] or tables[0].db or tables[0].catalog:
        raise SQLValidationError("FROM must name an approved scoped view: " + ", ".join(VIEWS) + "; no database qualifier.")
    table = tables[0]
    columns = catalog["views"][table.name]["columns"]
    aliases = {}
    for projection in tree.expressions:
        name = projection.alias_or_name
        if not name or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name) or name.lower() in aliases:
            raise SQLValidationError("Give every output a unique simple alias (letters, digits, underscores).")
        value = projection.this if isinstance(projection, exp.Alias) else projection
        if name.lower() == "n" and name != "n":
            raise SQLValidationError("Use the exact lowercase alias n for the distinct-student count.")
        if not list(value.find_all(exp.Column)) and not any(isinstance(x.this, exp.Star) for x in value.find_all(exp.Count)):
            raise SQLValidationError("Every output must derive from source columns or COUNT(*), not constant findings.")
        if name.lower() in columns and not (isinstance(value, exp.Column) and value.name == name.lower()):
            raise SQLValidationError("Do not shadow an input column with an expression alias; choose a new output name.")
        aliases[name.lower()] = projection.this if isinstance(projection, exp.Alias) else projection
    # Resolve output aliases only in grouping/HAVING/ordering, before checking domains.
    for key in ("group", "having", "order"):
        clause = tree.args.get(key)
        if clause:
            for col in list(clause.find_all(exp.Column)):
                if not col.table and col.name not in columns and col.name.lower() in aliases:
                    col.replace(aliases[col.name.lower()].copy())
    if len(list(tree.walk())) > MAX_NODES:
        raise SQLValidationError("Expanded aliases make this query too complex; simplify it.")
    for col in tree.find_all(exp.Column):
        if col.name not in columns or (col.table and col.table != table.alias_or_name) or col.db or col.catalog:
            raise SQLValidationError(f"Unknown column or qualifier: {col.name[:64]}. Use columns from the selected catalog view.")
        if col.name == "student_id" and not rows:
            parent = col.parent
            if not (isinstance(parent, exp.Distinct) and len(parent.expressions) == 1 and isinstance(parent.parent, exp.Count)):
                raise SQLValidationError("student_id is allowed only inside COUNT(DISTINCT student_id).")
    n = aliases.get("n")
    if not rows and not (isinstance(n, exp.Count) and isinstance(n.this, exp.Distinct)
            and len(n.this.expressions) == 1 and isinstance(n.this.expressions[0], exp.Column)
            and n.this.expressions[0].name == "student_id"):
        raise SQLValidationError("Include the exact aggregate COUNT(DISTINCT student_id) AS n; a literal or transformed count is not valid.")
    for star in tree.find_all(exp.Star):
        if not isinstance(star.parent, exp.Count):
            raise SQLValidationError("SELECT * is not allowed; name analytical columns explicitly.")
    if tree.args.get("distinct"):
        raise SQLValidationError("Use GROUP BY, not SELECT DISTINCT.")
    for aggregate in tree.find_all(exp.AggFunc):
        if aggregate.expressions or (isinstance(aggregate.this, exp.Distinct) and len(aggregate.this.expressions) != 1):
            raise SQLValidationError("Aggregate functions require exactly one argument; scalar MIN/MAX cannot stand in for aggregates.")
        if any(isinstance(x, exp.AggFunc) for child in aggregate.iter_expressions() for x in child.walk()):
            raise SQLValidationError("Nested aggregates are not supported.")
    group = tree.args.get("group")
    group_exprs = group.expressions if group else []
    if any(isinstance(x, exp.Literal) and not x.is_string for x in group_exprs):
        raise SQLValidationError("GROUP BY must use named dimensions or expressions, not positional numbers.")
    for clause in (tree.args.get("where"), group):
        if clause and any(isinstance(x, exp.AggFunc) for x in clause.walk()):
            raise SQLValidationError("Aggregates belong in SELECT, HAVING or ORDER BY, not WHERE/GROUP BY.")
    def grouped(node):
        """Reject SQLite's arbitrary bare-column results in aggregate queries."""
        if isinstance(node, exp.AggFunc) or any(node == g for g in group_exprs):
            return
        if isinstance(node, exp.Column):
            raise SQLValidationError("Every nonaggregated output/order/HAVING column must be in GROUP BY.")
        for child in node.iter_expressions():
            grouped(child)
    if rows and (list(tree.find_all(exp.AggFunc)) or group or tree.args.get("having")):
        raise SQLValidationError("Row browsing cannot contain aggregates, GROUP BY or HAVING; use aggregate mode.")
    for expression in ([] if rows else [*tree.expressions, tree.args.get("having"), tree.args.get("order")]):
        if expression:
            grouped(expression)
    for node in tree.walk():
        _type(node, columns)
    _predicates(tree, columns)
    limit = tree.args.get("limit")
    if limit:
        value = _literal(limit.expression)
        if not isinstance(value, (int, float)) or value < 0 or value != int(value) or value > MAX_ROWS:
            raise SQLValidationError(f"LIMIT must be an integer from 0 to {MAX_ROWS}; omit it to use the server cap.")
    # Validation uses an alias-expanded copy; execute precisely the submitted SQL.
    return sql.strip()


def _lockdown(db, view):
    """Allow only reads through the selected trusted view and safe functions."""
    def authorizer(action, arg1, arg2, database, origin):
        """Deny every action not needed by an approved aggregate SELECT."""
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").upper() in FUNCTIONS:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ:
            if arg1 == view and database == "temp":
                return sqlite3.SQLITE_OK
            if origin == view and database == "main" and arg1 in {"student", "cohort_membership", "course_enrollment", "course", "term", "student_attribute"}:
                return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY
    db.set_authorizer(authorizer)
    deadline = time.monotonic() + TIMEOUT_SECONDS
    remaining = INSTRUCTION_BUDGET
    def progress():
        """Stop long scans by both elapsed time and VM instruction count."""
        nonlocal remaining
        remaining -= 1000
        return int(remaining <= 0 or time.monotonic() > deadline)
    db.set_progress_handler(progress, 1000)


def execute_sql(sql, filters=None, *, rows=False):
    """Revalidate approved SQL and return bounded, small-cell-suppressed results."""
    row_mode = rows
    revision = cache.data_revision(DATABASE)
    validated = validate_sql(sql, filters, rows=row_mode)
    result_key = cache.key(revision, validated, _filters(filters), row_mode, analytics.MIN_CELL,
                           cache.file_revision(__file__))
    cached = RESULT_CACHE.get(result_key)
    if cached is not None:
        return cached
    view = next(sqlglot.parse_one(validated, read="sqlite").find_all(exp.Table)).name
    try:
        with _connection(filters) as db:
            _lockdown(db, view)
            cursor = db.execute(validated)
            columns = [item[0] for item in cursor.description]
            n_index = None if row_mode else next(i for i, name in enumerate(columns) if name.lower() == "n")
            rows, suppressed, truncated = [], 0, False
            for row in cursor:
                if not row_mode and row[n_index] < analytics.MIN_CELL:
                    suppressed += 1
                    continue
                if len(rows) == MAX_ROWS:
                    truncated = True
                    break
                if any(isinstance(v, float) and not math.isfinite(v) for v in row):
                    raise SQLValidationError("The formula produced a non-finite number; bound inputs or revise the arithmetic.")
                if any(isinstance(v, int) and abs(v) > 9007199254740991 for v in row):
                    raise SQLValidationError("An integer exceeds the browser's exact numeric range; use smaller units before displaying it.")
                rows.append(dict(zip(columns, [v[:MAX_STRING] if isinstance(v, str) else v for v in row])))
            result = {"columns": columns, "rows": rows, "suppressed_rows": suppressed, "truncated": truncated, "source": SOURCE}
            if revision == cache.data_revision(DATABASE):
                RESULT_CACHE.put(result_key, result)
            return result
    except sqlite3.Error as error:
        if "interrupt" in str(error).lower():
            raise SQLValidationError("Query exceeded the read-only time/instruction budget; simplify it or narrow the scope.") from None
        raise SQLValidationError("SQLite could not execute this approved query; check aggregate/function arguments and simplify the SQL.") from None
