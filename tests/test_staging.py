"""Tests del staging store, endpoints y parser."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.state import StagingStore


DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "agentes.json"
BACKUP_FILE = DATA_FILE.with_suffix(".bak.test")


@pytest.fixture(autouse=True)
def backup_y_reset():
    """Hace backup del JSON original antes de cada test y lo restaura al final."""
    if DATA_FILE.exists():
        shutil.copy(DATA_FILE, BACKUP_FILE)
    StagingStore.reset()
    yield
    StagingStore.reset()
    if BACKUP_FILE.exists():
        shutil.copy(BACKUP_FILE, DATA_FILE)
        BACKUP_FILE.unlink()


@pytest.fixture
def client() -> TestClient:
    StagingStore.reset()
    return TestClient(app)


def _nuevo_dict(nombre: str = "Test") -> dict:
    return {
        "metadata": {
            "nombre": nombre,
            "version": "0.1.0",
            "estado": "En Desarrollo",
            "framework": "Custom",
            "entorno_despliegue": "Sandbox",
            "dueno": "Test",
            "fecha_creacion": "2026-07-10",
            "ultima_actualizacion": "2026-07-10",
            "descripcion": "Test",
        },
        "llm_config": {
            "modelo": "gpt-4o-mini",
            "temperatura": 0.5,
            "proveedor": "OpenAI",
            "max_tokens": 1024,
            "system_prompt_resumen": "Test prompt.",
        },
        "rag_config": {"habilitado": False, "fuentes_de_datos": []},
        "tools": [],
        "gobernanza": {
            "nivel_acceso": "Interno",
            "maneja_datos_sensibles": False,
            "tipos_datos_sensibles": [],
            "cumple_compliance": [],
            "politica_retencion": "30 dias",
            "requiere_aprobacion_para_cambios": False,
        },
    }


# ==================== Staging ====================

def test_estado_staging_inicial(client: TestClient) -> None:
    r = client.get("/api/staging/estado")
    assert r.status_code == 200
    assert r.json()["total_en_staging"] >= 3


def test_crear_agente_staging(client: TestClient) -> None:
    r = client.post("/api/staging/agente", json=_nuevo_dict("Agente Nuevo"))
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["agente"]["metadata"]["nombre"] == "Agente Nuevo"
    assert data["agente"]["id"]


def test_actualizar_agente_staging(client: TestClient) -> None:
    inicial = client.get("/api/staging/estado").json()
    aid = client.get("/api/agentes").json()["agentes"][0]["id"]
    payload = _nuevo_dict("Nombre Actualizado")
    r = client.put(f"/api/staging/agente/{aid}", json=payload)
    assert r.status_code == 200
    detalle = client.get(f"/api/agentes/{aid}").json()
    assert detalle["metadata"]["nombre"] == "Nombre Actualizado"


def test_eliminar_agente_staging(client: TestClient) -> None:
    aid = client.get("/api/agentes").json()["agentes"][0]["id"]
    r = client.delete(f"/api/staging/agente/{aid}")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    r2 = client.get(f"/api/agentes/{aid}")
    assert r2.status_code == 404


def test_eliminar_agente_inexistente(client: TestClient) -> None:
    r = client.delete("/api/staging/agente/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_publicar_persiste(client: TestClient) -> None:
    client.post("/api/staging/agente", json=_nuevo_dict("Persistido"))
    r = client.post("/api/staging/publicar")
    assert r.status_code == 200
    contenido = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    nombres = [a["metadata"]["nombre"] for a in contenido["agentes"]]
    assert "Persistido" in nombres


def test_descartar_revierte(client: TestClient) -> None:
    client.post("/api/staging/agente", json=_nuevo_dict("Temporal"))
    r = client.post("/api/staging/descartar")
    assert r.status_code == 200
    contenido = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    nombres = [a["metadata"]["nombre"] for a in contenido["agentes"]]
    assert "Temporal" not in nombres


def test_upsert_invalido_400(client: TestClient) -> None:
    r = client.put("/api/staging/agente/abc", json={"foo": "bar"})
    assert r.status_code == 400


# ==================== Importador ====================

def test_importar_csv(client: TestClient) -> None:
    csv = "nombre,modelo,framework,estado,entorno\nBot Ventas,gpt-4o,LangChain,En Desarrollo,Staging\nBot Legal,claude-sonnet-4-5,Custom,Activo,Produccion"
    r = client.post("/api/staging/importar", content=csv, headers={"Content-Type": "text/plain"})
    assert r.status_code == 200
    d = r.json()
    assert d["formato_detectado"] == "csv"
    assert d["agregados"] == 2
    assert d["fallos_validacion"] == []


def test_importar_json(client: TestClient) -> None:
    payload = json.dumps([_nuevo_dict("JSON1"), _nuevo_dict("JSON2")])
    r = client.post("/api/staging/importar", content=payload, headers={"Content-Type": "text/plain"})
    assert r.status_code == 200
    d = r.json()
    assert d["formato_detectado"] == "json"
    assert d["agregados"] == 2


def test_importar_texto_libre(client: TestClient) -> None:
    texto = "nombre: Mi Agente de Texto\nmodelo: gpt-4o-mini\nframework: LangChain\nestado: En Desarrollo"
    r = client.post("/api/staging/importar", content=texto, headers={"Content-Type": "text/plain"})
    assert r.status_code == 200
    d = r.json()
    assert d["formato_detectado"] == "texto"
    assert d["agregados"] == 1
    nombres = [a["metadata"]["nombre"] for a in client.get("/api/staging/estado").json().get("agentes", [])] if "agentes" in d else []
    contenido = client.get("/api/agentes").json()
    nombres_finales = [a["metadata"]["nombre"] for a in contenido["agentes"]]
    assert "Mi Agente de Texto" in nombres_finales


def test_importar_contenido_vacio_400(client: TestClient) -> None:
    r = client.post("/api/staging/importar", content="   ", headers={"Content-Type": "text/plain"})
    assert r.status_code == 400


def test_importar_archivo(client: TestClient) -> None:
    csv = "nombre,modelo,framework,estado,entorno\nFromFile,gpt-4o,Custom,En Desarrollo,Sandbox"
    files = {"archivo": ("agentes.csv", csv.encode("utf-8"), "text/csv")}
    r = client.post("/api/staging/importar-archivo", files=files)
    assert r.status_code == 200
    d = r.json()
    assert d["archivo"] == "agentes.csv"
    assert d["agregados"] == 1


def test_importar_duplicados_se_omiten(client: TestClient) -> None:
    aid = client.get("/api/agentes").json()["agentes"][0]["id"]
    payload = _nuevo_dict("Duplicado")
    payload["id"] = aid
    body = json.dumps([payload])
    r = client.post("/api/staging/importar", content=body, headers={"Content-Type": "text/plain"})
    assert r.status_code == 200
    d = r.json()
    assert d["agregados"] == 0
    assert d["duplicados_omitidos"] >= 1


# ==================== Parser unitario ====================

def test_parser_detecta_csv() -> None:
    from app.importers.parser import parsear
    f, items, errs = parsear("nombre,modelo\nFoo,gpt-4o\nBar,claude-sonnet-4-5")
    assert f == "csv"
    assert errs == []
    assert len(items) == 2
    assert items[0]["metadata"]["nombre"] == "Foo"


def test_parser_detecta_json() -> None:
    from app.importers.parser import parsear
    f, items, errs = parsear('[{"x": 1}]')
    assert f == "json"
    assert len(items) == 1
    assert errs == []


def test_parser_detecta_texto() -> None:
    from app.importers.parser import parsear
    f, items, errs = parsear("Esto es solo texto sin estructura clara, bla bla.")
    assert f == "texto"
    assert errs == []
