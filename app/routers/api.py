"""API JSON para integraciones y futuro CRUD. Lee desde staging."""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.analysis import analizar_con_llm, detectar_integraciones, resumen_conexiones
from app.state import StagingStore


router = APIRouter(prefix="/api", tags=["api"])


def get_staging(request: Request) -> StagingStore:
    return StagingStore.instance(request.app.state.data_file)


@router.get("/agentes", summary="Lista todos los agentes con filtros opcionales")
def listar_agentes(
    request: Request,
    q: Optional[str] = Query(None, description="Busqueda libre"),
    estado: Optional[str] = Query(None, description="Filtra por estado"),
    framework: Optional[str] = Query(None, description="Filtra por framework"),
    store: StagingStore = Depends(get_staging),
):
    agentes = store.obtener_agentes()
    if q:
        ql = q.lower()
        agentes = [
            a for a in agentes
            if ql in a.metadata.nombre.lower()
            or ql in a.metadata.descripcion.lower()
            or ql in a.metadata.dueno.lower()
        ]
    if estado:
        agentes = [a for a in agentes if a.metadata.estado == estado]
    if framework:
        agentes = [a for a in agentes if a.metadata.framework == framework]
    return {
        "total": len(agentes),
        "agentes": [a.model_dump(mode="json") for a in agentes],
    }


@router.get("/agentes/{agente_id}", summary="Detalle de un agente")
def detalle_agente(
    agente_id: str,
    store: StagingStore = Depends(get_staging),
):
    agente = store.obtener_por_id(agente_id)
    if not agente:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    return agente.model_dump(mode="json")


@router.get("/stats", summary="Estadisticas agregadas para graficas")
def stats(
    request: Request,
    store: StagingStore = Depends(get_staging),
):
    agentes = store.obtener_agentes()
    return {
        "total": len(agentes),
        "activos": sum(1 for a in agentes if a.metadata.estado == "Activo"),
        "en_desarrollo": sum(1 for a in agentes if a.metadata.estado == "En Desarrollo"),
        "datos_sensibles": sum(1 for a in agentes if a.gobernanza.maneja_datos_sensibles),
    }


@router.get("/agentes/{agente_id}/integraciones", summary="Integraciones detectadas (AnythingLLM, Pinecone, etc.)")
def integraciones_agente(
    agente_id: str,
    store: StagingStore = Depends(get_staging),
):
    agente = store.obtener_por_id(agente_id)
    if not agente:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    data = agente.model_dump(mode="json")
    return {
        "agente_id": agente_id,
        "integraciones": detectar_integraciones(data),
        "resumen": resumen_conexiones(data),
    }


@router.post("/agentes/{agente_id}/analizar", summary="Analisis LLM on-demand del agente")
def analizar_agente(
    agente_id: str,
    store: StagingStore = Depends(get_staging),
):
    agente = store.obtener_por_id(agente_id)
    if not agente:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
    data = agente.model_dump(mode="json")
    texto = analizar_con_llm(data, api_key)
    return {
        "agente_id": agente_id,
        "modelo": os.getenv("ANALYSIS_MODEL", "claude-sonnet-5"),
        "analisis_md": texto,
        "llm_habilitado": bool(api_key),
    }
