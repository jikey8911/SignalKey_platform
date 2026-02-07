from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Crear app sin lifespan
app = FastAPI(title="Crypto Trading Signal API (Minimal)")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health endpoint simple
@app.get("/health")
async def health():
    return {"status": "ok", "message": "API is running"}

@app.get("/")
async def root():
    return {"message": "SignalKey API - Minimal Mode"}

logger.info("=== Minimal API started successfully ===")
