"""Empty API of EN-08: liveness and readiness. Routes from docs/05-backend/06-api-design.md come later."""

from fastapi import FastAPI, Response
from sqlalchemy import text

from smarthive.db.engine import engine

app = FastAPI(title="SmartHive", openapi_url="/api/v1/openapi.json")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz(response: Response):
    try:
        with engine().connect() as c:
            c.execute(text("SELECT 1"))
    except Exception:  # any failure means "not ready"
        response.status_code = 503
        return {"status": "database unavailable"}
    return {"status": "ready"}
