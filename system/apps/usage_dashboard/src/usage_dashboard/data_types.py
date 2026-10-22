from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel


class HealthResponse(FrozenModel):
    """What the health probe answers."""

    status: str = Field(description="Always 'ok'")
    is_frontend_built: bool = Field(description="Whether the pages' bundle has been built, so a page can be served")


class AppNamesResponse(FrozenModel):
    """The display name of every registered app, which the pages show an app's usage under."""

    display_names: dict[str, str] = Field(description="Display name by registered app name")
