# Research Synthesis Agent

Paquete del sistema multi-agente de investigación y síntesis (LangGraph · orchestrator-worker).

**Documentación completa:** [README del repositorio](../README.md) (arquitectura, CLI, API HTTP, UI web, KB interna, Docker, variables de entorno y contribución).

## Inicio rápido

```bash
cp .env.example .env          # añade tu API key de LLM
pip install -r requirements.txt

# Interfaz web + API
python -m src.api             # http://127.0.0.1:8000

# CLI
python -m src.main "tu pregunta" -o report.md

# Docker
make docker-build
make docker-run QUERY='¿Cuál es el estado actual de la fusión nuclear como fuente de energía comercial?'
make docker-serve             # UI en el puerto 8000
```

Licencia: [MIT](../LICENSE).
