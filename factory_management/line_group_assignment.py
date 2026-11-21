"""Generate stable IDs for manually created line group assignments."""

import uuid


def ensure_assignment_uid(doc, method=None):
    if doc.is_new() and not str(doc.get("assignment_uid") or "").strip():
        doc.assignment_uid = str(uuid.uuid4())
