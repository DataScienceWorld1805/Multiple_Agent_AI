# Multiple Agent AI — Research Synthesis Agent

Sistema multi-agente de **investigación y síntesis** con patrón *orchestrator-worker*. Dada una pregunta, descompone el tema, investiga en paralelo (web, papers académicos y base de conocimiento interna) y genera un **informe Markdown con citas ancladas** a hallazgos reales.

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
- **Docker-first**: build multi-stage, usuario no-root, Compose listo para usar

---

## Arquitectura

```
                    ┌─────────────────────┐
                    │    Orchestrator     │
                    │  (plan + retries)   │
                    └──────────┬──────────┘
                               │ fan-out
           ┌───────────────────┼───────────────────┐
           ▼                   ▼                   ▼
   WebResearcher      PapersResearcher    InternalKBResearcher
     (Tavily)             (arXiv)            (Chroma)
           │                   │                   │
           └───────────────────┼───────────────────┘
                               │ fan-in
                               ▼
                       ┌───────────────┐
                       │  Synthesizer  │
                       │  → Markdown   │
                       └───────────────┘
```

| Agente | Rol |
|--------|-----|
| **Orchestrator** | Descompone la query en 2–5 subpreguntas y asigna fuentes (`web` / `paper` / `internal_kb`) |
| **WebResearcher** | Busca evidencia en la web vía Tavily (o fake) |
| **PapersResearcher** | Recupera papers de arXiv (sin API key) |
| **InternalKBResearcher** | Consulta una KB vectorial local (Chroma + seed JSON) |
| **Synthesizer** | Integra hallazgos, detecta contradicciones y emite el informe citado |

---

## Stack

| Capa | Tecnología |
|------|------------|
| Lenguaje | Python ≥ 3.11 |
| Orquestación | LangGraph + LangChain Core |
| Modelos | Pydantic v2 |
| LLMs | OpenAI · Anthropic · Gemini · fake |
| Web | Tavily (`httpx` + retries) |
| Papers | arXiv (paquete `arxiv`) |
| Vector store | ChromaDB embebido |
| Observabilidad | Logs JSON · LangSmith (opcional) |
| Runtime | Docker Compose · Makefile |

---

## Inicio rápido (Docker)

Requisitos: **Docker** + **Docker Compose**.

```bash
git clone https://github.com/DataScienceWorld1805/Multiple_Agent_AI.git
cd Multiple_Agent_AI/research-synthesis-agent

cp .env.example .env
# Edita .env y añade al menos la API key del LLM que uses

make docker-build
make docker-run QUERY='¿Cuál es el estado actual de la fusión nuclear como fuente de energía comercial?'
```

El CLI imprime el informe Markdown por stdout. Para guardarlo en un archivo:

```bash
docker compose run --rm app python -m src.main "tu pregunta" -o /app/data/report.md
```

### Interfaz web (local)

```bash
cd research-synthesis-agent
pip install -r requirements.txt
python -m src.api
```

Abre [http://127.0.0.1:8000](http://127.0.0.1:8000): escribe una pregunta, lanza la investigación y consulta el informe (resumen, secciones, citas, plan y workers). Con Docker: `make docker-serve`.

### Modo demo / offline (sin APIs)

En `.env`:

```env
LLM_PROVIDER=fake
SEARCH_PROVIDER=fake
PAPERS_PROVIDER=fake
```

Luego:

```bash
make docker-run QUERY='What is the current status of commercial nuclear fusion?'
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
| `CHROMA_PERSIST_DIR` | `data/chroma` | Persistencia del índice |
| `KB_SEED_PATH` | `data/kb_documents.json` | Seed de la KB interna |
| `LOG_LEVEL` | `INFO` | Nivel de logging |
| `LANGSMITH_TRACING` | `false` | Activar tracing LangSmith |

> **Nota:** `.env.example` usa `LLM_PROVIDER=gemini` y `SEARCH_PROVIDER=fake` para un arranque económico. Los defaults del código (`config.py`) aplican si no defines `.env`.

### LangSmith (opcional)

```env
LANGSMITH_TRACING=true
LANGCHAIN_API_KEY=...
LANGCHAIN_PROJECT=research-synthesis-agent
```

---

## Ejecución local (sin Docker)

```bash
cd research-synthesis-agent
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux / macOS
# source .venv/bin/activate

pip install -r requirements.txt
# o: pip install -e ".[dev]"

cp .env.example .env
python -m src.main "Estado de la fusión nuclear comercial" -o report.md
```

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

---

## Base de conocimiento interna

La KB de demo vive en [`research-synthesis-agent/data/kb_documents.json`](research-synthesis-agent/data/kb_documents.json) (briefs sobre fusión nuclear). Formato:

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

Puedes ampliar o reemplazar ese JSON y apuntar `KB_SEED_PATH` a tu propio corpus. Chroma persiste el índice en `data/chroma/` (ignorado por git).

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
| `docker-build` | Construye la imagen multi-stage |
| `docker-run` | Ejecuta el agente vía Compose (`QUERY=...`) |
| `docker-test` | `pytest` en contenedor con providers `fake` |
| `run` | Corre el CLI en el host |
| `test` | Suite de tests local |
| `lint` / `format` | Ruff + Black |

---

## Estructura del repositorio

```text
Multiple_Agent_AI/
├── README.md                      # Esta documentación
└── research-synthesis-agent/
    ├── src/
    │   ├── agents/                # Orchestrator, researchers, synthesizer
    │   │   └── researchers/       # web · papers · internal_kb
    │   ├── graph/                 # Wiring LangGraph
    │   ├── schemas/               # Modelos Pydantic + GraphState
    │   ├── providers/             # Tavily, arXiv, Chroma
    │   ├── config.py              # Settings (pydantic-settings)
    │   ├── llm.py                 # Factory multi-provider
    │   └── main.py                # CLI
    ├── tests/                     # unit + integration
    ├── data/
    │   └── kb_documents.json      # Seed KB
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

Claves típicas a configurar (según providers): `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `TAVILY_API_KEY`, `LANGCHAIN_API_KEY`.

---

## Por qué LangGraph

Se eligió **LangGraph** (frente a SDKs acoplados a un único vendor) porque:

- Es nativo en Python y encaja con tipado + `asyncio`
- Modela de forma explícita el grafo orchestrator → workers → synthesizer
- Permite estado tipado, degradación parcial y observabilidad vía LangSmith
- No acopla el orquestador a un único proveedor de modelo

---

## Limitaciones actuales

- CLI-only (no hay API HTTP todavía)
- Un solo paquete en el monorepo (`research-synthesis-agent`)
- La KB de demo está orientada al tema de fusión nuclear
- Los informes son sintéticos: la calidad depende de las fuentes y del LLM configurado

---

## Contribuir

Ideas bienvenidas: nuevos researchers, API REST, más idiomas en el informe, CI con GitHub Actions, o ampliar la KB.

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
