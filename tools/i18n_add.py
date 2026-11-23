"""Append new translations to the three .po files and rebuild the .mo files (no gettext tools needed; uses polib).

Usage (from backend/, venv active):  python ../tools/i18n_add.py strings.json
strings.json: {"Uzbek source text": {"ru": "...", "en": "..."}, ...}
Existing msgids are left alone. The uz file gets the source text itself as the translation."""
import json
import sys
from pathlib import Path

import polib

BASE = Path(__file__).resolve().parents[1] / "backend" / "locale"
data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for lang in ("uz", "ru", "en"):
    path = BASE / lang / "LC_MESSAGES" / "django.po"
    text = path.read_text(encoding="utf-8")
    po = polib.pofile(str(path))
    have = {e.msgid for e in po}
    add = []
    for msgid, tr in data.items():
        if msgid in have:
            continue
        value = msgid if lang == "uz" else tr[lang]
        esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")  # noqa: E731
        add.append(f'msgid "{esc(msgid)}"\nmsgstr "{esc(value)}"\n')
    if add:
        path.write_text(text.rstrip("\n") + "\n\n" + "\n".join(add), encoding="utf-8")
    polib.pofile(str(path)).save_as_mofile(str(BASE / lang / "LC_MESSAGES" / "django.mo"))
    print(lang, "added", len(add))
