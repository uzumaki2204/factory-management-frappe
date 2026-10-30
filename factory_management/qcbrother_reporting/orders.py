"""PO eligibility is decided after choosing the latest revision, as in .NET."""

import re
from collections import defaultdict
from uuid import UUID

from .model import clean, po_key


def purchase_order_values(repository, items, planned=False):
    keys = {po_key(item) for item in items if all(po_key(item))}
    if not keys:
        return {}
    details = list(repository.order_details(keys))
    numbers = {clean(row["poNumber"]) for row in details if clean(row["poNumber"])}
    if not numbers:
        return {}
    latest = {}
    for row in repository.order_revisions(numbers):
        number = clean(row["poNumber"]).upper()
        if number not in latest or _compare_revision(row, latest[number]) > 0:
            latest[number] = row
    eligible = {number: str(row["id"]).lower() for number, row in latest.items() if _eligible(row, planned)}
    quantities, po_numbers = defaultdict(int), defaultdict(dict)
    for row in details:
        number = clean(row["poNumber"])
        if eligible.get(number.upper()) != str(row["purchaseOrderId"]).lower():
            continue
        key = po_key(row)
        quantities[key] += int(row["orderQty"])
        po_numbers[key].setdefault(number.upper(), number)
    if planned:
        return {key: quantity for key, quantity in quantities.items() if key in keys}
    return {key: ",".join(sorted(numbers.values(), key=str.upper)) for key, numbers in po_numbers.items()}


def _eligible(row, planned):
    document, status = clean(row["documentStatus"]).upper(), clean(row["status"]).upper()
    if planned:
        return document in {"NEW", "CHANGE"}
    return bool(document and status and document not in {"CANCEL", "FINALIZED"}
                and status not in {"COMPLETED", "CANCELLED"})


def _compare_revision(left, right):
    a, b = clean(left["revisionNo"]), clean(right["revisionNo"])
    ai, bi = _int64(a), _int64(b)
    if ai is not None and bi is not None and ai != bi:
        return (ai > bi) - (ai < bi)
    if a.upper() != b.upper():
        return (a.upper() > b.upper()) - (a.upper() < b.upper())
    return (UUID(str(left["id"])).int > UUID(str(right["id"])).int) - (
        UUID(str(left["id"])).int < UUID(str(right["id"])).int)


def _int64(value):
    if not re.fullmatch(r"[+-]?[0-9]+", value):
        return None
    number = int(value)
    return number if -(2 ** 63) <= number < 2 ** 63 else None
