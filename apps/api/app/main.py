from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import uploads   # v1
from app.routers.v2 import router as v2_router
import os

app = FastAPI(title="Finans Panel API", version="0.2.0")

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
    return {"status":"ok","service":"finanspanel-api","version":"0.2.0"}

# v1
app.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
# v2 (YENİ)
app.include_router(v2_router, prefix="/v2", tags=["v2"])
