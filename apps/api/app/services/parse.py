from fastapi import HTTPException, UploadFile
from io import BytesIO
from typing import Optional
import pandas as pd

def read_df(file: UploadFile) -> tuple[pd.DataFrame, list[str]]:
    name = (file.filename or "").lower()
    content = file.file.read()

    if name.endswith(".csv"):
        try:
            import pyarrow as pa  # noqa
            df = pd.read_csv(BytesIO(content), engine="pyarrow")
        except Exception:
            df = pd.read_csv(BytesIO(content))
        sheets = ["csv"]
    elif name.endswith((".xlsx", ".xls", ".xlsm")):
        try:
            xls = pd.ExcelFile(BytesIO(content), engine="openpyxl")
            sheet = xls.sheet_names[0] if xls.sheet_names else None
            if not sheet:
                raise ValueError("Sheet yok")
            df = pd.read_excel(xls, sheet_name=sheet)
            sheets = xls.sheet_names
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Excel okunamadı: {e}")
    else:
        raise HTTPException(status_code=400, detail="Desteklenmeyen dosya")

    df.columns = [str(c).strip() for c in df.columns]
    return df, sheets

def col(df, *cands: str) -> Optional[str]:
    low = {c.lower(): c for c in df.columns}
    for cand in cands:
        if cand.lower() in low:
            return low[cand.lower()]
    for c in df.columns:
        for cand in cands:
            if c.lower().replace(" ", "") == cand.lower().replace(" ", ""):
                return c
    return None

def to_dt(series):
    return pd.to_datetime(series, errors="coerce", dayfirst=True)

def norm_reason(v: object) -> str:
    s = str(v or "").strip().lower()

    # Standard bets
    if s in {"bet_placed", "bet placed"} or " bet_placed" in s or " placed" in s or "stake" in s or "wager" in s:
        return "BET_PLACED"
    if s in {"bet_settled", "bet settled"} or " settled" in s or "payout" in s or "result" in s:
        return "BET_SETTLED"

    # Free spins stream → normalize
    if "free_spins_bet" in s or "free spins bet" in s:
        return "BET_PLACED"
    if "free_spins_settled" in s or "free spins settled" in s or "free_spins_winnings" in s or "free spins winnings" in s:
        return "BET_SETTLED"
    if "free_spin_given" in s or "free spins given" in s or "free_spin start" in s:
        return "BONUS_GIVEN"

    # Money movements
    if s in {"deposit", "yatırım", "yatirim"}:
        return "DEPOSIT"
    if "bonus_given" in s or "bonus given" in s:
        return "BONUS_GIVEN"
    if "casino_bonus_achieved" in s or "bonus achieved" in s:
        return "BONUS_ACHIEVED"
    if "withdrawal_decline" in s:
        return "WITHDRAWAL_DECLINE"
    if "withdrawal" in s:
        return "WITHDRAWAL"
    if "adjust" in s:
        return "ADJUSTMENT"

    return s.upper()

def payment_str(row, c_payment: Optional[str], c_details: Optional[str]) -> Optional[str]:
    pm = str(row[c_payment]).strip() if c_payment and row.get(c_payment) is not None else ""
    dt = str(row[c_details]).strip() if c_details and row.get(c_details) is not None else ""
    s = " / ".join([x for x in [pm, dt] if x])
    return s or None
