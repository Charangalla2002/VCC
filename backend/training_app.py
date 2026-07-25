"""
training_app.py - Standalone FastAPI application dedicated to YOLO model training (runs on Port 8002).
"""
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting VCC Training Dedicated Server on Port 8002...")
    yield
    # Kill any in-flight training subprocess before we go down.
    from routers.training import shutdown_training
    shutdown_training()
    # Close SQLAlchemy engine connection pool
    from database import engine
    await engine.dispose()
    logger.info("Training Server database engine disposed.")


app = FastAPI(
    title="VCC Dedicated Training Service API",
    version="1.0.0",
    description="Dedicated microservice for YOLO training operations, isolated from live feed pipeline.",
    lifespan=lifespan,
)

# CORS middleware
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174")
ALLOWED_ORIGINS = list(set(
    [o.strip() for o in _raw_origins.split(",") if o.strip()] + 
    ["http://localhost:5173", "http://localhost:5174", "http://127.0.0.1:5173", "http://127.0.0.1:5174"]
))

logger.info("CORS allowed origins (Port 8002): %s", ALLOWED_ORIGINS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from starlette.requests import Request
from starlette.responses import Response

@app.middleware("http")
async def handle_options_preflight(request: Request, call_next):
    if request.method == "OPTIONS":
        origin = request.headers.get("origin")
        response = Response(status_code=200)
        if origin and (origin in ALLOWED_ORIGINS or origin.startswith("http://localhost:") or origin.startswith("http://127.0.0.1:")):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = request.headers.get("access-control-request-headers", "*")
        return response
    return await call_next(request)

# Mount the auth and training routers
from routers import auth, training
app.include_router(auth.router)
app.include_router(training.router)
