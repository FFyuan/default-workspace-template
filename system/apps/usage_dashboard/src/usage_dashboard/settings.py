"""The Usage app's own settings: which version of the widget the workspace shows.

One small JSON file in the app's data directory (``data/.apps/usage-dashboard/settings.json`` on a live workspace),
read on every request so an edit from another process lands without a restart, and written whole. A missing or
unreadable file reads as the defaults.
"""

import json
import os
import threading
from enum import auto
from pathlib import Path
from typing import Final

from loguru import logger
from pydantic import Field
from pydantic import PrivateAttr
from pydantic import ValidationError

from imbue.imbue_common.enums import LowerCaseStrEnum
from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.mutable_model import MutableModel

SETTINGS_FILENAME: Final[str] = "settings.json"


class WidgetVariant(LowerCaseStrEnum):
    """A version of the Usage widget (app-widgets plan section 7.8)."""

    # Concentric rings per subscription: the weekly limit outside, the 5-hour limit inside.
    RINGS = auto()
    # A row of horizontal bars per subscription: the 5-hour limit above the weekly one.
    BARS = auto()


class UsageSettings(FrozenModel):
    """What the settings file holds. Every field has a default, so an older file reads whole."""

    widget_variant: WidgetVariant = Field(default=WidgetVariant.RINGS, description="The version of the widget shown")


class UsageSettingsStore(MutableModel):
    """The settings file: read whole on every read, written whole under a lock."""

    path: Path = Field(frozen=True, description="The settings file")
    _lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    def read(self) -> UsageSettings:
        """The settings as they stand; an absent or unreadable file reads as the defaults."""
        if not self.path.exists():
            return UsageSettings()
        try:
            payload = json.loads(self.path.read_text())
        except (OSError, ValueError) as e:
            logger.warning("Ignoring an unreadable Usage settings file at {}: {}", self.path, e)
            return UsageSettings()
        try:
            return UsageSettings.model_validate(payload)
        except ValidationError as e:
            logger.warning("Ignoring a Usage settings file at {} that does not fit the settings: {}", self.path, e)
            return UsageSettings()

    def write(self, settings: UsageSettings) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.path.with_suffix(".json.tmp")
            temp_path.write_text(json.dumps(settings.model_dump(mode="json"), indent=2, sort_keys=True) + "\n")
            os.replace(temp_path, self.path)
