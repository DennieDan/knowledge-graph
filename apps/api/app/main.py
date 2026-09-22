from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from .accounts import router as accounts_router
from .auth import router as auth_router
from .config import get_settings
from .database import get_engine
from .drive import router as drive_router
from .drive_sync import router as drive_sync_router
from .models import Base
from .stacks import router as stacks_router
from .whatsapp import router as whatsapp_router

app = FastAPI(title="Knowledge Graph API")

app.add_middleware(
    SessionMiddleware,
    secret_key=get_settings().session_secret.get_secret_value(),
    session_cookie="kg_session",
    same_site="lax",
    https_only=False,
    max_age=60 * 60 * 24 * 14,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().web_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(accounts_router)
app.include_router(drive_router)
app.include_router(drive_sync_router)
app.include_router(whatsapp_router)
app.include_router(stacks_router)


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", response_model=None)
def readiness():
    try:
        with Session(get_engine()) as session:
            extension = session.scalar(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
            if not extension:
                return JSONResponse(status_code=503, content={"status": "not_ready"})
            # Check the schema as well as connectivity. A fresh, unmigrated DB isn't ready.
            for table in Base.metadata.sorted_tables:
                session.execute(select(table).limit(0))
        return {"status": "ok", "database": "ok", "pgvector": extension}
    except (SQLAlchemyError, ValidationError):
        # Do not expose connection strings or database error details to clients.
        return JSONResponse(status_code=503, content={"status": "not_ready"})
