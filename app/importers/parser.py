"""Parser heuristico para importar agentes desde texto pegado, CSV o JSON.

Estrategia:
1. Detectar el formato del contenido (JSON, CSV, texto libre)
2. Si es JSON: parsear y validar contra el schema
3. Si es CSV: leer con DictReader, mapear columnas por nombre a campos
4. Si es texto libre: extraer campos por patrones (regex)

En cualquier caso, devuelve una lista de diccionarios que el caller
valida con Pydantic. Los campos que no se pueden inferir quedan vacios.
"""
from __future__ import annotations

import csv
import io
import json
import re
import uuid
from datetime import date
from typing import Any

from app.state import StagingStore


ESTADOS = {"Activo", "En Desarrollo", "En Pausa", "Deprecado"}
FRAMEWORKS = {"LangChain", "LlamaIndex", "Custom", "CrewAI", "AutoGen", "Otro"}
ENTORNOS = {"Produccion", "Staging", "Desarrollo", "Sandbox"}
NIVELES_ACCESO = {"Publico", "Interno", "Interno - Restringido", "Confidencial"}
PROVEEDORES_CONOCIDOS = {"OpenAI", "Anthropic", "Google", "Meta", "Mistral", "Cohere", "Azure", "AWS"}


def _aplicar_defaults(agente: dict) -> dict:
    """Rellena con defaults razonables los campos faltantes para que pase Pydantic.
    El caller sabra que un campo esta en su default (vs. explicitamente provisto)
    revisando si la clave existe."""
    md = agente.setdefault("metadata", {})
    if not isinstance(md, dict):
        md = {}
        agente["metadata"] = md
    hoy = date.today().isoformat()
    md.setdefault("nombre", "Agente sin nombre")
    md.setdefault("version", "0.1.0")
    md.setdefault("estado", "En Desarrollo")
    md.setdefault("framework", "Custom")
    md.setdefault("entorno_despliegue", "Sandbox")
    md.setdefault("dueno", "Sin asignar")
    md.setdefault("fecha_creacion", hoy)
    md.setdefault("ultima_actualizacion", hoy)
    md.setdefault("descripcion", "Descripcion por completar.")

    llm = agente.setdefault("llm_config", {})
    if not isinstance(llm, dict):
        llm = {}
        agente["llm_config"] = llm
    llm.setdefault("modelo", "Sin Modelo")
    llm.setdefault("temperatura", 0.0)
    llm.setdefault("proveedor", "N/A")
    llm.setdefault("max_tokens", 2048)
    llm.setdefault("system_prompt_resumen", "N/A")

    rag = agente.setdefault("rag_config", {})
    if not isinstance(rag, dict):
        rag = {}
        agente["rag_config"] = rag
    rag.setdefault("habilitado", False)
    if "fuentes_de_datos" not in rag or rag["fuentes_de_datos"] is None:
        rag["fuentes_de_datos"] = []

    agente.setdefault("tools", [])

    gob = agente.setdefault("gobernanza", {})
    if not isinstance(gob, dict):
        gob = {}
        agente["gobernanza"] = gob
    gob.setdefault("nivel_acceso", "Interno")
    gob.setdefault("maneja_datos_sensibles", False)
    gob.setdefault("tipos_datos_sensibles", [])
    gob.setdefault("cumple_compliance", [])
    gob.setdefault("politica_retencion", "90 dias")
    gob.setdefault("requiere_aprobacion_para_cambios", False)
    return agente


def _detectar_formato(contenido: str) -> str:
    s = contenido.strip()
    if not s:
        return "vacio"
    if s.startswith("{") or s.startswith("["):
        try:
            json.loads(s)
            return "json"
        except json.JSONDecodeError:
            pass
    lineas = [l for l in s.splitlines() if l.strip()]
    if len(lineas) >= 2:
        primera = lineas[0]
        segunda = lineas[1]
        if "," in primera and "," in segunda and len(primera.split(",")) == len(segunda.split(",")):
            return "csv"
    return "texto"


def _split_csv_inteligente(texto: str) -> list[list[str]]:
    """Lee CSV tolerante: detecta delimitador y maneja comillas."""
    muestra = texto[:4096]
    try:
        dialect = csv.Sniffer().sniff(muestra, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ","
    reader = csv.reader(io.StringIO(texto), dialect=dialect)
    return [row for row in reader if any(cell.strip() for cell in row)]


def _normalizar_clave(s: str) -> str:
    return (
        s.strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("á", "a").replace("é", "e").replace("í", "i")
        .replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    )


# Mapa de encabezados CSV comunes → campo interno
MAPA_COLUMNAS = {
    "nombre": "metadata.nombre",
    "name": "metadata.nombre",
    "version": "metadata.version",
    "estado": "metadata.estado",
    "status": "metadata.estado",
    "framework": "metadata.framework",
    "entorno": "metadata.entorno_despliegue",
    "entorno_despliegue": "metadata.entorno_despliegue",
    "environment": "metadata.entorno_despliegue",
    "dueno": "metadata.dueno",
    "owner": "metadata.dueno",
    "descripcion": "metadata.descripcion",
    "description": "metadata.descripcion",
    "modelo": "llm_config.modelo",
    "model": "llm_config.modelo",
    "temperatura": "llm_config.temperatura",
    "temperature": "llm_config.temperatura",
    "proveedor": "llm_config.proveedor",
    "provider": "llm_config.proveedor",
    "max_tokens": "llm_config.max_tokens",
    "rag": "rag_config.habilitado",
    "rag_habilitado": "rag_config.habilitado",
    "db_vectorial": "rag_config.db_vectorial",
    "vector_db": "rag_config.db_vectorial",
    "embeddings": "rag_config.embeddings",
    "fuentes": "rag_config.fuentes_de_datos",
    "fuentes_de_datos": "rag_config.fuentes_de_datos",
    "nivel_acceso": "gobernanza.nivel_acceso",
    "datos_sensibles": "gobernanza.maneja_datos_sensibles",
    "maneja_datos_sensibles": "gobernanza.maneja_datos_sensibles",
    "compliance": "gobernanza.cumple_compliance",
    "cumple_compliance": "gobernanza.cumple_compliance",
    "retencion": "gobernanza.politica_retencion",
    "politica_retencion": "gobernanza.politica_retencion",
}


def _set_camino(d: dict, camino: str, valor: Any) -> None:
    """Asigna d[camino] cuando camino es 'a.b.c'."""
    partes = camino.split(".")
    cur = d
    for p in partes[:-1]:
        cur = cur.setdefault(p, {})
        if not isinstance(cur, dict):
            return
    cur[partes[-1]] = valor


def _get_camino(d: dict, camino: str) -> Any:
    partes = camino.split(".")
    cur: Any = d
    for p in partes:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def _parse_bool(s: str) -> bool | None:
    s = s.strip().lower()
    if s in ("true", "si", "sí", "yes", "1", "x"):
        return True
    if s in ("false", "no", "0", ""):
        return False
    return None


def _parsear_csv(texto: str) -> list[dict]:
    filas = _split_csv_inteligente(texto)
    if not filas:
        return []
    encabezados = [_normalizar_clave(h) for h in filas[0]]
    resultado: list[dict] = []
    for fila in filas[1:]:
        agente: dict[str, Any] = {}
        for i, celda in enumerate(fila):
            if i >= len(encabezados):
                break
            encabezado = encabezados[i]
            campo = MAPA_COLUMNAS.get(encabezado)
            if not campo:
                continue
            valor: Any = celda.strip()
            if campo.endswith("temperatura"):
                try:
                    valor = float(valor)
                except ValueError:
                    continue
            elif campo.endswith("max_tokens"):
                try:
                    valor = int(valor)
                except ValueError:
                    continue
            elif campo.endswith("habilitado") or campo.endswith("maneja_datos_sensibles"):
                b = _parse_bool(str(valor))
                if b is None:
                    continue
                valor = b
            elif campo.endswith("fuentes_de_datos") or campo.endswith("cumple_compliance") or campo.endswith("tipos_datos_sensibles"):
                valor = [v.strip() for v in re.split(r"[;|]", str(valor)) if v.strip()]
            _set_camino(agente, campo, valor)
        if agente:
            _aplicar_defaults(agente)
            resultado.append(agente)
    return resultado


def _parsear_json(texto: str) -> list[dict]:
    data = json.loads(texto)
    
    # Heurística para JSON de Workflows (ej. n8n, Langflow, Custom)
    if isinstance(data, dict) and ("nodes" in data or "connections" in data or "name" in data):
        # Es posible que sea un WF exportado
        agente = {}
        nombre_wf = data.get("name", "Agente desde Workflow")
        _set_camino(agente, "metadata.nombre", nombre_wf)
        
        texto_nodos = json.dumps(data.get("nodes", []))
        
        # Intentar inferir framework
        if "langchain" in texto_nodos.lower():
            _set_camino(agente, "metadata.framework", "LangChain")
        elif "llamaindex" in texto_nodos.lower():
            _set_camino(agente, "metadata.framework", "LlamaIndex")
        
        # Intentar inferir modelo / proveedor
        if "gpt-4" in texto_nodos.lower():
            _set_camino(agente, "llm_config.modelo", "gpt-4o")
            _set_camino(agente, "llm_config.proveedor", "OpenAI")
        elif "claude" in texto_nodos.lower():
            _set_camino(agente, "llm_config.modelo", "claude-3-5-sonnet")
            _set_camino(agente, "llm_config.proveedor", "Anthropic")
            
        # Extraer herramientas (tools)
        tools = []
        for nodo in data.get("nodes", []):
            ntipo = nodo.get("type", "").lower()
            if "tool" in ntipo or "function" in ntipo:
                t_nombre = nodo.get("name", "Tool sin nombre")
                t_params = nodo.get("parameters", {})
                t_desc = t_params.get("toolDescription", t_params.get("description", "Herramienta extraída del workflow"))
                tools.append({
                    "nombre": t_nombre,
                    "descripcion": t_desc,
                    "tipo": nodo.get("type", "Custom Tool")
                })
        if tools:
            _set_camino(agente, "tools", tools)
            
        _aplicar_defaults(agente)
        return [agente]

    if isinstance(data, dict) and "agentes" in data:
        data = data["agentes"]
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    resultado = []
    for d in data:
        if isinstance(d, dict):
            _aplicar_defaults(d)
            resultado.append(d)
    return resultado


_PATRONES_TEXTO = [
    ("metadata.nombre", re.compile(r"(?:nombre|name|agente)\s*[:=]\s*([^\n,;]+)", re.IGNORECASE)),
    ("llm_config.modelo", re.compile(r"(?:modelo|model)\s*[:=]\s*([\w\.\-]+)", re.IGNORECASE)),
    ("llm_config.temperatura", re.compile(r"temperatura\s*[:=]\s*([0-9.]+)", re.IGNORECASE)),
    ("llm_config.proveedor", re.compile(r"proveedor\s*[:=]\s*([A-Za-z]+)", re.IGNORECASE)),
    ("metadata.framework", re.compile(r"framework\s*[:=]\s*([A-Za-z]+)", re.IGNORECASE)),
    ("metadata.estado", re.compile(r"estado\s*[:=]\s*([A-Za-z\s]+)", re.IGNORECASE)),
    ("metadata.entorno_despliegue", re.compile(r"entorno\s*[:=]\s*([A-Za-z]+)", re.IGNORECASE)),
    ("rag_config.db_vectorial", re.compile(r"(?:vector\s*db|db\s*vectorial|vectordb)\s*[:=]\s*([A-Za-z]+)", re.IGNORECASE)),
    ("rag_config.embeddings", re.compile(r"embeddings?\s*[:=]\s*([\w\.\-]+)", re.IGNORECASE)),
    ("gobernanza.nivel_acceso", re.compile(r"(?:nivel\s*acceso|acceso)\s*[:=]\s*([A-Za-z\s\-]+)", re.IGNORECASE)),
]


def _parsear_texto(texto: str) -> list[dict]:
    """Texto libre: cada parrafo/bloque separado por linea vacia = 1 agente."""
    bloques = re.split(r"\n\s*\n", texto.strip())
    agentes: list[dict] = []
    for bloque in bloques:
        agente: dict[str, Any] = {}
        for campo, patron in _PATRONES_TEXTO:
            m = patron.search(bloque)
            if not m:
                continue
            valor: Any = m.group(1).strip()
            if campo.endswith("temperatura"):
                try:
                    valor = float(valor)
                except ValueError:
                    continue
            _set_camino(agente, campo, valor)
        if not agente:
            continue
        agente.setdefault("metadata", {})
        if not isinstance(agente["metadata"], dict):
            continue
        if not agente["metadata"].get("nombre"):
            primera = bloque.strip().splitlines()[0].strip()
            if primera and len(primera) < 120:
                agente["metadata"]["nombre"] = primera[:120]
        if not agente["metadata"].get("nombre"):
            continue
        agente["metadata"].setdefault("descripcion", bloque.strip()[:500])
        agente["metadata"].setdefault("version", "0.1.0")
        agente["metadata"].setdefault("estado", "En Desarrollo")
        agente["metadata"].setdefault("framework", "Custom")
        agente["metadata"].setdefault("entorno_despliegue", "Staging")
        agente["metadata"].setdefault("dueno", "Sin asignar")
        hoy = date.today().isoformat()
        agente["metadata"].setdefault("fecha_creacion", hoy)
        agente["metadata"].setdefault("ultima_actualizacion", hoy)
        agente.setdefault("llm_config", {})
        if not isinstance(agente["llm_config"], dict):
            agente["llm_config"] = {}
        agente["llm_config"].setdefault("modelo", "Sin Modelo")
        agente["llm_config"].setdefault("temperatura", 0.0)
        agente["llm_config"].setdefault("proveedor", "N/A")
        agente["llm_config"].setdefault("max_tokens", 2048)
        agente["llm_config"].setdefault(
            "system_prompt_resumen", "N/A"
        )
        agente.setdefault("rag_config", {"habilitado": False, "fuentes_de_datos": []})
        agente.setdefault("tools", [])
        agente.setdefault("gobernanza", {
            "nivel_acceso": "Interno",
            "maneja_datos_sensibles": False,
            "tipos_datos_sensibles": [],
            "cumple_compliance": [],
            "politica_retencion": "90 dias",
            "requiere_aprobacion_para_cambios": False,
        })
        agentes.append(agente)
    return agentes


def parsear(contenido: str) -> tuple[str, list[dict], list[str]]:
    """Detecta formato y devuelve (formato, diccionarios, errores)."""
    formato = _detectar_formato(contenido)
    if formato == "vacio":
        return formato, [], ["Contenido vacio"]
    try:
        if formato == "json":
            return formato, _parsear_json(contenido), []
        if formato == "csv":
            return formato, _parsear_csv(contenido), []
        return formato, _parsear_texto(contenido), []
    except Exception as e:
        return formato, [], [f"Error al parsear: {e}"]


def parsear_archivo(nombre: str, contenido: bytes | str) -> tuple[str, list[dict], list[str]]:
    if isinstance(contenido, bytes):
        try:
            contenido = contenido.decode("utf-8")
        except UnicodeDecodeError:
            contenido = contenido.decode("latin-1", errors="replace")
    return parsear(contenido)
