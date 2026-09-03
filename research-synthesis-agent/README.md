# Research Synthesis Agent

Paquete del sistema multi-agente de investigación y síntesis (LangGraph · orchestrator-worker).

**Toda la documentación está en el [README del repositorio](../README.md)** (instalación, Docker, variables de entorno, CLI, arquitectura y contribución).

## UI local

```bash
pip install -r requirements.txt
cp .env.example .env   # si aún no tienes .env
python -m src.api
```

Abre [http://127.0.0.1:8000](http://127.0.0.1:8000). La UI lanza jobs vía `POST /api/research` y hace polling hasta obtener el informe.

Licencia: [MIT](../LICENSE).

```bash
# Desde esta carpeta
cp .env.example .env
make docker-build
make docker-run QUERY='¿Cuál es el estado actual de la fusión nuclear como fuente de energía comercial?'
```
