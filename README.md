# Archivero de Agentes AI · Dashboard de Gobernanza

Dashboard ejecutivo y técnico para presentar el inventario de agentes de IA de la organización a stakeholders. Pensado para responder tres preguntas en una mirada:

1. **¿Cuántos agentes tenemos y en qué estado están?**
2. **¿Qué modelos, frameworks y proveedores usamos?**
3. **¿Qué tan seguros son? (datos sensibles, compliance, gobernanza)**

---

## Características

- **Dashboard ejecutivo** con tarjetas resumen, 3 gráficas (Chart.js) y tabla con badges por estado/modelo/entorno
- **Vista de detalle** por agente con 4 paneles: Arquitectura, RAG, Herramientas, Gobernanza
- **API JSON** documentada automáticamente en `/docs`
- **Validación estricta** del esquema vía Pydantic v2
- **Tests** con pytest
- **Docker** listo para producción
- **CI** con GitHub Actions

---

## Stack

| Capa | Tecnología |
|---|---|
| Backend | Python 3.11+ / FastAPI |
| Frontend | Jinja2 + TailwindCSS (CDN) + Chart.js (CDN) + FontAwesome (CDN) |
| Datos | JSON (validado con Pydantic) |
| Tests | pytest |
| Container | Docker |

---

## Estructura del proyecto

```
archivero-agentes-ai/
├── app/
│   ├── main.py              ← FastAPI app + lifespan
│   ├── models.py            ← Modelos Pydantic (esquema)
│   ├── repository.py        ← Carga/persistencia del JSON
│   ├── routers/
│   │   ├── pages.py         ← Rutas HTML (/, /agentes/{id})
│   │   └── api.py           ← Rutas JSON (/api/...)
│   └── templates/
│       ├── base.html
│       ├── dashboard.html
│       └── agente_detalle.html
├── data/
│   └── agentes.json         ← Base de datos (3 agentes de ejemplo)
├── tests/
│   └── test_basic.py
├── .github/workflows/ci.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## Ejecución local

### Opción 1: Python directo

```bash
# 1. Clonar e instalar
git clone <repo>
cd archivero-agentes-ai
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Configurar (opcional)
cp .env.example .env

# 3. Correr
uvicorn app.main:app --reload

# 4. Abrir
# http://localhost:8000          → Dashboard
# http://localhost:8000/docs     → API docs (Swagger)
# http://localhost:8000/health   → Healthcheck
```

### Opción 2: Docker

```bash
docker build -t archivero-agentes .
docker run -p 8000:8000 archivero-agentes
```

---

## ¿Cómo agregar un agente nuevo?

Edita `data/agentes.json` y agrega un objeto al arreglo `agentes` siguiendo el esquema validado por Pydantic. El campo `id` debe ser un UUID v4.

Reinicia el servidor (o `Ctrl+C` y `uvicorn app.main:app --reload` de nuevo).

---

## Esquema del agente (v1.0)

```jsonc
{
  "id": "uuid-v4",
  "metadata": {
    "nombre": "string",
    "version": "semver",
    "estado": "Activo | En Desarrollo | En Pausa | Deprecado",
    "framework": "LangChain | LlamaIndex | Custom | CrewAI | AutoGen | Otro",
    "entorno_despliegue": "Produccion | Staging | Desarrollo | Sandbox",
    "dueno": "string",
    "fecha_creacion": "YYYY-MM-DD",
    "ultima_actualizacion": "YYYY-MM-DD",
    "descripcion": "string"
  },
  "llm_config": {
    "modelo": "string",
    "temperatura": 0.0-2.0,
    "proveedor": "string",
    "max_tokens": "int > 0",
    "system_prompt_resumen": "string"
  },
  "rag_config": {
    "habilitado": true,
    "db_vectorial": "Pinecone | Weaviate | ChromaDB | ...",
    "embeddings": "string",
    "fuentes_de_datos": ["string"],
    "chunk_size": "int",
    "chunk_overlap": "int"
  },
  "tools": [
    { "nombre": "string", "tipo": "API | RAG | SQL | Codigo", "descripcion": "string" }
  ],
  "gobernanza": {
    "nivel_acceso": "Publico | Interno | Interno - Restringido | Confidencial",
    "maneja_datos_sensibles": "bool",
    "tipos_datos_sensibles": ["string"],
    "cumple_compliance": ["string"],
    "politica_retencion": "string",
    "requiere_aprobacion_para_cambios": "bool"
  }
}
```

---

## API

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/` | Dashboard ejecutivo |
| GET | `/agentes/{id}` | Vista detallada de un agente |
| GET | `/api/agentes` | Lista agentes (filtros: `?q=`, `?estado=`, `?framework=`) |
| GET | `/api/agentes/{id}` | Detalle JSON de un agente |
| GET | `/api/stats` | Estadísticas agregadas |
| GET | `/health` | Healthcheck |
| GET | `/docs` | Swagger UI |

---

## Tests

```bash
pytest -v
```

---

## Roadmap (ideas para v2)

- [ ] Formulario web para crear/editar agentes (sin tocar JSON)
- [ ] Export del dashboard a PDF
- [ ] Historial de versiones por agente
- [ ] Métricas de uso reales (ejecuciones, costos)
- [ ] Conector automático para extraer config desde n8n
- [ ] Comparativa lado a lado entre dos agentes
- [ ] Autenticación (OAuth/SSO)

---

## Licencia

MIT
