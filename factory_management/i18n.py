"""Shared translated messages for API and public QC page."""
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def catalog():
    path = Path(__file__).parent / "public" / "js" / "qc-i18n.json"
    return json.loads(path.read_text(encoding="utf-8"))


def message(key, lang="vi"):
    texts = catalog().get(lang, catalog()["vi"])
    return texts.get(key, catalog()["vi"][key])
