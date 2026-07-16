"""Carga y persistencia del archivo de agentes."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from app.models import Agente, ArchivoAgentes


class DataRepositoryError(Exception):
    """Errores del repositorio de datos."""


class AgenteRepository:
    def __init__(self, ruta_archivo: str | os.PathLike) -> None:
        self.ruta_archivo = Path(ruta_archivo)

    def cargar(self) -> ArchivoAgentes:
        if not self.ruta_archivo.exists():
            raise DataRepositoryError(f"No se encontro el archivo: {self.ruta_archivo}")
        try:
            contenido = self.ruta_archivo.read_text(encoding="utf-8")
            data = json.loads(contenido)
            return ArchivoAgentes.model_validate(data)
        except json.JSONDecodeError as e:
            raise DataRepositoryError(f"JSON invalido en {self.ruta_archivo}: {e}") from e
        except ValidationError as e:
            raise DataRepositoryError(
                f"Esquema invalido en {self.ruta_archivo}:\n{e}"
            ) from e

    def guardar(self, archivo: ArchivoAgentes) -> None:
        self.ruta_archivo.parent.mkdir(parents=True, exist_ok=True)
        serializado = archivo.model_dump(mode="json")
        self.ruta_archivo.write_text(
            json.dumps(serializado, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def obtener_por_id(self, agente_id: str) -> Optional[Agente]:
        archivo = self.cargar()
        for agente in archivo.agentes:
            if str(agente.id) == agente_id:
                return agente
        return None

    def listar(
        self,
        busqueda: Optional[str] = None,
        estado: Optional[str] = None,
        framework: Optional[str] = None,
    ) -> list[Agente]:
        archivo = self.cargar()
        resultado = archivo.agentes
        if busqueda:
            q = busqueda.lower()
            resultado = [
                a for a in resultado
                if q in a.metadata.nombre.lower()
                or q in a.metadata.descripcion.lower()
                or q in a.metadata.dueno.lower()
            ]
        if estado:
            resultado = [a for a in resultado if a.metadata.estado == estado]
        if framework:
            resultado = [a for a in resultado if a.metadata.framework == framework]
        return resultado
