from fastapi import APIRouter
from .cycles import router as cycles_router
from .profit_stream import router as profit_router
from .brief import router as brief_router
from .upload_summary import router as upload_summary_router

router = APIRouter()
router.include_router(cycles_router,        prefix="/cycles",         tags=["v2-cycles"])
router.include_router(profit_router,        prefix="/profit-stream",  tags=["v2-profit"])
router.include_router(brief_router,         prefix="/brief",          tags=["v2-brief"])
router.include_router(upload_summary_router,prefix="/upload-summary", tags=["v2-upload"])
