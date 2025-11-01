from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from pydantic import BaseModel
from io import BytesIO
from typing import Optional, List, Dict, Tuple

router = APIRouter()

# ========== MODELLER ==========

class UploadSummary(BaseModel):
    filename: str
    sheet_names: List[str]
    first_sheet: Optional[str]
    columns: List[str]
    row_count_sampled: int
    row_count_exact: Optional[int] = None

class CycleEntry(BaseModel):
    index: int
    start_row: int
    end_row: int
    start_at: str
    deposit_amount: float
    payment_method: Optional[str] = None
    label: str

class CyclesResponse(BaseModel):
    filename: str
    total_rows: int
    cycles: List[CycleEntry]

class ProfitRow(BaseModel):
    ts: str
    source: str               # MAIN | BONUS | ADJUSTMENT
    amount: float
    detail: Optional[str] = None  # bonus adı/kodu veya ödeme yöntemi

class ProfitStreamResponse(BaseModel):
    filename: str
    cycle_index: int
    member_id: str
    rows: List[ProfitRow]

# ========== YARDIMCI ==========

def _read_dataframe_sync(file: UploadFile):
    try:
        import pandas as pd  # type: ignore
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pandas yüklenemedi: {e}")
    name = (file.filename or "").lower()
    content = file.file.read()
    try:
        if name.endswith((".xlsx", ".xls", ".xlsm")):
            xls = pd.ExcelFile(BytesIO(content), engine="openpyxl")
            sh = xls.sheet_names[0] if xls.sheet_names else None
            df = pd.read_excel(xls, sheet_name=sh) if sh else None
            if df is None: raise ValueError("Çalışma sayfası bulunamadı")
            sheets = xls.sheet_names
            first = sh
        elif name.endswith(".csv"):
            import pandas as pd
            df = pd.read_csv(BytesIO(content))
            sheets, first = ["csv"], "csv"
        else:
            raise HTTPException(status_code=400, detail="Desteklenmeyen dosya")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Dosya okunamadı: {e}")
    df.columns = [str(c).strip() for c in df.columns]
    return df, sheets, first

def _col(df, *cands: str) -> Optional[str]:
    low = {c.lower(): c for c in df.columns}
    for cand in cands:
        if cand.lower() in low: return low[cand.lower()]
    for c in df.columns:
        for cand in cands:
            if c.lower().replace(" ","")==cand.lower().replace(" ",""): return c
    return None

def _to_dt(series):
    import pandas as pd  # type: ignore
    return pd.to_datetime(series, errors="coerce", dayfirst=True)

def _norm_reason(v: object) -> str:
    s = str(v or "").strip().lower()
    if s in {"bet_placed","bet placed"} or "placed" in s or "stake" in s: return "BET_PLACED"
    if s in {"bet_settled","bet settled"} or "settled" in s or "payout" in s: return "BET_SETTLED"
    if s in {"deposit","yatırım","yatirim"}: return "DEPOSIT"
    if s in {"bonus_given","bonus given"} or ("bonus" in s and "achiev" not in s): return "BONUS_GIVEN"
    if s in {"casino_bonus_achieved","casino bonus achieved"} or ("bonus" in s and "achiev" in s): return "BONUS_ACHIEVED"
    if "withdrawal_decline" in s: return "WITHDRAWAL_DECLINE"
    if "withdrawal" in s: return "WITHDRAWAL"
    if "adjust" in s: return "ADJUSTMENT"
    return s.upper()

def _payment_str(row, col_payment: Optional[str], col_details: Optional[str]) -> Optional[str]:
    pm = str(row[col_payment]).strip() if col_payment and row.get(col_payment) is not None else ""
    dt = str(row[col_details]).strip() if col_details and row.get(col_details) is not None else ""
    s = " / ".join([x for x in [pm, dt] if x])
    return s or None

def _fmt(ts) -> str:
    try: return str(ts)
    except: return ""

# ========== ENDPOINTLER ==========

@router.post("", response_model=UploadSummary)
async def upload_file(file: UploadFile = File(...)):
    df, sheets, first = _read_dataframe_sync(file)
    return UploadSummary(
        filename=file.filename, sheet_names=sheets, first_sheet=first,
        columns=[str(c) for c in df.columns],
        row_count_sampled=min(len(df), 5000), row_count_exact=int(len(df))
    )

@router.post("/cycles", response_model=CyclesResponse)
async def list_cycles(file: UploadFile = File(...), member_id: Optional[str] = Form(None)):
    import pandas as pd  # type: ignore
    df, _, _ = _read_dataframe_sync(file)

    col_ts = _col(df,"Date & Time","Date","timestamp","time")
    col_member = _col(df,"Player ID","member_id","User ID","Account ID")
    col_reason = _col(df,"Reason","Description","Event")
    col_amount = _col(df,"Amount","Base Amount","Bet Amount","Stake")
    col_payment = _col(df,"Payment Method","Method")
    col_details = _col(df,"Details","Note")
    for name, col in [("Date & Time",col_ts),("Player ID",col_member),("Reason",col_reason),("Amount",col_amount)]:
        if not col: raise HTTPException(status_code=422, detail=f"Eksik kolon: {name}")

    df[col_ts] = _to_dt(df[col_ts])
    import pandas as pd
    df[col_amount] = pd.to_numeric(df[col_amount], errors="coerce").fillna(0.0)
    df["__reason"] = df[col_reason].apply(_norm_reason)
    df = df.sort_values(col_ts).reset_index(drop=True)
    if member_id:
        df = df[df[col_member].astype(str)==str(member_id)].reset_index(drop=True)

    cycles: List[CycleEntry] = []
    dep_idx = df.index[df["__reason"]=="DEPOSIT"].tolist()
    if not dep_idx:
        return CyclesResponse(filename=file.filename,total_rows=int(len(df)),cycles=cycles)

    for i,s_idx in enumerate(dep_idx):
        e_idx = dep_idx[i+1] if i+1<len(dep_idx) else len(df)
        row = df.iloc[s_idx]
        label = f"{_fmt(row[col_ts])} • {row[col_amount]:,.2f} ₺"
        pay = _payment_str(row, col_payment, col_details)
        if pay: label += f" • [{pay}]"
        cycles.append(CycleEntry(
            index=i, start_row=int(s_idx), end_row=int(e_idx),
            start_at=_fmt(row[col_ts]), deposit_amount=float(row[col_amount]),
            payment_method=pay, label=label
        ))
    return CyclesResponse(filename=file.filename,total_rows=int(len(df)),cycles=cycles)

@router.post("/profit-stream", response_model=ProfitStreamResponse)
async def profit_stream(
    file: UploadFile = File(...),
    cycle_index: Optional[int] = Form(None),
    member_id: Optional[str] = Form(None),
):
    """
    Seçilen yatırım (Deposit → next Deposit) için KAZANÇ AKIŞI:
    - Satır = {Tarih, Kaynak (MAIN|BONUS|ADJUSTMENT), Miktar, Detay}
    - Miktar = BET_SETTLED Amount (pozitif/negatif olabilir; pozitif kazançtır)
    - Kaynak: ilgili placed varsa placed ZAMANINDAN ÖNCEKİ en yakın finansal olaya bak (DEPOSIT/BONUS_GIVEN/ADJUSTMENT),
              yoksa settled zamanından önceki olaya bak.
    - Detay: BONUS ise M (Details) adı/kodu; DEPOSIT/ADJUSTMENT ise Payment Method/Details birleştirmesi.
    """
    import pandas as pd  # type: ignore
    df, _, _ = _read_dataframe_sync(file)

    col_ts = _col(df,"Date & Time","Date","timestamp","time")
    col_member = _col(df,"Player ID","member_id","User ID","Account ID")
    col_reason = _col(df,"Reason","Description","Event")
    col_amount = _col(df,"Amount","Base Amount","Bet Amount","Stake")
    col_ref = _col(df,"Reference ID","Ref ID","Bet ID","Ticket")
    col_betcid = _col(df,"BetCID","Bet CID")
    col_payment = _col(df,"Payment Method","Method")
    col_details = _col(df,"Details","Note")
    for name,col in [("Date & Time",col_ts),("Player ID",col_member),("Reason",col_reason),("Amount",col_amount)]:
        if not col: raise HTTPException(status_code=422, detail=f"Eksik kolon: {name}")

    df[col_ts] = _to_dt(df[col_ts])
    df = df.sort_values(col_ts).reset_index(drop=True)
    df["__reason"] = df[col_reason].apply(_norm_reason)

    # Member filtre
    if member_id:
        df = df[df[col_member].astype(str)==str(member_id)].reset_index(drop=True)

    # Cycle sınırı (yalnız yatırımlar)
    dep_idx = df.index[df["__reason"]=="DEPOSIT"].tolist()
    if not dep_idx:
        raise HTTPException(status_code=422, detail="DEPOSIT yok.")
    bounds: List[Tuple[int,int]] = []
    for i,s in enumerate(dep_idx):
        e = dep_idx[i+1] if i+1<len(dep_idx) else len(df)
        bounds.append((int(s),int(e)))
    if cycle_index is None: cycle_index = len(bounds)-1
    if cycle_index<0 or cycle_index>=len(bounds): raise HTTPException(status_code=400, detail="Geçersiz cycle_index")
    s_idx,e_idx = bounds[cycle_index]
    cycle = df.iloc[s_idx:e_idx].copy()
    dep_row = df.iloc[s_idx]
    member_val = str(dep_row[col_member])

    # Anahtar oluşturucu (REF->BetCID->fallback)
    def key_of(i: int) -> str:
        vref = str(cycle.iloc[i][col_ref]).strip() if col_ref else ""
        if vref and vref.lower() not in ("nan","none"): return f"R:{vref}"
        vbc = str(cycle.iloc[i][col_betcid]).strip() if col_betcid else ""
        if vbc and vbc.lower() not in ("nan","none"): return f"C:{vbc}"
        return f"F:{i}"  # fallback

    # placed/settled indexleri anahtara map et
    from collections import defaultdict, deque
    placed_ix = cycle.index[cycle["__reason"]=="BET_PLACED"].tolist()
    settled_ix = cycle.index[cycle["__reason"]=="BET_SETTLED"].tolist()
    pmap: Dict[str,deque] = defaultdict(deque)
    smap: Dict[str,deque] = defaultdict(deque)
    for i in placed_ix: pmap[key_of(cycle.index.get_loc(i))].append(i)
    for i in settled_ix: smap[key_of(cycle.index.get_loc(i))].append(i)

    # finansal olaylara bakarak kaynak bulucu
    fin_mask = cycle["__reason"].isin(["DEPOSIT","BONUS_GIVEN","ADJUSTMENT"])
    fin_ix = cycle.index[fin_mask].tolist()

    def source_for(ts_index: int) -> Tuple[str, Optional[str]]:
        """ts_index'e kadar GERİYE bak; ilk finansal olayın türünü ve detayını döndür."""
        src, detail = "MAIN", None
        j = ts_index
        while j >= cycle.index[0]:
            r = cycle.loc[j,"__reason"]
            if r in ("DEPOSIT","BONUS_GIVEN","ADJUSTMENT"):
                if r=="DEPOSIT":
                    src = "MAIN"; detail = _payment_str(cycle.loc[j], col_payment, col_details)
                elif r=="BONUS_GIVEN":
                    src = "BONUS"; detail = str(cycle.loc[j, col_details] or cycle.loc[j, col_reason] or "Bonus")
                else:
                    src = "ADJUSTMENT"; detail = _payment_str(cycle.loc[j], col_payment, col_details)
                break
            j -= 1
        return src, (detail.strip() if isinstance(detail,str) else detail)

    # eşle: placed ↔ settled (order)
    pairs: List[Tuple[int,int,str]] = []  # (p_i, s_i, key)
    for key in set(list(pmap.keys())+list(smap.keys())):
        ps, ss = pmap.get(key,deque()), smap.get(key,deque())
        while ps and ss:
            pairs.append((ps.popleft(), ss.popleft(), key))

    # kazanç satırları = tüm SETTLED'lar (eşleşen varsa placed zamanına göre kaynak, yoksa settled zamanına göre)
    rows: List[ProfitRow] = []
    for key, s_list in smap.items():
        # eşleşenler
        matched_s = {s for _,s,k in pairs if k==key}
        for p_i, s_i, k in [t for t in pairs if t[2]==key]:
            src, det = source_for(p_i)  # placed'tan önceki finansal olay
            rows.append(ProfitRow(
                ts=_fmt(cycle.loc[s_i, _col(cycle,"Date & Time","Date","timestamp","time")]),
                source=src,
                amount=float(cycle.loc[s_i, col_amount]),
                detail=(det or None)
            ))
        # eşleşmeyen SETTLED (placed yok): yine de listele, kaynağı settled zamanına göre bul
        for s_i in s_list:
            if s_i in matched_s: continue
            src, det = source_for(s_i)
            rows.append(ProfitRow(
                ts=_fmt(cycle.loc[s_i, _col(cycle,"Date & Time","Date","timestamp","time")]),
                source=src,
                amount=float(cycle.loc[s_i, col_amount]),
                detail=(det or None)
            ))

    # tarihe göre sırala (yeni→eski)
    rows.sort(key=lambda r: r.ts)
    return ProfitStreamResponse(filename=file.filename, cycle_index=int(cycle_index), member_id=member_val, rows=rows)
