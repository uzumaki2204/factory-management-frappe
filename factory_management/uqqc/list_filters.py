"""Resolve Factory Device Link filters against device IDs and displayed names."""

import json

import frappe
from frappe.desk import reportview


DEVICE_LINK_DOCTYPES = {"QC Favorite", "QC Inspection Event", "UQQC Inspection Event"}
DEVICE_DOCTYPE = "Factory Device"
NO_MATCHING_DEVICE = "__no_matching_factory_device__"
DEVICE_QUERY_PAGE_SIZE = 500
DEVICE_FILTER_OPERATORS = {"in", "not in", "like", "not like"}


def _parse_filters(raw_filters):
    if isinstance(raw_filters, str):
        try:
            return json.loads(raw_filters)
        except json.JSONDecodeError:
            return None
    return raw_filters


def _device_filter_cache():
    cache = getattr(frappe.local, "factory_device_link_filter_cache", None)
    if cache is None:
        cache = {}
        frappe.local.factory_device_link_filter_cache = cache
    return cache


def _paged_device_names(filters):
    names = []
    start = 0
    while True:
        page = frappe.get_list(
            DEVICE_DOCTYPE,
            filters=filters,
            fields=["name"],
            order_by="name asc",
            start=start,
            page_length=DEVICE_QUERY_PAGE_SIZE,
        )
        names.extend(row["name"] for row in page)
        if len(page) < DEVICE_QUERY_PAGE_SIZE:
            break
        start += DEVICE_QUERY_PAGE_SIZE
    return names


def _matching_device_names(pattern):
    cache = _device_filter_cache()
    cache_key = ("like", pattern)
    if cache_key not in cache:
        cache[cache_key] = _paged_device_names({"device_name": ["like", pattern]})
    return cache[cache_key]


def _filter_values(value):
    """Normalize Frappe's list value and tolerate a comma-separated filter value."""
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, (list, tuple)):
            value = decoded
        else:
            value = value.split(",")
    elif not isinstance(value, (list, tuple, set)):
        value = [value]

    return list(dict.fromkeys(
        str(item).strip()
        for item in value
        if item is not None and not isinstance(item, (dict, list, tuple, set)) and str(item).strip()
    ))


def _matching_device_names_in(values):
    values = _filter_values(values)
    cache = _device_filter_cache()
    cache_key = ("in", tuple(sorted(values)))
    if cache_key in cache:
        return cache[cache_key]

    names = set()
    for start in range(0, len(values), DEVICE_QUERY_PAGE_SIZE):
        batch = values[start:start + DEVICE_QUERY_PAGE_SIZE]
        # A filter can contain the Frappe document ID or the visible device_name.
        names.update(_paged_device_names({"name": ["in", batch]}))
        names.update(_paged_device_names({"device_name": ["in", batch]}))

    cache[cache_key] = sorted(names)
    return cache[cache_key]


def _replacement(value, operator):
    operator = " ".join(str(operator).lower().split())
    is_negative = operator in {"not in", "not like"}

    if operator in {"like", "not like"}:
        if not isinstance(value, str) or not value:
            return None
        names = _matching_device_names(value)
    elif operator in {"in", "not in"}:
        names = _matching_device_names_in(value)
        if not names:
            # Device Link fields are mandatory. This sentinel keeps empty IN/NOT IN
            # filters valid on MariaDB while matching no possible Factory Device ID.
            return ("!=" if is_negative else "="), NO_MATCHING_DEVICE
    else:
        return None

    if names:
        return ("not in" if is_negative else "in"), names

    # SQL NOT LIKE excludes NULL links. This comparison preserves that behavior.
    return ("!=" if is_negative else "="), NO_MATCHING_DEVICE


def _rewrite_condition(condition):
    if not isinstance(condition, (list, tuple)):
        return None

    if len(condition) == 3:
        field_index, operator_index, value_index = 0, 1, 2
    elif len(condition) == 4:
        if condition[0] not in DEVICE_LINK_DOCTYPES:
            return None
        field_index, operator_index, value_index = 1, 2, 3
    else:
        return None

    if condition[field_index] != "device":
        return None
    operator = " ".join(str(condition[operator_index]).lower().split())
    if operator not in DEVICE_FILTER_OPERATORS:
        return None

    replacement = _replacement(condition[value_index], operator)
    if replacement is None:
        return None

    new_condition = list(condition)
    new_condition[operator_index], new_condition[value_index] = replacement
    return new_condition


def _rewrite_filter_collection(filters):
    if isinstance(filters, dict):
        clause = filters.get("device")
        if (
            isinstance(clause, (list, tuple))
            and len(clause) == 2
            and " ".join(str(clause[0]).lower().split()) in DEVICE_FILTER_OPERATORS
        ):
            replacement = _replacement(clause[1], clause[0])
            if replacement:
                rewritten = dict(filters)
                rewritten["device"] = list(replacement)
                return rewritten
        return filters

    if not isinstance(filters, list):
        return filters

    single_condition = _rewrite_condition(filters)
    if single_condition is not None:
        return single_condition

    rewritten = []
    changed = False
    for condition in filters:
        new_condition = _rewrite_condition(condition)
        if new_condition is None:
            rewritten.append(condition)
        else:
            rewritten.append(new_condition)
            changed = True
    return rewritten if changed else filters


def _rewrite_device_filters():
    form = frappe.local.form_dict
    if form.get("doctype") not in DEVICE_LINK_DOCTYPES:
        return

    for key in ("filters", "or_filters"):
        raw_filters = form.get(key)
        filters = _parse_filters(raw_filters)
        if filters is None:
            continue

        rewritten = _rewrite_filter_collection(filters)
        if rewritten != filters:
            form[key] = json.dumps(rewritten, ensure_ascii=False)


@frappe.whitelist()
@frappe.read_only()
def get():
    _rewrite_device_filters()
    return reportview.get()


@frappe.whitelist()
@frappe.read_only()
def get_list():
    _rewrite_device_filters()
    return reportview.get_list()


@frappe.whitelist()
@frappe.read_only()
def get_count():
    _rewrite_device_filters()
    return reportview.get_count()
