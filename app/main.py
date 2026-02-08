from fastapi import FastAPI

from app.config import settings
from app.database import Base, engine
from app.routers.auth import router as auth_router
from app.routers.logs import router as logs_router
from app.routers.me import router as me_router
from app.routers.stats import router as stats_router


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    @app.on_event("startup")
    def on_startup() -> None:
        Base.metadata.create_all(bind=engine)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router)
    app.include_router(me_router)
    app.include_router(logs_router)
    app.include_router(stats_router)
    return app


app = create_app()

