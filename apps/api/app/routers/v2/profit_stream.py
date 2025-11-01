from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from pydantic import BaseModel
from app.services.parse import read_df, norm_reason, col, to_dt, payment_str
from app.services.matchers import build_key
from app.services.profit import assign_source

router = APIRouter()

class ProfitRow(BaseModel):
    ts: str
    source: str                # MAIN | BONUS | ADJUSTMENT
    amount: float
    detail: str | None         # bonus adı/kodu veya ödeme yöntemi

class ProfitStreamResponse(BaseModel):
    filename: str
    cycle_index: int
    member_id: str
    rows: list[ProfitRow]

@router.post("", response_model=ProfitStreamResponse)
async def profit_stream(
    file: UploadFile = File(...),
    cycle_index: int | None = Form(None),
    member_id: str | None = Form(None),
):
    df, _ = read_df(file)
    c_ts = col(df,"Date & Time","Date","timestamp","time")
    c_mb = col(df,"Player ID","member_id","User ID","Account ID")
    c_rs = col(df,"Reason","Description","Event")
    c_am = col(df,"Amount","Base Amount","Bet Amount","Stake")
    c_ref = col(df,"Reference ID","Ref ID","Bet ID","Ticket")
    c_cid = col(df,"BetCID","Bet CID")
    c_pm = col(df,"Payment Method","Method")
    c_dt = col(df,"Details","Note")
    for name,c in [("Date & Time",c_ts),("Player ID",c_mb),("Reason",c_rs),("Amount",c_am)]:
        if not c: raise HTTPException(status_code=422, detail=f"Eksik kolon: {name}")

    df[c_ts] = to_dt(df[c_ts])
    df = df.sort_values(c_ts).reset_index(drop=True)
    df["__r"] = df[c_rs].apply(norm_reason)
    if member_id:
        df = df[df[c_mb].astype(str)==str(member_id)].reset_index(drop=True)

    # DEPOSIT bazlı cycle sınırları
    deps = df.index[df["__r"]=="DEPOSIT"].tolist()
    if not deps:
        raise HTTPException(status_code=422, detail="Bu dosyada DEPOSIT yok.")
    bounds = [(int(s), int(deps[i+1] if i+1 < len(deps) else len(df))) for i,s in enumerate(deps)]
    if cycle_index is None:
        cycle_index = len(bounds) - 1
    if cycle_index < 0 or cycle_index >= len(bounds):
        raise HTTPException(status_code=400, detail=f"Geçersiz cycle_index: {cycle_index}")

    s,e = bounds[cycle_index]
    cyc = df.iloc[s:e].copy()
    dep_row = df.iloc[s]
    member_val = str(dep_row[c_mb])

    # eşleştir: placed/settled anahtarları
    placed = cyc.index[cyc["__r"]=="BET_PLACED"].tolist()
    settled = cyc.index[cyc["__r"]=="BET_SETTLED"].tolist()
    # anahtar → kuyruk
    from collections import defaultdict, deque
    pmap: dict[str, deque] = defaultdict(deque)
    smap: dict[str, deque] = defaultdict(deque)
    for i in placed:  pmap[build_key(cyc, i, c_ref, c_cid)].append(i)
    for i in settled: smap[build_key(cyc, i, c_ref, c_cid)].append(i)

    rows: list[ProfitRow] = []
    # eşleşen SETTLED → source = placed'tan önceki finansal olay
    matched_s: set[int] = set()
    for key in set(pmap)|set(smap):
        ps, ss = pmap.get(key, deque()), smap.get(key, deque())
        while ps and ss:
            p_i, s_i = ps.popleft(), ss.popleft()
            matched_s.add(s_i)
            src, det = assign_source(cyc, p_i, c_pm, c_dt, c_rs)
            rows.append(ProfitRow(
                ts=str(cyc.loc[s_i, c_ts]),
                source=src, amount=float(cyc.loc[s_i, c_am]),
                detail=det
            ))
    # eşleşmeyen SETTLED → source = settled anından geriye bak
    for key, ss in smap.items():
        for s_i in ss:
            if s_i in matched_s: continue
            src, det = assign_source(cyc, s_i, c_pm, c_dt, c_rs, fallback=True)
            rows.append(ProfitRow(
                ts=str(cyc.loc[s_i, c_ts]),
                source=src, amount=float(cyc.loc[s_i, c_am]),
                detail=det
            ))

    rows.sort(key=lambda r: r.ts)
    return ProfitStreamResponse(filename=file.filename, cycle_index=cycle_index, member_id=member_val, rows=rows)
