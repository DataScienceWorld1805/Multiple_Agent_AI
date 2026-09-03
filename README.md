# Multiple Agent AI — Research Synthesis Agent

Sistema multi-agente de **investigación y síntesis** con patrón *orchestrator-worker*. Dada una pregunta de investigación, descompone el tema, investiga en paralelo (web, papers académicos y base de conocimiento interna) y genera un **informe estructurado con citas ancladas** a hallazgos reales.

Puedes usarlo por **CLI**, por **API HTTP** o desde una **interfaz web académica** local.

> Paquete principal: [`research-synthesis-agent/`](research-synthesis-agent/)

---

## Características

- **Orquestación explícita** con [LangGraph](https://github.com/langchain-ai/langgraph): `orchestrator → researchers (fan-out) → synthesizer (fan-in)`
- **Tres fuentes en paralelo**: búsqueda web (Tavily), papers (arXiv) y KB interna (Chroma embebido)
- **Informe estructurado**: resumen ejecutivo, secciones por subpregunta, contradicciones explícitas, limitaciones y referencias `[1]`, `[2]`…
- **Citas grounded**: solo se citan `finding_id` reales producidos por los researchers
- **Degradación parcial**: si un worker falla, el grafo continúa con el resto
- **Reintentos inteligentes**: reformulación de subpreguntas débiles (`FAILED` / `INSUFFICIENT`)
- **Multi-LLM**: OpenAI, Anthropic, Gemini o modo `fake` (sin APIs, ideal para demos y CI)
- **Interfaz web** (`Synthesis`): UI académica para lanzar consultas y leer el informe
- **API HTTP** (FastAPI): jobs asíncronos con polling (`POST/GET /api/research`)
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
      (Tavily/fake)             (arXiv/fake)            (Chroma)
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
```

| Componente | Rol |
|------------|-----|
| **Orchestrator** | Descompone la query en 2–5 subpreguntas y asigna fuentes (`web` / `paper` / `internal_kb`) |
| **WebResearcher** | Busca evidencia en la web vía Tavily (o fake) |
| **PapersResearcher** | Recupera papers de arXiv (sin API key) |
| **InternalKBResearcher** | Consulta una KB vectorial local (Chroma + seed JSON) |
| **Synthesizer** | Integra hallazgos, detecta contradicciones y emite el informe citado |
| **API + UI** | Expone el grafo como jobs HTTP y renderiza el informe en el navegador |

### Flujo de una consulta

1. El usuario envía una pregunta (CLI, UI o API).
2. El **orchestrator** crea un `ResearchPlan` con subpreguntas y fuentes asignadas.
3. Los **researchers** se ejecutan en paralelo (`asyncio.gather`), con timeout y reintentos.
4. Si hay resultados `FAILED` / `INSUFFICIENT`, el orchestrator puede **reformular** y reintentar.
5. El **synthesizer** produce un `FinalReport` (JSON + Markdown).
6. CLI imprime Markdown; la UI muestra el informe tipado y permite exportarlo.

---

## Stack

| Capa | Tecnología |
|------|------------|
| Lenguaje | Python ≥ 3.11 |
| Orquestación | LangGraph + LangChain Core |
| Modelos | Pydantic v2 |
| LLMs | OpenAI · Anthropic · Gemini (`google-genai`) · fake |
| Web | Tavily (`httpx` + retries) |
| Papers | arXiv (paquete `arxiv`) |
| Vector store | ChromaDB embebido |
| API | FastAPI + Uvicorn |
| Frontend | HTML/CSS/JS estático (servido por FastAPI) |
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
3. Espera el job (puede tardar 1–3 minutos según LLM y fuentes).
4. Revisa resumen, hallazgos, contradicciones, limitaciones y referencias.
5. Exporta el Markdown o abre la sección de metodología (plan + workers).

Documentación interactiva de la API: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

### Opción B — Docker (CLI)

Requisitos: **Docker** + **Docker Compose**.

```bash
git clone https://github.com/DataScienceWorld1805/Multiple_Agent_AI.git
cd Multiple_Agent_AI/research-synthesis-agent

cp .env.example .env
# Edita .env y añade al menos la API key del LLM que uses

make docker-build
make docker-run QUERY='¿Cuál es el estado actual de la fusión nuclear como fuente de energía comercial?'
```

Para guardar el informe:

```bash
docker compose run --rm app python -m src.main "tu pregunta" -o /app/data/report.md
```

UI en Docker:

```bash
make docker-serve
# luego http://127.0.0.1:8000
```

### Opción C — CLI local

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
make serve   # UI con respuestas deterministas
```

---

## Configuración

Copia `.env.example` → `.env` dentro de `research-synthesis-agent/`.

### LLM (elige uno)

```env
# Gemini (recomendado en .env.example)
LLM_PROVIDER=gemini
LLM_MODEL=gemini-flash-latest
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

> **Nota sobre Gemini:** modelos antiguos como `gemini-2.0-flash` pueden devolver `404 NOT_FOUND`. El ejemplo del proyecto usa `gemini-flash-latest`. Si un modelo falla, lista los disponibles con el SDK `google-genai` o prueba `gemini-3.6-flash` / `gemini-flash-latest`.

### Búsqueda y papers

```env
SEARCH_PROVIDER=tavily   # o fake
TAVILY_API_KEY=tvly-...  # solo si SEARCH_PROVIDER=tavily
PAPERS_PROVIDER=arxiv    # o fake
```

### Variables principales

| Variable | Default (código) | Descripción |
|----------|------------------|-------------|
| `LLM_PROVIDER` | `openai` | `openai` · `anthropic` · `gemini` · `fake` |
| `LLM_MODEL` | `gpt-4o-mini` | Modelo del provider elegido |
| `LLM_TEMPERATURE` | `0.2` | Temperatura del LLM |
| `SEARCH_PROVIDER` | `tavily` | `tavily` · `fake` |
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

> `.env.example` usa `LLM_PROVIDER=gemini` y `SEARCH_PROVIDER=fake` para un arranque económico. Los defaults de `config.py` aplican si no defines `.env`.

### LangSmith (opcional)

```env
LANGSMITH_TRACING=true
LANGCHAIN_API_KEY=...
LANGCHAIN_PROJECT=research-synthesis-agent
```

---

## Interfaz web

La UI vive en [`research-synthesis-agent/frontend/`](research-synthesis-agent/frontend/) y la sirve FastAPI junto a la API.

| Archivo | Rol |
|---------|-----|
| `frontend/index.html` | Estructura de la página (consulta + informe) |
| `frontend/styles.css` | Estilo académico (serif para lectura, navy institucional) |
| `frontend/app.js` | Lanza jobs, hace polling y renderiza el `FinalReport` |

### Qué muestra

1. **Resumen ejecutivo**
2. **Hallazgos** (secciones por subpregunta, con enlaces a citas `[n]`)
3. **Contradicciones** (si las hay)
4. **Limitaciones**
5. **Referencias** (bibliografía con tipo de fuente: web / paper / internal_kb)
6. **Metodología** (desplegable): plan del orchestrator + estado de cada worker
7. **Exportar Markdown** del informe completo

La barra de estado indica etapas aproximadas mientras el job corre en segundo plano.

---

## API HTTP

Entrypoint: `python -m src.api` (Uvicorn en el puerto **8000**).

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/` | UI web |
| `GET` | `/api/health` | Estado del servicio + providers configurados |
| `POST` | `/api/research` | Crea un job de investigación |
| `GET` | `/api/research/{job_id}` | Consulta estado / resultado del job |
| `GET` | `/docs` | Swagger UI (OpenAPI) |

### Crear investigación

```http
POST /api/research
Content-Type: application/json

{ "query": "¿Cuál es el estado actual de la fusión nuclear comercial?" }
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

Cuando `status` es `done`, la respuesta incluye:

- `plan` — plan de subpreguntas
- `results_summary` — resumen por worker (tipo, status, hallazgos, duración)
- `report` — `FinalReport` completo (`executive_summary`, `sections`, `contradictions`, `citations`, `limitations`, `markdown`)
- `errors` — errores no fatales del grafo

Los jobs se guardan **en memoria** del proceso (se pierden al reiniciar el servidor). Suficiente para uso local / demos.

---

## CLI

```text
python -m src.main QUERY... [-o/--output PATH]
```

| Argumento | Descripción |
|-----------|-------------|
| `QUERY` | Pregunta o tema de investigación (una o más palabras) |
| `-o` / `--output` | Ruta opcional para escribir el Markdown (también se imprime por stdout) |

Ejemplos:

```bash
python -m src.main "Impacto de los LLM en la educación superior"
python -m src.main "Commercial nuclear fusion status" -o fusion-report.md
make run QUERY='¿Qué avances hay en stellarators?'
```

### Salida del informe

El Markdown generado incluye:

1. **Executive Summary** — síntesis de alto nivel  
2. **Secciones** — una por subpregunta del plan  
3. **Contradictions** — conflictos entre fuentes (no se promedian)  
4. **Limitations** — huecos y sesgos detectados  
5. **References** — citas numeradas ligadas a findings reales  

Programáticamente, el mismo contenido está en `FinalReport` tras `await build_graph().arun(query)`.

---

## Base de conocimiento interna (KB)

La **KB interna** es un corpus **local y propio** indexado en Chroma. Sirve para:

- Incorporar notas institucionales, briefs o documentos privados que no están en la web
- Contrastar evidencia externa (web/arXiv) con conocimiento interno
- Demostrar una tercera fuente en el patrón multi-agente

El seed de demo está en [`research-synthesis-agent/data/kb_documents.json`](research-synthesis-agent/data/kb_documents.json) (briefs sobre fusión nuclear). Formato:

```json
[
  {
    "id": "kb-fusion-1",
    "title": "Internal Brief: Magnetic Fusion Pilots",
    "content": "...",
    "source": "internal_kb",
    "metadata": { "topic": "fusion", "year": "2024" }
  }
]
```

Cómo usarla:

1. Amplía o reemplaza el JSON con tu corpus.
2. Apunta `KB_SEED_PATH` si usas otra ruta.
3. Chroma persiste el índice en `data/chroma/` (ignorado por git).
4. Cuando el orchestrator asigne `internal_kb` a una subpregunta, el `InternalKBResearcher` recupera los `KB_TOP_K` fragmentos más similares y los cita como `kb://{doc_id}`.

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

# En Docker (providers fake, sin APIs)
make docker-test

# En local
make test      # pytest -q
make lint      # ruff + black --check
make format    # auto-fix
```

Hay tests unitarios (orchestrator, researchers, synthesizer) y un e2e con fakes inyectados.

---

## Makefile

| Target | Descripción |
|--------|-------------|
| `serve` | Arranca API + UI en `http://127.0.0.1:8000` |
| `run` | Corre el CLI en el host (`QUERY=...`) |
| `test` | Suite de tests local |
| `lint` / `format` | Ruff + Black |
| `docker-build` | Construye la imagen multi-stage |
| `docker-run` | Ejecuta el CLI vía Compose |
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
    │   ├── graph/                    # Wiring LangGraph + arun()
    │   ├── schemas/                  # Modelos Pydantic + GraphState
    │   ├── providers/                # Tavily, arXiv, Chroma
    │   ├── config.py                 # Settings (pydantic-settings)
    │   ├── llm.py                    # Factory multi-provider
    │   ├── api.py                    # FastAPI (jobs + static UI)
    │   ├── main.py                   # CLI
    │   └── logging_utils.py
    ├── frontend/                     # UI académica
    │   ├── index.html
    │   ├── styles.css
    │   └── app.js
    ├── tests/                        # unit + integration
    ├── data/
    │   └── kb_documents.json         # Seed KB
    ├── Dockerfile
    ├── docker-compose.yml
    ├── Makefile
    ├── pyproject.toml
    ├── requirements.txt
    └── .env.example
```

---

## Seguridad

- **Nunca** subas `.env` ni API keys. El `.gitignore` del paquete ya excluye `.env`, `.env.local` y `data/chroma/`.
- Las claves solo se leen por variables de entorno / `env_file` de Compose.
- La imagen Docker corre como usuario no-root `app`.
- `.dockerignore` excluye secretos, venvs y caches del build.
- La API local no implementa autenticación: pensada para uso en localhost.

Claves típicas: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `TAVILY_API_KEY`, `LANGCHAIN_API_KEY`.

---

## Por qué LangGraph

Se eligió **LangGraph** (frente a SDKs acoplados a un único vendor) porque:

- Es nativo en Python y encaja con tipado + `asyncio`
- Modela de forma explícita el grafo orchestrator → workers → synthesizer
- Permite estado tipado, degradación parcial y observabilidad vía LangSmith
- No acopla el orquestador a un único proveedor de modelo

La capa FastAPI/UI es un **adaptador**: no reemplaza el grafo; solo lo invoca (`build_graph().arun(query)`).

---

## Limitaciones actuales

- Un solo paquete en el monorepo (`research-synthesis-agent`)
- Los jobs de la API viven en memoria (no hay cola persistente tipo Redis)
- La UI aún no hace streaming fino por nodo del grafo (solo estados de job + hints)
- La KB de demo está orientada al tema de fusión nuclear
- Los informes son sintéticos: la calidad depende de las fuentes y del LLM configurado
- Sin autenticación en la API (uso local)

---

## Contribuir

Ideas bienvenidas: nuevos researchers, persistencia de jobs, streaming SSE de etapas, más idiomas en el informe, CI con GitHub Actions, o ampliar la KB.

1. Fork del repo  
2. Crea una rama (`git checkout -b feature/mi-mejora`)  
3. Asegura tests (`make docker-test` o `make test`) y lint (`make lint`)  
4. Abre un Pull Request  

---

## Disclaimer

Este proyecto es experimental / educativo. Los informes generados **no sustituyen** revisión humana, asesoría profesional ni fuentes primarias verificadas. Valida siempre las citas antes de usar el contenido en contextos críticos.

---

## Licencia

Este proyecto se publica bajo la [licencia MIT](LICENSE). Podés usarlo, copiarlo, modificarlo, distribuirlo y usarlo en proyectos comerciales, con la única condición de conservar el aviso de copyright y la licencia.

---

## Autor

Mantenido por [DataScienceWorld1805](https://github.com/DataScienceWorld1805) · repo: [Multiple_Agent_AI](https://github.com/DataScienceWorld1805/Multiple_Agent_AI)
