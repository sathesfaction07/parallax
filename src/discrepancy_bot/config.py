"""Settings, and where each one comes from.

Two of these are guesses that change the answer -- the propagation window and the source relation.
They are settings rather than constants precisely so that they can be argued with; a number that
decides whether something is a conflict should not be buried in a function.

No list-typed fields. Pydantic parses those as JSON, so `DB_CACHED_SOURCES=a,b` fails with a
decode error that tells the user nothing. Comma strings are split in a property instead.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .classify import SourceRelation


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DB_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    left_file: str = "system_a.csv"
    right_file: str = "system_b.csv"
    left_name: str = "system-a"
    right_name: str = "system-b"

    propagation_minutes: int = Field(default=60, ge=0)
    relation: SourceRelation = SourceRelation.UNDECLARED
    cached_sources: str = ""

    apply_rules: bool = True
    truncate_unit: str = "day"

    @property
    def window(self) -> timedelta:
        return timedelta(minutes=self.propagation_minutes)

    @property
    def caches(self) -> frozenset[str]:
        return frozenset(s.strip() for s in self.cached_sources.split(",") if s.strip())

    @property
    def left_path(self) -> Path:
        return self.data_dir / self.left_file

    @property
    def right_path(self) -> Path:
        return self.data_dir / self.right_file


def provenance() -> list[tuple[str, str, str]]:
    """Where each setting's value comes from, for `doctor`.

    (name, source, what happens if it is wrong)
    """
    return [
        (
            "propagation_minutes",
            "CONFIGURED, never measured",
            "too wide and real conflicts are called races; too narrow and races are called "
            "conflicts",
        ),
        (
            "relation",
            "DECLARED by whoever set it up",
            "the same evidence flips between CONFLICT and TRANSITION; left UNDECLARED it stays "
            "UNSEPARABLE, which is the honest default",
        ),
        (
            "cached_sources",
            "DECLARED; nothing in a row says it is a copy",
            "a real decision-maker declared a cache has every difference explained away as lag",
        ),
        (
            "truncate_unit",
            "chosen, and only used to REPORT precision loss, never to compare",
            "nothing -- it is diagnostic",
        ),
        (
            "apply_rules",
            "chosen",
            "off, the report is larger and every difference is visible; on, it is smaller and "
            "the removals are listed separately",
        ),
    ]
