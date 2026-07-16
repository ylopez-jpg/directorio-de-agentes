"""Tests basicos del dashboard."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repository import AgenteRepository, DataRepositoryError


DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "agentes.json"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_dashboard_carga(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "Archivero de Agentes AI" in r.text


def test_dashboard_muestra_agentes(client: TestClient) -> None:
    r = client.get("/")
    assert "Soporte" in r.text or "Financiero" in r.text or "Onboarding" in r.text


def test_api_agentes_lista(client: TestClient) -> None:
    r = client.get("/api/agentes")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert isinstance(data["agentes"], list)
    a = data["agentes"][0]
    assert "metadata" in a
    assert "llm_config" in a
    assert "rag_config" in a
    assert "tools" in a
    assert "gobernanza" in a


def test_api_agentes_filtro(client: TestClient) -> None:
    r = client.get("/api/agentes?estado=Activo")
    assert r.status_code == 200
    data = r.json()
    for a in data["agentes"]:
        assert a["metadata"]["estado"] == "Activo"


def test_api_detalle_ok(client: TestClient) -> None:
    lista = client.get("/api/agentes").json()
    aid = lista["agentes"][0]["id"]
    r = client.get(f"/api/agentes/{aid}")
    assert r.status_code == 200
    assert r.json()["id"] == aid


def test_api_detalle_404(client: TestClient) -> None:
    r = client.get("/api/agentes/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_pagina_detalle_404(client: TestClient) -> None:
    r = client.get("/agentes/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_repo_carga_ok() -> None:
    repo = AgenteRepository(DATA_FILE)
    archivo = repo.cargar()
    assert len(archivo.agentes) >= 1
    for a in archivo.agentes:
        assert a.metadata.nombre
        assert a.llm_config.temperatura >= 0


def test_repo_archivo_inexistente() -> None:
    repo = AgenteRepository("./no_existe.json")
    with pytest.raises(DataRepositoryError):
        repo.cargar()
