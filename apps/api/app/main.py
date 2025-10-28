from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import uploads
import os

app = FastAPI(title="Finans Panel API", version="0.1.0")

origins_env = os.getenv("API_CORS_ORIGINS")
origins = origins_env.split(",") if origins_env else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "finanspanel-api", "version": "0.1.0"}

app.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
