from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from io import BytesIO

router = APIRouter()

class UploadSummary(BaseModel):
    filename: str
    sheet_names: list[str]
    first_sheet: str | None
    columns: list[str]
    row_count_sampled: int

@router.post("", response_model=UploadSummary)
async def upload_file(file: UploadFile = File(...)):
    name = (file.filename or "").lower()
    if not name.endswith((".csv", ".xlsx", ".xls", ".xlsm")):
        raise HTTPException(status_code=400, detail="Desteklenmeyen dosya türü (.csv/.xlsx/.xls/.xlsm)")

    content = await file.read()

    try:
        # Pandas/openpyxl'i fonksiyon içinde import ederek start-up'ta ağır yükten kaçınıyoruz
        import pandas as pd  # type: ignore

        if name.endswith((".xlsx", ".xls", ".xlsm")):
            xls = pd.ExcelFile(BytesIO(content), engine="openpyxl")
            sheet_names = xls.sheet_names
            first_sheet = sheet_names[0] if sheet_names else None
            if not first_sheet:
                raise ValueError("Çalışma sayfası bulunamadı")
            df = pd.read_excel(xls, sheet_name=first_sheet, nrows=5000)
        else:
            df = pd.read_csv(BytesIO(content))
            sheet_names = ["csv"]
            first_sheet = "csv"

        cols = [str(c) for c in df.columns]
        sampled = min(len(df), 5000)

        return {
            "filename": file.filename,
            "sheet_names": sheet_names,
            "first_sheet": first_sheet,
            "columns": cols,
            "row_count_sampled": sampled,
        }
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Dosya okunamadı: {e}")
