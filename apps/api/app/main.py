from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .database import get_engine
from .models import Base

app = FastAPI(title="Knowledge Graph API")


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
