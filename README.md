# Multiple Agent AI — Research Synthesis Agent

Sistema multi-agente de **investigación y síntesis** con patrón *orchestrator-worker*. Dada una pregunta de investigación, descompone el tema, investiga en paralelo (web, papers académicos y, opcionalmente, KB interna) y genera un **informe estructurado con citas ancladas** a hallazgos reales.

Puedes usarlo por **CLI**, por **API HTTP** o desde una **interfaz web académica** local, con exportación a **Markdown** y **PDF**.

> Paquete principal: [`research-synthesis-agent/`](research-synthesis-agent/)

---

## Características

- **Orquestación explícita** con [LangGraph](https://github.com/langchain-ai/langgraph): `orchestrator → researchers (fan-out) → synthesizer (fan-in)`
- **Fuentes en paralelo**: web (DuckDuckGo / Tavily / fake), papers (arXiv) y KB interna (Chroma; **deshabilitada por defecto** mientras el seed esté vacío)
- **Informe estructurado**: resumen ejecutivo, secciones por subpregunta, contradicciones, limitaciones y referencias `[1]`, `[2]`…
- **Citas grounded**: solo se citan `finding_id` reales; se excluyen citas `kb://` mientras la KB esté vacía
- **Referencias web alineadas a la consulta**: ranking por relevancia y filtrado de hits débiles
- **Degradación parcial**: si un worker falla, el grafo continúa con el resto
- **Reintentos inteligentes**: reformulación de subpreguntas débiles (`FAILED` / `INSUFFICIENT`)
- **Multi-LLM**: OpenAI, Anthropic, Gemini o modo `fake`
- **Resiliencia Gemini**: reintentos ante `503`/`429` (`ServerError`/`ClientError`) + **fallback automático** a modelos lite
- **Interfaz web** (`Synthesis`): UI académica, jobs con polling, export **Markdown** y **PDF** (texto real vía jsPDF)
- **API HTTP** (FastAPI): `POST/GET /api/research` + OpenAPI en `/docs`
- **Docker-first**: build multi-stage, usuario no-root, Compose listo para usar

---

## Arquitectura

```
                         ┌─────────────────────┐
                         │    Orchestrator     │
                         │  (plan + retries)   │
                         └──────────┬──────────┘
                                    │ fan-out
            ┌───────────────────────┼───────────────────────┐
            ▼                       ▼                       ▼
    WebResearcher          PapersResearcher       InternalKBResearcher
  (DuckDuckGo/Tavily/fake)      (arXiv/fake)         (Chroma; opcional)
            │                       │                       │
            └───────────────────────┼───────────────────────┘
                                    │ fan-in
                                    ▼
                            ┌───────────────┐
                            │  Synthesizer  │
                            │ → FinalReport │
                            └───────┬───────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                     ▼
            CLI                  API HTTP              UI web
         (src.main)             (src.api)            (frontend/)
                                                      MD + PDF
```

| Componente | Rol |
|------------|-----|
| **Orchestrator** | Descompone la query en 2–5 subpreguntas; asigna `web` / `paper` (no `internal_kb` mientras la KB esté vacía) |
| **WebResearcher** | Busca evidencia en internet (DuckDuckGo por defecto) y filtra por relevancia |
| **PapersResearcher** | Recupera papers de arXiv |
| **InternalKBResearcher** | Consulta Chroma si hay documentos seed; hoy el seed es `[]` |
| **Synthesizer** | Integra hallazgos, detecta contradicciones y emite el informe citado |
| **API + UI** | Jobs HTTP + UI académica con export Markdown/PDF |

### Flujo de una consulta

1. El usuario envía una pregunta (CLI, UI o API).
2. El **orchestrator** crea un `ResearchPlan` con subpreguntas concretas y fuentes habilitadas.
3. Los **researchers** corren en paralelo (`asyncio.gather`), con timeout y reintentos.
4. Si hay `FAILED` / `INSUFFICIENT`, el orchestrator puede **reformular** y reintentar.
5. El **synthesizer** produce un `FinalReport` (JSON + Markdown) y solo lista referencias usadas (web/paper).
6. CLI imprime Markdown; la UI muestra el informe y permite exportar **`.md`** o **`.pdf`**.

---

## Stack

| Capa | Tecnología |
|------|------------|
| Lenguaje | Python ≥ 3.11 |
| Orquestación | LangGraph + LangChain Core |
| Modelos | Pydantic v2 |
| LLMs | OpenAI · Anthropic · Gemini (`google-genai`) · fake |
| Web | DuckDuckGo (`duckduckgo-search`) · Tavily · fake |
| Papers | arXiv (`arxiv`) |
| Vector store | ChromaDB embebido |
| API | FastAPI + Uvicorn |
| Frontend | HTML/CSS/JS + jsPDF (export PDF) |
| Observabilidad | Logs JSON · LangSmith (opcional) |
| Runtime | Docker Compose · Makefile |

---

## Inicio rápido

### Opción A — Interfaz web (recomendado)

```bash
cd research-synthesis-agent
cp .env.example .env
# Edita .env y añade GEMINI_API_KEY (u otro LLM)

pip install -r requirements.txt
python -m src.api
# equivalente: make serve
```

Abre [http://127.0.0.1:8000](http://127.0.0.1:8000):

1. Escribe una pregunta de investigación.
2. Pulsa **Iniciar investigación**.
3. Espera el job (puede tardar 1–3 minutos según LLM, web y arXiv; Gemini puede reintentar o usar fallback si hay `503`).
4. Revisa resumen, hallazgos, contradicciones, limitaciones y referencias.
5. Exporta con **Exportar Markdown** o **Exportar PDF**.
6. Opcional: abre **Metodología** (plan + workers).

Documentación interactiva de la API: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

### Opción B — Docker (UI)

Requisitos: **Docker** + **Docker Compose**.

```bash
git clone https://github.com/DataScienceWorld1805/Multiple_Agent_AI.git
cd Multiple_Agent_AI/research-synthesis-agent

cp .env.example .env
# Edita .env y añade al menos la API key del LLM

make docker-build
make docker-serve
# http://127.0.0.1:8000
```

Rebuild limpio (cuando cambies código o front):

```bash
docker compose build --no-cache
docker compose run --rm -d -p 8000:8000 --name research-synthesis-ui app python -m src.api
```

### Opción C — Docker / CLI

```bash
make docker-run QUERY='¿Cuál es el estado actual de la fusión nuclear como fuente de energía comercial?'

# Guardar Markdown
docker compose run --rm app python -m src.main "tu pregunta" -o /app/data/report.md
```

### Opción D — CLI local

```bash
cd research-synthesis-agent
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux / macOS
# source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
python -m src.main "Estado de la fusión nuclear comercial" -o report.md
```

### Modo demo / offline (sin APIs)

En `.env`:

```env
LLM_PROVIDER=fake
SEARCH_PROVIDER=fake
PAPERS_PROVIDER=fake
```

Luego:

```bash
make run QUERY='What is the current status of commercial nuclear fusion?'
# o
make serve
```

---

## Configuración

Copia `.env.example` → `.env` dentro de `research-synthesis-agent/`.

### LLM (elige uno)

```env
# Gemini (recomendado en .env.example)
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.6-flash
GEMINI_API_KEY=tu-api-key

# OpenAI
# LLM_PROVIDER=openai
# LLM_MODEL=gpt-4o-mini
# OPENAI_API_KEY=sk-...

# Anthropic
# LLM_PROVIDER=anthropic
# LLM_MODEL=claude-3-5-sonnet-latest
# ANTHROPIC_API_KEY=sk-ant-...
```

> **Nota sobre Gemini:** modelos saturados pueden devolver `503 UNAVAILABLE` (sobre todo en corridas largas con varias llamadas). El cliente:
>
> 1. Reintenta ante `429`/`503` (`ClientError` y `ServerError`)
> 2. Si el modelo primario sigue fallando, prueba **fallbacks** (`gemini-flash-lite-latest`, `gemini-3.5-flash-lite`, etc.)
>
> Modelo por defecto del ejemplo: `gemini-3.6-flash`. Alternativas: `gemini-3.5-flash`, `gemini-flash-lite-latest`.

### Búsqueda y papers

```env
SEARCH_PROVIDER=duckduckgo   # web real sin API key (recomendado)
# SEARCH_PROVIDER=tavily
# TAVILY_API_KEY=tvly-...    # solo si SEARCH_PROVIDER=tavily
# SEARCH_PROVIDER=fake       # offline / tests
PAPERS_PROVIDER=arxiv        # o fake
```

### Variables principales

| Variable | Default (código) | Descripción |
|----------|------------------|-------------|
| `LLM_PROVIDER` | `openai` | `openai` · `anthropic` · `gemini` · `fake` |
| `LLM_MODEL` | `gpt-4o-mini` | Modelo del provider (ej. `gemini-3.6-flash`) |
| `LLM_TEMPERATURE` | `0.2` | Temperatura del LLM |
| `SEARCH_PROVIDER` | `duckduckgo` | `duckduckgo` · `tavily` · `fake` |
| `PAPERS_PROVIDER` | `arxiv` | `arxiv` · `fake` |
| `MAX_SUBQUESTIONS` | `5` | Máximo de subpreguntas del plan |
| `MIN_SUBQUESTIONS` | `2` | Mínimo de subpreguntas |
| `RESEARCHER_TIMEOUT_SECONDS` | `60` | Timeout por worker |
| `MAX_RETRIES` | `2` | Reintentos del orquestador |
| `WEB_MAX_RESULTS` | `5` | Resultados web por query |
| `ARXIV_MAX_RESULTS` | `5` | Papers por query |
| `KB_TOP_K` | `5` | Chunks recuperados de la KB |
| `KB_COLLECTION_NAME` | `internal_kb` | Colección Chroma |
| `CHROMA_PERSIST_DIR` | `data/chroma` | Persistencia del índice |
| `KB_SEED_PATH` | `data/kb_documents.json` | Seed de la KB interna |
| `LOG_LEVEL` | `INFO` | Nivel de logging |
| `LANGSMITH_TRACING` | `false` | Activar tracing LangSmith |

> `.env.example` usa `LLM_PROVIDER=gemini`, `LLM_MODEL=gemini-3.6-flash` y `SEARCH_PROVIDER=duckduckgo`.

### LangSmith (opcional)

```env
LANGSMITH_TRACING=true
LANGCHAIN_API_KEY=...
LANGCHAIN_PROJECT=research-synthesis-agent
```

---

## Interfaz web

La UI vive en [`research-synthesis-agent/frontend/`](research-synthesis-agent/frontend/) y la sirve FastAPI.

| Archivo | Rol |
|---------|-----|
| `frontend/index.html` | Estructura (consulta + informe + botones de export) |
| `frontend/styles.css` | Estilo académico |
| `frontend/app.js` | Jobs, polling, render del informe, export MD/PDF |

### Qué muestra

1. **Resumen ejecutivo**
2. **Hallazgos** (secciones por subpregunta, con enlaces a citas)
3. **Contradicciones** (si las hay)
4. **Limitaciones**
5. **Referencias** (web / paper; sin KB mientras el seed esté vacío)
6. **Metodología** (desplegable): plan + estado de workers
7. **Exportar Markdown** → `research-report.md`
8. **Exportar PDF** → `research-report.pdf` (generado con jsPDF: texto sólido, A4, saltos de página y numeración)

---

## API HTTP

Entrypoint: `python -m src.api` (Uvicorn en el puerto **8000**).

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/` | UI web |
| `GET` | `/api/health` | Estado + providers configurados |
| `POST` | `/api/research` | Crea un job de investigación |
| `GET` | `/api/research/{job_id}` | Estado / resultado del job |
| `GET` | `/docs` | Swagger UI (OpenAPI) |

### Crear investigación

```http
POST /api/research
Content-Type: application/json

{ "query": "¿Cuál es el paso a paso para redactar un informe de escena del crimen?" }
```

Respuesta:

```json
{
  "job_id": "40e856611377407287088a03bfb6ca83",
  "status": "queued"
}
```

### Consultar job

```http
GET /api/research/{job_id}
```

Estados: `queued` → `running` → `done` | `failed`.

Cuando `status` es `done`, incluye `plan`, `results_summary`, `report` (`FinalReport`) y `errors`.

Los jobs viven **en memoria** del proceso (se pierden al reiniciar). Pensado para uso local / demos.

---

## CLI

```text
python -m src.main QUERY... [-o/--output PATH]
```

| Argumento | Descripción |
|-----------|-------------|
| `QUERY` | Pregunta o tema de investigación |
| `-o` / `--output` | Ruta opcional para escribir el Markdown |

Ejemplos:

```bash
python -m src.main "Impacto de los LLM en la educación superior"
python -m src.main "Commercial nuclear fusion status" -o fusion-report.md
make run QUERY='¿Qué avances hay en stellarators?'
```

### Salida del informe

1. **Executive Summary**
2. **Secciones** por subpregunta
3. **Contradictions**
4. **Limitations**
5. **References** (citas numeradas ligadas a findings reales)

Programáticamente: `await build_graph().arun(query)` → `state["report"]`.

---

## Base de conocimiento interna (KB)

Corpus **local** indexado en Chroma para notas privadas / institucionales.

**Estado actual**

- Seed: [`data/kb_documents.json`](research-synthesis-agent/data/kb_documents.json) = `[]`
- Al arrancar con seed vacío, Chroma se **resetea** (sin documentos residuales)
- El orchestrator **no asigna** `internal_kb`
- El sintetizador **excluye** citas `kb://`

**Para reactivarla**

1. Añade documentos al JSON (o cambia `KB_SEED_PATH`).
2. Reinicia el servicio para reindexar.
3. Vuelve a permitir `internal_kb` en el plan del orchestrator.

Formato:

```json
[
  {
    "id": "kb-1",
    "title": "Brief interno",
    "content": "...",
    "source": "internal_kb",
    "metadata": { "topic": "...", "year": "2025" }
  }
]
```

---

## Contrato de datos (resumen)

| Modelo | Campos clave |
|--------|----------------|
| `SubQuestion` | `id`, `question`, `rationale`, `assigned_sources`, `priority` |
| `ResearchPlan` | `original_query`, `subquestions`, `max_subquestions`, `created_at` |
| `Finding` | `claim`, `evidence`, `source_*`, `confidence`, `relevance` |
| `ResearcherResult` | `researcher_type`, `findings`, `status`, `duration_ms` |
| `FinalReport` | `query`, `executive_summary`, `sections`, `contradictions`, `citations`, `limitations`, `markdown` |

Enums:

- `SourceType`: `web` · `paper` · `internal_kb`
- `ResearcherStatus`: `success` · `partial` · `failed` · `insufficient`

---

## Tests y calidad

```bash
cd research-synthesis-agent

make docker-test   # providers fake, sin APIs
make test          # pytest -q
make lint          # ruff + black --check
make format        # auto-fix
```

Hay tests unitarios (orchestrator, researchers, synthesizer) y un e2e con fakes.

---

## Makefile

| Target | Descripción |
|--------|-------------|
| `serve` | API + UI en `http://127.0.0.1:8000` |
| `run` | CLI en el host (`QUERY=...`) |
| `test` | Suite local |
| `lint` / `format` | Ruff + Black |
| `docker-build` | Construye la imagen |
| `docker-run` | CLI vía Compose |
| `docker-serve` | API + UI en contenedor (`-p 8000:8000`) |
| `docker-test` | `pytest` en contenedor con providers `fake` |

---

## Estructura del repositorio

```text
Multiple_Agent_AI/
├── README.md                         # Esta documentación
├── LICENSE
└── research-synthesis-agent/
    ├── src/
    │   ├── agents/                   # Orchestrator, researchers, synthesizer
    │   │   └── researchers/          # web · papers · internal_kb
    │   ├── graph/                    # LangGraph + arun()
    │   ├── schemas/                  # Pydantic + GraphState
    │   ├── providers/                # DuckDuckGo/Tavily, arXiv, Chroma
    │   ├── config.py
    │   ├── llm.py                    # Multi-provider + resiliencia Gemini
    │   ├── api.py                    # FastAPI (jobs + static UI)
    │   ├── main.py                   # CLI
    │   └── logging_utils.py
    ├── frontend/                     # UI académica + export MD/PDF
    │   ├── index.html
    │   ├── styles.css
    │   └── app.js
    ├── tests/
    ├── data/
    │   └── kb_documents.json         # Seed KB (vacío por defecto)
    ├── Dockerfile
    ├── docker-compose.yml
    ├── Makefile
    ├── pyproject.toml
    ├── requirements.txt
    └── .env.example
```

---

## Seguridad

- **Nunca** subas `.env` ni API keys. El `.gitignore` excluye `.env`, `.env.local` y `data/chroma/`.
- Las claves solo se leen por entorno / `env_file` de Compose.
- La imagen Docker corre como usuario no-root `app`.
- La API local **no** tiene autenticación (uso en localhost).

Claves típicas: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `TAVILY_API_KEY`, `LANGCHAIN_API_KEY`.

---

## Por qué LangGraph

- Nativo en Python con tipado + `asyncio`
- Grafo explícito orchestrator → workers → synthesizer
- Estado tipado, degradación parcial y LangSmith opcional
- Desacoplado del vendor de LLM

FastAPI/UI son **adaptadores**: invocan `build_graph().arun(query)` sin reemplazar el grafo.

---

## Limitaciones actuales

- Un solo paquete en el monorepo
- Jobs de la API en memoria (sin cola persistente)
- UI sin streaming fino por nodo (polling + hints de etapa)
- KB deshabilitada por seed vacío (reactivable)
- Calidad del informe depende de LLM + fuentes externas
- Gemini puede demorar más si reintenta o cambia a un modelo fallback
- Sin autenticación en la API

---

## Contribuir

Ideas bienvenidas: nuevos researchers, persistencia de jobs, SSE de etapas, reactivar/ampliar la KB, CI con GitHub Actions, más idiomas en el informe.

1. Fork del repo  
2. Rama (`git checkout -b feature/mi-mejora`)  
3. Tests (`make docker-test` o `make test`) y lint (`make lint`)  
4. Pull Request  

---

## Disclaimer

Proyecto experimental / educativo. Los informes **no sustituyen** revisión humana ni fuentes primarias verificadas. Valida siempre las citas antes de usar el contenido en contextos críticos.

---

## Licencia

Publicado bajo la [licencia MIT](LICENSE).

---

## Autor

Mantenido por [DataScienceWorld1805](https://github.com/DataScienceWorld1805) · repo: [Multiple_Agent_AI](https://github.com/DataScienceWorld1805/Multiple_Agent_AI)
