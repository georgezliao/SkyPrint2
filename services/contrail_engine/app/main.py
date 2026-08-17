import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import compare, health, optimize, predict, route_history

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting SkyPrint Contrail Engine")
    logger.info(f"Weather provider: {settings.weather_provider}")
    logger.info(f"Fallback-only mode: {settings.fallback_only}")
    yield
    logger.info("Shutting down Contrail Engine")


app = FastAPI(
    title="SkyPrint Contrail Engine",
    description="Scientific contrail modeling service using PyContrails CoCiP",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(predict.router)
app.include_router(compare.router)
app.include_router(optimize.router)
app.include_router(route_history.router)
