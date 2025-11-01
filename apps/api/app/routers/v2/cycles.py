from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from pydantic import BaseModel
from app.services.parse import read_df, norm_reason, col, to_dt, payment_str
import pandas as pd

router = APIRouter()

class CycleEntry(BaseModel):
    index: int
    start_row: int
    end_row: int
    start_at: str
    label: str  # "tarih • TYPE • [detay]"

class CyclesResponse(BaseModel):
    filename: str
    total_rows: int
    cycles: list[CycleEntry]

@router.post("", response_model=CyclesResponse)
async def list_cycles(file: UploadFile = File(...), member_id: str | None = Form(None)):
    df, _ = read_df(file)
    c_ts = col(df, "Date & Time", "Date", "timestamp", "time")
    c_mb = col(df, "Player ID", "member_id", "User ID", "Account ID")
    c_rs = col(df, "Reason", "Description", "Event")
    c_am = col(df, "Amount", "Base Amount", "Bet Amount", "Stake")
    c_pm = col(df, "Payment Method", "Method")
    c_dt = col(df, "Details", "Note")
    for name, c in [("Date & Time", c_ts), ("Player ID", c_mb), ("Reason", c_rs)]:
        if not c:
            raise HTTPException(status_code=422, detail=f"Eksik kolon: {name}")

    df[c_ts] = to_dt(df[c_ts])
    df["__r"] = df[c_rs].apply(norm_reason)
    df = df.sort_values(c_ts).reset_index(drop=True)
    if member_id:
        df = df[df[c_mb].astype(str) == str(member_id)].reset_index(drop=True)

    if c_am:
        df["_amt"] = pd.to_numeric(df[c_am], errors="coerce").fillna(0.0)
    else:
        df["_amt"] = 0.0

    # Start events: DEPOSIT, BONUS_GIVEN (includes FREE_SPIN_GIVEN), ADJUSTMENT>0
    start_mask = (df["__r"].isin(["DEPOSIT", "BONUS_GIVEN"])) | ((df["__r"] == "ADJUSTMENT") & (df["_amt"] > 0))
    start_idxs = df.index[start_mask].tolist()

    cycles: list[CycleEntry] = []
    if not start_idxs:
        cycles.append(CycleEntry(index=0, start_row=0, end_row=int(len(df)), start_at=str(df.iloc[0][c_ts]),
                                 label=f"{str(df.iloc[0][c_ts])} • (no start event)"))
        return CyclesResponse(filename=file.filename, total_rows=int(len(df)), cycles=cycles)

    for i, s in enumerate(start_idxs):
        e = start_idxs[i + 1] if i + 1 < len(start_idxs) else len(df)
        row = df.loc[s]
        rtype = row["__r"]
        if rtype == "DEPOSIT":
            detail = payment_str(row, c_pm, c_dt)
            label = f"{row[c_ts]} • DEPOSIT" + (f" • [{detail}]" if detail else "")
        elif rtype == "BONUS_GIVEN":
            det = (str(row[c_dt] or row[c_rs]) if c_dt else str(row[c_rs])) or "Bonus"
            label = f"{row[c_ts]} • BONUS • [{det}]"
        else:  # ADJUSTMENT +
            detail = payment_str(row, c_pm, c_dt)
            label = f"{row[c_ts]} • ADJUSTMENT • [{detail or 'manual top-up'}]"
        cycles.append(CycleEntry(index=i, start_row=int(s), end_row=int(e), start_at=str(row[c_ts]), label=label))

    return CyclesResponse(filename=file.filename, total_rows=int(len(df)), cycles=cycles)
