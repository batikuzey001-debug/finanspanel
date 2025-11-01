from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.services.parse import read_df, col

router = APIRouter()

class UploadSummaryV2(BaseModel):
    filename: str
    sheet_names: List[str]
    first_sheet: Optional[str]
    columns: List[str]
    row_count_exact: int

@router.post("", response_model=UploadSummaryV2)
async def upload_summary(file: UploadFile = File(...)):
    """
    v2 upload özet: v1 /uploads'in yerini alır.
    - sheet isimleri, ilk sheet
    - kolonlar
    - satır sayısı
    """
    try:
        df, sheets = read_df(file)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Dosya okunamadı: {e}")

    # Sheet ismi (CSV ise 'csv')
    first_sheet = sheets[0] if sheets else None
    columns = [str(c) for c in df.columns]
    return UploadSummaryV2(
        filename=file.filename,
        sheet_names=sheets or [],
        first_sheet=first_sheet,
        columns=columns,
        row_count_exact=int(len(df)),
    )
