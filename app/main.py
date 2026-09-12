"""
FastAPI entrypoint for the Projekt:Alpha execution backend.

Run:  ALPHA_DATA_DIR=data uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.state import AppState


@asynccontextmanager
async def lifespan(app: FastAPI):
    state = AppState()
    state.start_background()
    app.state.alpha = state
    yield
    state.ws.stop()
    state.lake.close()


app = FastAPI(
    title="Projekt:Alpha Execution Backend",
    description="Real Kraken Spot + Futures execution, quant analytics and strategy orchestration. No simulated data — unavailable sources return explicit errors.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev convenience; pin via ALPHA_ALLOWED_ORIGINS in production
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/api/health")
def health(request: Request):
    state: AppState = request.app.state.alpha
    return {"ok": True, "mode": state.settings.execution_mode, "ws": state.ws.connected, "instances": len(state.engine.instances)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
