from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import uploads
import os

app = FastAPI(title="Finans Panel API", version="0.1.0")

# CORS
origins_env = os.getenv("API_CORS_ORIGINS")
origins = [o.strip() for o in origins_env.split(",")] if origins_env else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"ok": True, "service": "finanspanel-api"}

@app.get("/health")
async def health():
    # ← Buradaki satır önce eksik tırnak yüzünden patlıyordu
    return {"status": "ok", "service": "finanspanel-api", "version": "0.1.0"}

# Router en sonda; ağır importlar varsa bile app ayağa kalkar
app.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
