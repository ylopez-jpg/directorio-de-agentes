"""Staging store: cambios en memoria hasta que el usuario publique.

El patron es:
- El archivo en disco (data/agentes.json) es la fuente de verdad
- El staging mantiene un "working copy" del archivo en memoria
- Operaciones put/delete/add/import modifican el working copy
- publicar() escribe el working copy al disco de forma atomica
- descartar() recarga desde disco, perdiendo los cambios pendientes
"""
from __future__ import annotations

import copy
import json
import shutil
import tempfile
import threading
import uuid
from datetime import date
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from app.models import Agente, ArchivoAgentes
from app.repository import DataRepositoryError


class StagingStore:
    """Singleton en memoria del estado de staging."""

    _instance: Optional["StagingStore"] = None
    _lock = threading.Lock()

    def __init__(self, ruta_archivo: str | Path) -> None:
        self.ruta_archivo = Path(ruta_archivo)
        self._archivo: Optional[ArchivoAgentes] = None
        self._cargado = False

    @classmethod
    def instance(cls, ruta_archivo: Optional[str | Path] = None) -> "StagingStore":
        with cls._lock:
            if cls._instance is None:
                if ruta_archivo is None:
                    raise RuntimeError("StagingStore no inicializado")
                cls._instance = cls(ruta_archivo)
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._instance = None

    def _asegurar_cargado(self) -> ArchivoAgentes:
        if not self._cargado:
            if not self.ruta_archivo.exists():
                raise DataRepositoryError(f"No existe {self.ruta_archivo}")
            contenido = self.ruta_archivo.read_text(encoding="utf-8")
            data = json.loads(contenido)
            self._archivo = ArchivoAgentes.model_validate(data)
            self._cargado = True
        return self._archivo  # type: ignore[return-value]

    def _persistir_a_disco(self) -> None:
        if self._archivo is None:
            return
        serializado = self._archivo.model_dump(mode="json")
        self.ruta_archivo.parent.mkdir(parents=True, exist_ok=True)
        tmp = tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.ruta_archivo.parent,
            delete=False,
            suffix=".tmp",
        )
        try:
            json.dump(serializado, tmp, indent=2, ensure_ascii=False)
            tmp.close()
            shutil.move(tmp.name, self.ruta_archivo)
        except Exception:
            Path(tmp.name).unlink(missing_ok=True)
            raise

    def obtener_archivo(self) -> ArchivoAgentes:
        return copy.deepcopy(self._asegurar_cargado())

    def obtener_agentes(self) -> list[Agente]:
        return self.obtener_archivo().agentes

    def obtener_por_id(self, agente_id: str) -> Optional[Agente]:
        for a in self._asegurar_cargado().agentes:
            if str(a.id) == agente_id:
                return copy.deepcopy(a)
        return None

    def upsert(self, agente: Agente) -> Agente:
        archivo = self._asegurar_cargado()
        for i, existente in enumerate(archivo.agentes):
            if str(existente.id) == str(agente.id):
                archivo.agentes[i] = agente
                return copy.deepcopy(agente)
        archivo.agentes.append(agente)
        return copy.deepcopy(agente)

    def eliminar(self, agente_id: str) -> bool:
        archivo = self._asegurar_cargado()
        antes = len(archivo.agentes)
        archivo.agentes = [a for a in archivo.agentes if str(a.id) != agente_id]
        return len(archivo.agentes) < antes

    def importar(self, agentes: list[Agente]) -> int:
        archivo = self._asegurar_cargado()
        ids_existentes = {str(a.id) for a in archivo.agentes}
        agregados = 0
        for agente in agentes:
            if str(agente.id) in ids_existentes:
                continue
            archivo.agentes.append(agente)
            ids_existentes.add(str(agente.id))
            agregados += 1
        return agregados

    def contar_cambios(self) -> int:
        return len(self._asegurar_cargado().agentes)

    def publicar(self) -> int:
        archivo = self._asegurar_cargado()
        archivo.ultima_actualizacion = date.today()
        self._archivo = archivo
        self._persistir_a_disco()
        return len(archivo.agentes)

    def descartar(self) -> None:
        self._archivo = None
        self._cargado = False
        self._asegurar_cargado()

    @staticmethod
    def nuevo_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def validar_dict(datos: dict) -> Agente:
        if "id" not in datos or not datos["id"]:
            datos["id"] = str(uuid.uuid4())
        try:
            return Agente.model_validate(datos)
        except ValidationError as e:
            raise DataRepositoryError(f"Agente invalido: {e}") from e
