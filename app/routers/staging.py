"""Endpoints de staging: edicion en memoria + publicacion + importador."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse

from app.importers.parser import parsear, parsear_archivo
from app.repository import DataRepositoryError
from app.state import StagingStore


router = APIRouter(prefix="/api/staging", tags=["staging"])


def get_staging(request: Request) -> StagingStore:
    return StagingStore.instance(request.app.state.data_file)


@router.get("/estado", summary="Cantidad de agentes en staging")
def estado(request: Request, store: StagingStore = Depends(get_staging)) -> dict:
    agentes = store.obtener_agentes()
    return {
        "total_en_staging": len(agentes),
        "cambios_pendientes": True,
    }


@router.put("/agente/{agente_id}", summary="Actualiza o crea un agente en staging")
def upsert_agente(
    agente_id: str,
    request: Request,
    payload: dict = Body(...),
    store: StagingStore = Depends(get_staging),
) -> dict:
    payload["id"] = agente_id
    try:
        agente = StagingStore.validar_dict(payload)
    except DataRepositoryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    guardado = store.upsert(agente)
    return {"ok": True, "agente": guardado.model_dump(mode="json")}


@router.post("/agente", summary="Crea un agente nuevo en staging")
def crear_agente(
    request: Request,
    payload: dict = Body(...),
    store: StagingStore = Depends(get_staging),
) -> dict:
    if "id" not in payload or not payload["id"]:
        payload["id"] = StagingStore.nuevo_id()
    try:
        agente = StagingStore.validar_dict(payload)
    except DataRepositoryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    guardado = store.upsert(agente)
    return {"ok": True, "agente": guardado.model_dump(mode="json")}


@router.delete("/agente/{agente_id}", summary="Elimina un agente del staging")
def eliminar_agente(
    agente_id: str,
    request: Request,
    store: StagingStore = Depends(get_staging),
) -> dict:
    ok = store.eliminar(agente_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Agente no encontrado en staging")
    return {"ok": True}


@router.post("/publicar", summary="Escribe staging al archivo JSON")
def publicar(
    request: Request,
    store: StagingStore = Depends(get_staging),
) -> dict:
    total = store.publicar()
    return {"ok": True, "publicados": total}


@router.post("/descartar", summary="Recarga staging desde disco")
def descartar(
    request: Request,
    store: StagingStore = Depends(get_staging),
) -> dict:
    store.descartar()
    return {"ok": True, "total_en_staging": len(store.obtener_agentes())}


@router.post("/importar", summary="Importa agentes desde texto/CSV/JSON")
def importar(
    request: Request,
    contenido: str = Body(..., media_type="text/plain"),
    store: StagingStore = Depends(get_staging),
) -> dict:
    formato, items, errores = parsear(contenido)
    if errores and not items:
        raise HTTPException(status_code=400, detail={"formato": formato, "errores": errores})
    validados: list[Any] = []
    fallos: list[str] = []
    for item in items:
        try:
            validados.append(StagingStore.validar_dict(item))
        except DataRepositoryError as e:
            fallos.append(str(e))
    agregados = store.importar(validados)
    return {
        "ok": True,
        "formato_detectado": formato,
        "recibidos": len(items),
        "agregados": agregados,
        "duplicados_omitidos": len(items) - agregados - len(fallos),
        "fallos_validacion": fallos,
    }


@router.post("/importar-archivo", summary="Importa agentes desde un archivo")
async def importar_archivo(
    request: Request,
    archivo: UploadFile = File(...),
    store: StagingStore = Depends(get_staging),
) -> dict:
    contenido = await archivo.read()
    formato, items, errores = parsear_archivo(archivo.filename or "import.txt", contenido)
    if errores and not items:
        raise HTTPException(status_code=400, detail={"formato": formato, "errores": errores})
    validados: list[Any] = []
    fallos: list[str] = []
    for item in items:
        try:
            validados.append(StagingStore.validar_dict(item))
        except DataRepositoryError as e:
            fallos.append(str(e))
    agregados = store.importar(validados)
    return {
        "ok": True,
        "archivo": archivo.filename,
        "formato_detectado": formato,
        "recibidos": len(items),
        "agregados": agregados,
        "duplicados_omitidos": len(items) - agregados - len(fallos),
        "fallos_validacion": fallos,
    }
