"""A controlled tag list. Only tags defined in taxonomy.json can be stored."""
from __future__ import annotations

import json
import re
from pathlib import Path

SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class Taxonomy:
    def __init__(self, tags: dict[str, list[str]]):
        for name in tags:
            if not SLUG.match(name):
                raise ValueError(f"tag '{name}' must be lowercase words joined by hyphens")
        self.keywords = {name: [kw.lower() for kw in kws] for name, kws in tags.items()}
        self._patterns = {
            name: [re.compile(r"\b" + re.escape(kw)) for kw in kws]
            for name, kws in self.keywords.items()
        }

    @classmethod
    def load(cls, path: str | Path) -> "Taxonomy":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data["tags"])

    def names(self) -> list[str]:
        return sorted(self.keywords)

    def match_text(self, text: str) -> set[str]:
        """Tags whose keywords appear at the start of a word in the text."""
        lowered = text.lower()
        return {
            name
            for name, patterns in self._patterns.items()
            if any(p.search(lowered) for p in patterns)
        }

    def resolve(self, explicit: list[str], text: str) -> tuple[set[str], list[str]]:
        """Combine tags the author wrote with tags found in the text.

        Returns (accepted tags, explicit tags that are not in the taxonomy).
        """
        accepted: set[str] = set()
        unknown: list[str] = []
        for raw in explicit:
            slug = raw.strip().lower()
            if not slug:
                continue
            if slug in self.keywords:
                accepted.add(slug)
            else:
                unknown.append(slug)
        accepted |= self.match_text(text)
        return accepted, unknown
