from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from pydantic import BaseModel
from app.services.parse import read_df, norm_reason, col, to_dt, payment_str

router = APIRouter()

class CycleEntry(BaseModel):
    index: int
    start_row: int
    end_row: int
    start_at: str
    deposit_amount: float
    payment_method: str | None
    label: str  # "tarih • tutar ₺ • [yöntem]"

class CyclesResponse(BaseModel):
    filename: str
    total_rows: int
    cycles: list[CycleEntry]

@router.post("", response_model=CyclesResponse)
async def list_cycles(file: UploadFile = File(...), member_id: str | None = Form(None)):
    df, _ = read_df(file)
    c_ts = col(df,"Date & Time","Date","timestamp","time")
    c_mb = col(df,"Player ID","member_id","User ID","Account ID")
    c_rs = col(df,"Reason","Description","Event")
    c_am = col(df,"Amount","Base Amount","Bet Amount","Stake")
    c_pm = col(df,"Payment Method","Method")
    c_dt = col(df,"Details","Note")
    for name, c in [("Date & Time",c_ts),("Player ID",c_mb),("Reason",c_rs),("Amount",c_am)]:
        if not c: raise HTTPException(status_code=422, detail=f"Eksik kolon: {name}")

    df[c_ts] = to_dt(df[c_ts])
    df[c_am] = df[c_am].apply(lambda v: float(str(v).replace(",",".")) if str(v) else 0.0)
    df["__r"] = df[c_rs].apply(norm_reason)
    df = df.sort_values(c_ts).reset_index(drop=True)
    if member_id:
        df = df[df[c_mb].astype(str)==str(member_id)].reset_index(drop=True)

    deps = df.index[df["__r"]=="DEPOSIT"].tolist()
    if not deps:
        return CyclesResponse(filename=file.filename, total_rows=int(len(df)), cycles=[])

    cycles: list[CycleEntry] = []
    for i, s in enumerate(deps):
        e = deps[i+1] if i+1 < len(deps) else len(df)
        row = df.iloc[s]
        start_at = str(row[c_ts])
        amount = float(row[c_am])
        pay = payment_str(row, c_pm, c_dt)
        label = f"{start_at} • {amount:,.2f} ₺" + (f" • [{pay}]" if pay else "")
        cycles.append(CycleEntry(
            index=i, start_row=int(s), end_row=int(e),
            start_at=start_at, deposit_amount=round(amount,2),
            payment_method=pay, label=label
        ))
    return CyclesResponse(filename=file.filename, total_rows=int(len(df)), cycles=cycles)
