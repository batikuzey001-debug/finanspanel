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
    label: str  # "tarih • tutar ₺ • [yöntem]" veya "tarih • BONUS • [detay]"

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
    for name, c in [("Date & Time",c_ts),("Player ID",c_mb),("Reason",c_rs)]:
        if not c: raise HTTPException(status_code=422, detail=f"Eksik kolon: {name}")

    df[c_ts] = to_dt(df[c_ts])
    df["__r"] = df[c_rs].apply(norm_reason)
    df = df.sort_values(c_ts).reset_index(drop=True)
    if member_id:
        df = df[df[c_mb].astype(str)==str(member_id)].reset_index(drop=True)

    cycles: list[CycleEntry] = []
    dep_idx = df.index[df["__r"]=="DEPOSIT"].tolist()

    if dep_idx:
        # klasik: DEPOSIT → next DEPOSIT
        if c_am:
            import pandas as pd  # type: ignore
            df[c_am] = pd.to_numeric(df[c_am], errors="coerce").fillna(0.0)
        for i, s in enumerate(dep_idx):
            e = dep_idx[i+1] if i+1 < len(dep_idx) else len(df)
            row = df.loc[s]
            start_at = str(row[c_ts])
            amount = float(row[c_am]) if c_am else 0.0
            pay = payment_str(row, c_pm, c_dt)
            label = f"{start_at} • {amount:,.2f} ₺" + (f" • [{pay}]" if pay else "")
            cycles.append(CycleEntry(
                index=i, start_row=int(s), end_row=int(e),
                start_at=start_at, deposit_amount=round(amount,2),
                payment_method=pay, label=label
            ))
    else:
        # 🔁 DEPOSIT yok — bonus/adjustment tabanlı tek cycle (0 → son)
        first_fin = df.index[df["__r"].isin(["BONUS_GIVEN","ADJUSTMENT"])]
        if len(first_fin):
            i0 = int(first_fin[0])
            r0 = df.loc[i0]
            start_at = str(r0[c_ts])
            tag = "BONUS" if r0["__r"]=="BONUS_GIVEN" else "ADJUSTMENT"
            det = (str(r0[c_dt] or r0[c_rs]) if c_dt else str(r0[c_rs])) if tag=="BONUS" else payment_str(r0, c_pm, c_dt)
            label = f"{start_at} • {tag}" + (f" • [{det}]" if det else "")
        else:
            # hiç finansal yoksa yine tek cycle ama nötr etiket
            i0, start_at, label = 0, str(df.iloc[0][c_ts]), f"{str(df.iloc[0][c_ts])} • (no deposit/bonus)"
        cycles.append(CycleEntry(
            index=0, start_row=0, end_row=int(len(df)),
            start_at=start_at, deposit_amount=0.0,
            payment_method=None, label=label
        ))

    return CyclesResponse(filename=file.filename, total_rows=int(len(df)), cycles=cycles)
