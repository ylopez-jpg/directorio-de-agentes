"""Rutas que devuelven paginas HTML."""
from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.state import StagingStore


router = APIRouter(tags=["pages"])


def get_staging(request: Request) -> StagingStore:
    return StagingStore.instance(request.app.state.data_file)


def _stats(archivo) -> dict:
    agentes = archivo.agentes
    total = len(agentes)
    estados = Counter(a.metadata.estado for a in agentes)
    frameworks = Counter(a.metadata.framework for a in agentes)
    proveedores = Counter(a.llm_config.proveedor for a in agentes)
    entornos = Counter(a.metadata.entorno_despliegue for a in agentes)
    modelos = Counter(a.llm_config.modelo for a in agentes)
    modelo_top = modelos.most_common(1)[0] if modelos else ("-", 0)
    framework_top = frameworks.most_common(1)[0] if frameworks else ("-", 0)
    datos_sensibles_indices = [str(i + 1) for i, a in enumerate(agentes) if a.gobernanza.maneja_datos_sensibles]
    datos_sensibles = len(datos_sensibles_indices)
    return {
        "total": total,
        "activos": estados.get("Activo", 0),
        "en_desarrollo": estados.get("En Desarrollo", 0),
        "datos_sensibles": datos_sensibles,
        "datos_sensibles_indices": datos_sensibles_indices,
        "modelo_top": modelo_top[0],
        "framework_top": framework_top[0],
        "estados": dict(estados),
        "frameworks": dict(frameworks),
        "proveedores": dict(proveedores),
        "entornos": dict(entornos),
        "modelos": dict(modelos),
    }


@router.get("/", response_class=HTMLResponse, name="dashboard")
def dashboard(request: Request, store: StagingStore = Depends(get_staging)):
    archivo = store.obtener_archivo()
    stats = _stats(archivo)
    return request.app.state.templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "agentes": archivo.agentes,
            "stats": stats,
        },
    )


@router.get("/agentes/{agente_id}", response_class=HTMLResponse, name="agente_detalle")
def agente_detalle(
    request: Request,
    agente_id: str,
    store: StagingStore = Depends(get_staging),
):
    agente = store.obtener_por_id(agente_id)
    if not agente:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    return request.app.state.templates.TemplateResponse(
        request,
        "agente_detalle.html",
        {
            "agente": agente,
        },
    )
