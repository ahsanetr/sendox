"""Request-scoped dependencies.

Settings are read off ``app.state`` rather than the module-level cache so that an
app built with ``create_app(settings)`` — tests, or any future second app in one
process — actually uses the settings it was given.
"""

from typing import Annotated

from fastapi import Depends, Request

from sendox_api.config import Settings


def get_request_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_request_settings)]
