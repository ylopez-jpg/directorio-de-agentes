"""Deteccion automatica de integraciones y analisis LLM de agentes."""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# Catalogo de integraciones conocidas: patron -> metadata.
# El patron se busca case-insensitive sobre cualquier campo de texto del agente.
INTEGRATIONS: list[dict[str, Any]] = [
    {
        "key": "anythingllm",
        "nombre": "AnythingLLM",
        "icono": "fa-solid fa-brain",
        "color": "text-purple-400",
        "categoria": "RAG / Knowledge",
        "patrones": [r"\banythingllm\b", r"\banything\s*llm\b"],
    },
    {
        "key": "pinecone",
        "nombre": "Pinecone",
        "icono": "fa-solid fa-map-pin",
        "color": "text-blue-400",
        "categoria": "Vector DB",
        "patrones": [r"\bpinecone\b"],
    },
    {
        "key": "weaviate",
        "nombre": "Weaviate",
        "icono": "fa-solid fa-cube",
        "color": "text-green-400",
        "categoria": "Vector DB",
        "patrones": [r"\bweaviate\b"],
    },
    {
        "key": "chroma",
        "nombre": "ChromaDB",
        "icono": "fa-solid fa-palette",
        "color": "text-orange-400",
        "categoria": "Vector DB",
        "patrones": [r"\bchroma(d)?db?\b", r"\bchroma\b"],
    },
    {
        "key": "qdrant",
        "nombre": "Qdrant",
        "icono": "fa-solid fa-vector-square",
        "color": "text-rose-400",
        "categoria": "Vector DB",
        "patrones": [r"\bqdrant\b"],
    },
    {
        "key": "faiss",
        "nombre": "FAISS",
        "icono": "fa-solid fa-bolt",
        "color": "text-yellow-400",
        "categoria": "Vector DB",
        "patrones": [r"\bfaiss\b"],
    },
    {
        "key": "openai",
        "nombre": "OpenAI",
        "icono": "fa-solid fa-m",
        "color": "text-emerald-400",
        "categoria": "LLM Provider",
        "patrones": [r"\bopenai\b", r"\bgpt-?[0-9]", r"\bo[0-9]-?\w*\b"],
    },
    {
        "key": "anthropic",
        "nombre": "Anthropic",
        "icono": "fa-solid fa-a",
        "color": "text-amber-400",
        "categoria": "LLM Provider",
        "patrones": [r"\banthropic\b", r"\bclaude\b"],
    },
    {
        "key": "google",
        "nombre": "Google AI",
        "icono": "fa-solid fa-g",
        "color": "text-sky-400",
        "categoria": "LLM Provider",
        "patrones": [r"\bgoogle\b", r"\bgemini\b", r"\bvertex\s*ai\b"],
    },
    {
        "key": "mcp",
        "nombre": "MCP (Model Context Protocol)",
        "icono": "fa-solid fa-plug",
        "color": "text-cyan-400",
        "categoria": "Tool Protocol",
        "patrones": [r"\bmcp\b", r"\bmodel\s*context\s*protocol\b"],
    },
    {
        "key": "n8n",
        "nombre": "n8n",
        "icono": "fa-solid fa-diagram-project",
        "color": "text-pink-400",
        "categoria": "Orquestador",
        "patrones": [r"\bn8n\b"],
    },
    {
        "key": "langchain",
        "nombre": "LangChain",
        "icono": "fa-solid fa-link",
        "color": "text-lime-400",
        "categoria": "Framework",
        "patrones": [r"\blangchain\b", r"\blang\s*chain\b"],
    },
    {
        "key": "llamaindex",
        "nombre": "LlamaIndex",
        "icono": "fa-solid fa-llama",
        "color": "text-teal-400",
        "categoria": "Framework",
        "patrones": [r"\bllamaindex\b", r"\bllama\s*index\b"],
    },
    {
        "key": "crewai",
        "nombre": "CrewAI",
        "icono": "fa-solid fa-people-group",
        "color": "text-fuchsia-400",
        "categoria": "Framework",
        "patrones": [r"\bcrewai\b", r"\bcrew\s*ai\b"],
    },
    {
        "key": "autogen",
        "nombre": "AutoGen",
        "icono": "fa-solid fa-robot",
        "color": "text-indigo-400",
        "categoria": "Framework",
        "patrones": [r"\bautogen\b"],
    },
    {
        "key": "twilio",
        "nombre": "Twilio (SMS/WhatsApp)",
        "icono": "fa-solid fa-message",
        "color": "text-red-400",
        "categoria": "Canal",
        "patrones": [r"\btwilio\b", r"\bwhatsapp\b", r"\bsms\b"],
    },
    {
        "key": "supabase",
        "nombre": "Supabase",
        "icono": "fa-solid fa-database",
        "color": "text-emerald-300",
        "categoria": "Datos",
        "patrones": [r"\bsupabase\b"],
    },
    {
        "key": "datatables",
        "nombre": "DataTables / Logging",
        "icono": "fa-solid fa-table",
        "color": "text-zinc-300",
        "categoria": "Datos",
        "patrones": [r"\bdatatables?\b"],
    },
]


def _iter_text_fields(agente: dict) -> Iterable[tuple[str, str]]:
    """Genera (campo_path, valor) para todos los strings del agente."""
    def walk(node: Any, path: str):
        if isinstance(node, dict):
            for k, v in node.items():
                yield from walk(v, f"{path}.{k}" if path else k)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                yield from walk(item, f"{path}[{i}]")
        elif isinstance(node, str):
            yield path, node
    yield from walk(agente, "")


def detectar_integraciones(agente_dict: dict) -> list[dict]:
    """Escanea todos los campos de texto del agente y devuelve las
    integraciones detectadas con la lista de campos donde aparecen.
    """
    campos_por_key: dict[str, list[str]] = {}
    blob = json.dumps(agente_dict, ensure_ascii=False)
    for integ in INTEGRATIONS:
        campos: list[str] = []
        for path, value in _iter_text_fields(agente_dict):
            valor_lower = value.lower()
            for patron in integ["patrones"]:
                if re.search(patron, valor_lower, re.IGNORECASE):
                    if path not in campos:
                        campos.append(path)
                    break
        if campos:
            campos_por_key[integ["key"]] = campos

    resultado = []
    for integ in INTEGRATIONS:
        if integ["key"] in campos_por_key:
            resultado.append({
                **integ,
                "patrones": None,  # no exponer regex al frontend
                "detectado_en": campos_por_key[integ["key"]],
                "total_menciones": sum(
                    len(re.findall(p, blob, re.IGNORECASE))
                    for p in integ["patrones"]
                ),
            })
    return resultado


def resumen_conexiones(agente_dict: dict) -> dict:
    """Resumen rapido: cuantos servicios, por categoria, cuantos LLMs, etc."""
    dets = detectar_integraciones(agente_dict)
    por_categoria: dict[str, int] = {}
    for d in dets:
        por_categoria[d["categoria"]] = por_categoria.get(d["categoria"], 0) + 1
    return {
        "total_integraciones": len(dets),
        "por_categoria": por_categoria,
        "tiene_rag": any(d["key"] in {"pinecone", "weaviate", "chroma", "qdrant", "faiss"} for d in dets),
        "tiene_mcp": any(d["key"] == "mcp" for d in dets),
        "proveedores_llm": [d["nombre"] for d in dets if d["categoria"] == "LLM Provider"],
        "frameworks": [d["nombre"] for d in dets if d["categoria"] == "Framework"],
    }


# ---------------------------------------------------------------------------
# Analisis LLM on-demand (Anthropic)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_LLM = """Eres un auditor tecnico senior de agentes de IA. Tu trabajo es
revisar la configuracion de un agente y devolver un analisis estructurado en
Markdown. Se conciso y especifico. Responde en espanol.

Estructura obligatoria (usa estos encabezados exactos):

## Componentes detectados
Enumera los componentes reales del agente (framework, LLM, RAG, tools).

## Conexiones externas
Lista cualquier servicio externo (Pinecone, AnythingLLM, MCP, etc.) y que hace
el agente con cada uno. Si una conexion parece declarada pero no usada, senalalo.

## Riesgos y gobernanza
Riesgos potenciales: datos sensibles, prompt injection, alucinaciones, falta de
compliance, configuracion riesgosa (temperatura alta, RAG deshabilitado en
agentes que lo necesitan, etc.).

## Recomendaciones
3 a 5 acciones concretas priorizadas (Alta / Media / Baja).

## Veredicto
Una sola linea: APTO / APTO CON OBSERVACIONES / NO APTO para produccion.
"""


def analizar_con_llm(agente_dict: dict, api_key: str | None) -> str:
    """Envia el agente a Claude y devuelve el analisis en markdown.

    Si no hay api_key, devuelve un string con instrucciones para configurarla.
    """
    if not api_key:
        return (
            "**Analisis LLM deshabilitado.**\n\n"
            "Configura la variable de entorno `ANTHROPIC_API_KEY` "
            "(o `ANTHROPIC_AUTH_TOKEN` para gateways compatibles) y reinicia "
            "el servidor para habilitar el analisis automatico con Claude."
        )

    try:
        import anthropic
    except ImportError as e:
        return f"**SDK anthropic no instalado:** {e}"

    cliente = anthropic.Anthropic(api_key=api_key)
    payload = json.dumps(agente_dict, ensure_ascii=False, indent=2)
    mensaje = cliente.messages.create(
        model=os.getenv("ANALYSIS_MODEL", "claude-sonnet-5"),
        max_tokens=1500,
        system=SYSTEM_PROMPT_LLM,
        messages=[
            {
                "role": "user",
                "content": (
                    "Analiza este agente de IA. Devuelve el informe en el "
                    "formato indicado:\n\n```json\n" + payload + "\n```"
                ),
            }
        ],
    )
    # messages.content es una lista de bloques; concatenamos los de tipo text.
    partes = [b.text for b in mensaje.content if getattr(b, "type", None) == "text"]
    return "\n\n".join(partes) if partes else "(respuesta vacia del modelo)"
