# Research Synthesis Agent

Paquete del sistema multi-agente de investigación y síntesis (LangGraph · orchestrator-worker).

**Documentación completa:** [README del repositorio](../README.md) (arquitectura, CLI, API, UI, export PDF/Markdown, KB, DuckDuckGo, resiliencia Gemini, Docker y contribución).

## Inicio rápido

```bash
cp .env.example .env          # GEMINI_API_KEY + LLM_MODEL=gemini-3.6-flash
pip install -r requirements.txt

# Interfaz web + API (export MD/PDF)
python -m src.api             # http://127.0.0.1:8000

# CLI
python -m src.main "tu pregunta" -o report.md

# Docker
make docker-build
make docker-serve             # UI en :8000
make docker-run QUERY='tu pregunta'
```

Defaults útiles del `.env.example`: `SEARCH_PROVIDER=duckduckgo`, KB seed vacía (`[]`).

Licencia: [MIT](../LICENSE).
