"""Require a catalog update only when homepage copy changes."""

from __future__ import annotations

import re
import subprocess
import sys
from html.parser import HTMLParser


class _HomepageText(HTMLParser):
    """Collect rendered HTML text while ignoring code and presentation blocks."""

    _ignored = {"script", "style", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._ignored:
            self._ignored_depth += 1
        if not self._ignored_depth:
            for name, value in attrs:
                if name.lower() in {"alt", "title", "aria-label", "placeholder"} and value:
                    normalized = " ".join(value.split())
                    if normalized:
                        self.parts.append(normalized)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._ignored and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            normalized = " ".join(data.split())
            if normalized:
                self.parts.append(normalized)


def visible_homepage_text(source: str) -> str:
    parser = _HomepageText()
    parser.feed(source)
    parser.close()
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def read_at(ref: str) -> str:
    return subprocess.check_output(
        ["git", "show", f"{ref}:templates/index.html"], text=True, encoding="utf-8"
    )


def main() -> int:
    base_ref, head_ref = sys.argv[1:3]
    if visible_homepage_text(read_at(base_ref)) == visible_homepage_text(read_at(head_ref)):
        print("Homepage text unchanged; translation catalog update is not required.")
        return 0

    print("Visible homepage text changed without translations/public_home.json.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
