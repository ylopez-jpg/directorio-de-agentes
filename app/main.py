"""Archivero de Agentes AI - Dashboard de Gobernanza."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.repository import AgenteRepository, DataRepositoryError
from app.routers import api, pages, staging
from app.state import StagingStore

load_dotenv()

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
DATA_FILE = os.getenv("DATA_FILE", "./data/agentes.json")


@asynccontextmanager
async def lifespan(app: FastAPI):
    ruta = Path(DATA_FILE)
    if not ruta.exists():
        logger.warning("No se encontro %s. La app iniciara vacia.", ruta)
    else:
        try:
            repo = AgenteRepository(ruta)
            repo.cargar()
            StagingStore.reset()
            StagingStore.instance(ruta)
            logger.info("Archivo de agentes cargado OK: %s", ruta)
        except DataRepositoryError as e:
            logger.error("Error al cargar agentes.json: %s", e)
            raise
    yield
    StagingStore.reset()


app = FastAPI(
    title=os.getenv("APP_NAME", "Archivero de Agentes AI"),
    description="Dashboard de Gobernanza de IA - Reportes ejecutivos y tecnicos.",
    version="1.0.0",
    lifespan=lifespan,
)

STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.state.templates = templates
app.state.data_file = DATA_FILE

app.include_router(pages.router)
app.include_router(api.router)
app.include_router(staging.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}


@app.exception_handler(DataRepositoryError)
async def data_error_handler(request: Request, exc: DataRepositoryError):
    return HTMLResponse(
        content=f"<h1>Error de datos</h1><pre>{exc}</pre>",
        status_code=500,
    )
