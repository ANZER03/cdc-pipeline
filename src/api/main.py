from fastapi import FastAPI


app = FastAPI(title="Nexus API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/docs-ready")
def docs_ready() -> dict[str, bool]:
    return {"docs": True}
