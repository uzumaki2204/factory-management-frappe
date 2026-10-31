"""Resolve QC event Device Link filters against the displayed device name."""

import json

import frappe
from frappe.desk import reportview


EVENT_DOCTYPES = {"QC Inspection Event", "UQQC Inspection Event"}
DEVICE_DOCTYPE = "Factory Device"
NO_MATCHING_DEVICE = "__no_matching_factory_device__"
DEVICE_QUERY_PAGE_SIZE = 500


def _parse_filters(raw_filters):
    if isinstance(raw_filters, str):
        try:
            return json.loads(raw_filters)
        except json.JSONDecodeError:
            return None
    return raw_filters


def _matching_device_names(pattern):
    cache = getattr(frappe.local, "factory_device_name_filter_cache", None)
    if cache is None:
        cache = {}
        frappe.local.factory_device_name_filter_cache = cache

    if pattern in cache:
        return cache[pattern]

    names = []
    start = 0
    while True:
        page = frappe.get_list(
            DEVICE_DOCTYPE,
            filters={"device_name": ["like", pattern]},
            fields=["name"],
            order_by="name asc",
            start=start,
            page_length=DEVICE_QUERY_PAGE_SIZE,
        )
        names.extend(row["name"] for row in page)
        if len(page) < DEVICE_QUERY_PAGE_SIZE:
            break
        start += DEVICE_QUERY_PAGE_SIZE

    cache[pattern] = names
    return names


def _replacement(pattern, operator):
    if not isinstance(pattern, str) or not pattern:
        return None

    names = _matching_device_names(pattern)
    is_negative = str(operator).lower() == "not like"
    if names:
        return ("not in" if is_negative else "in"), names

    # Factory Device records use UUID names, so this value cannot match a real Link.
    # Keep SQL's NOT LIKE behavior for NULL links: NULL does not satisfy the filter.
    return ("!=" if is_negative else "="), NO_MATCHING_DEVICE


def _rewrite_condition(condition):
    if not isinstance(condition, (list, tuple)):
        return None

    if len(condition) == 3:
        field_index, operator_index, value_index = 0, 1, 2
    elif len(condition) == 4:
        if condition[0] not in EVENT_DOCTYPES:
            return None
        field_index, operator_index, value_index = 1, 2, 3
    else:
        return None

    if condition[field_index] != "device":
        return None
    operator = str(condition[operator_index]).lower()
    if operator not in {"like", "not like"}:
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
            and str(clause[0]).lower() in {"like", "not like"}
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
    if form.get("doctype") not in EVENT_DOCTYPES:
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
