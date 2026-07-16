"""Modelos Pydantic para validar el esquema de agentes.json."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


EstadoAgente = Literal["Activo", "En Desarrollo", "En Pausa", "Deprecado"]
FrameworkAgente = Literal["LangChain", "LlamaIndex", "Custom", "CrewAI", "AutoGen", "Otro"]
EntornoDespliegue = Literal["Produccion", "Staging", "Desarrollo", "Sandbox"]
NivelAcceso = Literal["Publico", "Interno", "Interno - Restringido", "Confidencial"]


class Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: str = Field(..., min_length=1, max_length=120)
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+(-[a-z0-9.]+)?$")
    estado: EstadoAgente
    framework: FrameworkAgente
    entorno_despliegue: EntornoDespliegue
    dueno: str
    fecha_creacion: date
    ultima_actualizacion: date
    descripcion: str = Field(..., min_length=1)

    @field_validator("ultima_actualizacion")
    @classmethod
    def fecha_no_futura(cls, v: date, info) -> date:
        creacion = info.data.get("fecha_creacion")
        if creacion and v < creacion:
            raise ValueError("ultima_actualizacion no puede ser anterior a fecha_creacion")
        return v


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modelo: str
    temperatura: float = Field(..., ge=0.0, le=2.0)
    proveedor: str
    max_tokens: int = Field(..., gt=0)
    system_prompt_resumen: str = Field(..., min_length=1)


class RAGConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    habilitado: bool
    db_vectorial: Optional[str] = None
    embeddings: Optional[str] = None
    fuentes_de_datos: list[str] = Field(default_factory=list)
    chunk_size: Optional[int] = Field(default=None, gt=0)
    chunk_overlap: Optional[int] = Field(default=None, ge=0)


class Tool(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: str
    tipo: str
    descripcion: str


class Gobernanza(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nivel_acceso: NivelAcceso
    maneja_datos_sensibles: bool
    tipos_datos_sensibles: list[str] = Field(default_factory=list)
    cumple_compliance: list[str] = Field(default_factory=list)
    politica_retencion: str
    requiere_aprobacion_para_cambios: bool


class Agente(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    metadata: Metadata
    llm_config: LLMConfig
    rag_config: RAGConfig
    tools: list[Tool] = Field(default_factory=list)
    gobernanza: Gobernanza


class ArchivoAgentes(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str
    ultima_actualizacion: date
    agentes: list[Agente] = Field(default_factory=list)
