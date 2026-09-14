from fastapi import FastAPI

app = FastAPI(title="Knowledge Graph API")


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
