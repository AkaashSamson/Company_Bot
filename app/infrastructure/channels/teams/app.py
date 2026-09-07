import os

from microsoft_teams.apps import App, FastAPIAdapter

from app.infrastructure.channels.teams.handler import create_message_handler


def _create_teams_app(fastapi_app):
    skip_auth = os.getenv("TEAMS_SKIP_AUTH", "true").lower() == "true"
    adapter = FastAPIAdapter(app=fastapi_app)
    teams_app = App(http_server_adapter=adapter, skip_auth=skip_auth)
    teams_app.on_message(create_message_handler())
    return teams_app


async def initialize_teams(fastapi_app) -> None:
    """Register the Teams endpoint on the existing FastAPI application."""
    teams_app = _create_teams_app(fastapi_app)
    await teams_app.initialize()