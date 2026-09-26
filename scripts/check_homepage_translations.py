from __future__ import annotations
import json
from pathlib import Path

REQUIRED_LANGS = ["de","en","cs","sk","hu","nl","pl","it","es","fr","ch"]
CATALOG = Path("translations/public_home.json")
data = json.loads(CATALOG.read_text(encoding="utf-8"))

missing_langs = [lang for lang in REQUIRED_LANGS if lang not in data]
assert not missing_langs, f"Missing languages: {missing_langs}"

base_keys = set(data["de"])
for lang in REQUIRED_LANGS:
    keys = set(data[lang])
    assert keys == base_keys, f"{lang}: translation keys differ; missing={sorted(base_keys-keys)}, extra={sorted(keys-base_keys)}"
    for key, value in data[lang].items():
        assert isinstance(value, str) and value.strip(), f"{lang}.{key}: empty translation"

print("Homepage translation catalog complete for: " + ", ".join(REQUIRED_LANGS))
