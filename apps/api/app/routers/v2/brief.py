from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from pydantic import BaseModel
from typing import Optional, List, Tuple, Dict
from app.services.parse import read_df, col, to_dt, norm_reason, payment_str
from app.services.matchers import build_key

router = APIRouter()

# ------------------ MODELLER ------------------

class Row1_LastOp(BaseModel):
    type: str                      # "DEPOSIT" | "BONUS" | "ADJUSTMENT"
    ts: str
    amount: float
    method: Optional[str] = None   # deposit/adjustment için L+M
    bonus_detail: Optional[str] = None
    bonus_kind: Optional[str] = None  # "trial" | "deposit" | "freespin" | "cashback" | "other"

class Row2_Wager(BaseModel):
    window_from: str
    window_to: Optional[str] = None
    wager_total: float
    wager_count: int

class OpenItem(BaseModel):
    id: Optional[str] = None
    placed_ts: Optional[str] = None
    amount: Optional[float] = None

class LateGapItem(BaseModel):
    id: Optional[str] = None
    placed_ts: Optional[str] = None
    settled_ts: Optional[str] = None
    gap_minutes: Optional[float] = None
    placed_amount: Optional[float] = None
    settled_amount: Optional[float] = None

class Row3_Open(BaseModel):
    open_total_amount: float
    open_count: int
    items: List[OpenItem]

class Row4_Late(BaseModel):
    late_gap_count: int
    late_gap_total_minutes: float
    items: List[LateGapItem]

class TopGame(BaseModel):
    game_name: str
    wager: float
    profit: float

class Row5_TopWager(BaseModel):
    items: List[TopGame]

class Row6_TopProfit(BaseModel):
    items: List[TopGame]

class BriefResponse(BaseModel):
    filename: str
    cycle_index_from: int
    cycle_index_to: int
    member_id: str
    row1_last_op: Row1_LastOp
    row2_wager: Row2_Wager
    row3_open: Row3_Open
    row4_late: Row4_Late
    row5_top_wager: Row5_TopWager
    row6_top_profit: Row6_TopProfit
    currency: Optional[str] = None


# ------------------ YARDIMCI ------------------

def _bounds_deposits(df, reason_col: str) -> List[Tuple[int, int]]:
    deps = df.index[df[reason_col] == "DEPOSIT"].tolist()
    if not deps:
        return [(0, len(df))]  # DEPOSIT yoksa tüm dosya tek cycle
    bounds: List[Tuple[int, int]] = []
    for i, s in enumerate(deps):
        e = deps[i + 1] if i + 1 < len(deps) else len(df)
        bounds.append((int(s), int(e)))
    return bounds

def _bonus_kind_from_text(txt: str) -> str:
    s = (txt or "").lower()
    if any(k in s for k in ["trial", "deneme"]): return "trial"
    if any(k in s for k in ["free", "freespin", "spin"]): return "freespin"
    if any(k in s for k in ["cashback", "kayıp", "kayip", "loss"]): return "cashback"
    if any(k in s for k in ["deposit", "yatırım", "yatirim"]): return "deposit"
    return "other"

def _key_for_row(df, idx, c_ref, c_cid) -> str:
    return build_key(df, idx, c_ref, c_cid)

def _fmt(ts) -> str:
    try:
        return str(ts)
    except Exception:
        return ""


# ------------------ ENDPOINT ------------------

@router.post("", response_model=BriefResponse)
async def brief(
    file: UploadFile = File(...),
    # yeni parametreler: cycle aralığı
    start_cycle_index: Optional[int] = Form(None),
    end_cycle_index:   Optional[int] = Form(None),
    # geriye uyumluluk için eski isim
    cycle_index:       Optional[int] = Form(None),
    member_id:         Optional[str] = Form(None),
    threshold_minutes: int = Form(5),
):
    """
    ÇEVRİM PANELİ BRIEF — 6 satır:
      1) Son işlem (DEPOSIT / BONUS / **pozitif** ADJUSTMENT) + detay
         (-/0 ADJUSTMENT son işlem olarak kabul edilmez)
      2) Bu işleme bağlı pencere wager toplamı
      3) Açık işlemler (placed var, settled yok)
      4) Geç sonuçlananlar (>5dk)
      5) En çok ÇEVRİM yapılan 3 oyun (Σ|PLACED|)
      6) En çok KÂR eden 3 oyun (ΣSETTLED + ΣPLACED)
    Aralık: [start_cycle_index .. end_cycle_index] tek pencere olarak birleştirilir.
    """
    import pandas as pd  # type: ignore
    import numpy as np   # type: ignore
    from collections import defaultdict, deque

    df, _ = read_df(file)

    # Kolonlar
    c_ts = col(df, "Date & Time", "Date", "timestamp", "time")
    c_mb = col(df, "Player ID", "member_id", "User ID", "Account ID")
    c_rs = col(df, "Reason", "Description", "Event")
    c_am = col(df, "Amount", "Base Amount", "Bet Amount", "Stake")
    c_ref = col(df, "Reference ID", "Ref ID", "Bet ID", "Ticket")
    c_cid = col(df, "BetCID", "Bet CID")
    c_pay = col(df, "Payment Method", "Method")
    c_det = col(df, "Details", "Note")
    c_game = col(df, "Game Name", "Game")
    c_curr = col(df, "Currency", "Base Currency", "System Currency")

    for name, c in [("Date & Time", c_ts), ("Player ID", c_mb), ("Reason", c_rs), ("Amount", c_am)]:
        if not c: raise HTTPException(status_code=422, detail=f"Eksik kolon: {name}")

    # Normalize
    df[c_ts] = to_dt(df[c_ts])
    df = df.sort_values(c_ts).reset_index(drop=True)
    df["__r"] = df[c_rs].apply(norm_reason)
    df["_amt"] = pd.to_numeric(df[c_am], errors="coerce").fillna(0.0)

    if member_id:
        df = df[df[c_mb].astype(str) == str(member_id)].reset_index(drop=True)
    if len(df) == 0:
        raise HTTPException(status_code=422, detail="Filtre sonrası satır yok.")

    # --- cycle aralığını belirle ---
    bounds = _bounds_deposits(df, "__r")  # her biri (start,end)
    total_cycles = len(bounds)

    if start_cycle_index is None and cycle_index is not None:
        start_cycle_index = cycle_index
    if start_cycle_index is None:
        start_cycle_index = total_cycles - 1
    if end_cycle_index is None:
        end_cycle_index = start_cycle_index

    if start_cycle_index < 0 or start_cycle_index >= total_cycles:
        raise HTTPException(status_code=400, detail=f"Geçersiz start_cycle_index: {start_cycle_index}")
    if end_cycle_index < start_cycle_index or end_cycle_index >= total_cycles:
        raise HTTPException(status_code=400, detail=f"Geçersiz end_cycle_index: {end_cycle_index}")

    s_idx = bounds[start_cycle_index][0]
    e_idx = bounds[end_cycle_index][1]
    cyc = df.iloc[s_idx:e_idx].copy()
    member_val = str(df.iloc[s_idx][c_mb])

    # ---- 1) Son işlem (NEGATİF ADJUSTMENT HARİÇ) ----
    fin_any_mask   = cyc["__r"].isin(["DEPOSIT", "BONUS_GIVEN", "ADJUSTMENT"])  # pencere bitişi için
    fin_valid_mask = (cyc["__r"].isin(["DEPOSIT", "BONUS_GIVEN"])) | ((cyc["__r"] == "ADJUSTMENT") & (cyc["_amt"] > 0))

    if fin_valid_mask.any():
        last_fin_idx = cyc.index[fin_valid_mask][-1]
        row = cyc.loc[last_fin_idx]
        rtype = "BONUS" if row["__r"] == "BONUS_GIVEN" else row["__r"]
        last_op = Row1_LastOp(
            type=rtype,
            ts=_fmt(row[c_ts]),
            amount=round(float(row["_amt"]), 2),
            method=payment_sql := (payment_str(row, c_pay, c_det) if rtype in ("DEPOSIT", "ADJUSTMENT") else None),
            bonus_detail=((str(row[c_det] or row[c_rs]) if c_det else str(row[c_rs])) if rtype == "BONUS" else None),
            bonus_kind=(_bonus_kind_from_text(str(row[c_det] or row[c_rs])) if rtype == "BONUS" else None),
        )
        window_from_ts = row[c_ts]
        start_idx_for_next = last_fin_idx
    else:
        # hiç geçerli finansal yok → aralığın başını esas al
        first_ts = cyc.iloc[0][c_ts]
        last_op = Row1_LastOp(type="DEPOSIT", ts=_fmt(first_ts), amount=0.0, method=None)
        window_from_ts = first_ts
        start_idx_for_next = cyc.index[0]

    # Pencere bitişi: start_idx_for_next'ten sonra gelen İLK finansal (pozitif/negatif ayrımı yok); yoksa aralığın sonu
    if fin_any_mask.any():
        next_any = cyc.index[(cyc.index > start_idx_for_next) & fin_any_mask]
        window_to_ts = cyc.loc[next_any[0], c_ts] if len(next_any) else cyc.iloc[-1][c_ts]
    else:
        window_to_ts = cyc.iloc[-1][c_ts]

    # ---- 2) Penceredeki wager toplamı ----
    in_window = (cyc[c_ts] >= window_from_ts) & (cyc[c_ts] <= (window_to_ts if window_to_ts is not None else cyc.iloc[-1][c_ts]))
    placed_win = (cyc["__r"] == "BET_PLACED") & in_window
    wager_total = float(cyc.loc[placed_win, "_amt"].abs().sum())
    wager_count = int(placed_win.sum())
    row2 = Row2_Wager(
        window_from=_fmt(window_from_ts),
        window_to=_fmt(window_to_ts) if window_to_ts is not None else None,
        wager_total=round(wager_total, 2),
        wager_count=wager_count,
    )

    # ---- 3) Açık işlemler ----
    placed_ix  = cyc.index[cyc["__r"] == "BET_PLACED"].tolist()
    settled_ix = cyc.index[cyc["__r"] == "BET_SETTLED"].tolist()
    pmap: Dict[str, deque] = defaultdict(deque)
    smap: Dict[str, deque] = defaultdict(deque)
    for i in placed_ix:  pmap[_key_for_row(cyc, i, c_ref, c_cid)].append(i)
    for i in settled_ix: smap[_key_for_row(cyc, i, c_ref, c_cid)].append(i)
    # eşleşenleri düş
    for key in set(pmap) | set(smap):
        ps, ss = pmap.get(key, deque()), smap.get(key, deque())
        while ps and ss:
            ps.popleft(); ss.popleft()

    open_items: List[OpenItem] = []
    open_total = 0.0
    for _, q in pmap.items():
        for idx_p in q:
            amt = float(cyc.loc[idx_p, "_amt"])
            open_total += abs(amt)
            open_items.append(OpenItem(
                id=(str(cyc.loc[idx_p, c_ref]) if c_ref else None),
                placed_ts=_fmt(cyc.loc[idx_p, c_ts]),
                amount=round(abs(amt), 2),
            ))
    row3 = Row3_Open(open_total_amount=round(open_total, 2), open_count=len(open_items), items=open_items[:50])

    # ---- 4) Geç sonuçlanan (>5dk) ----
    pmap2: Dict[str, deque] = defaultdict(deque)
    smap2: Dict[str, deque] = defaultdict(deque)
    for i in placed_ix:  pmap2[_key_for_row(cyc, i, c_ref, c_cid)].append(i)
    for i in settled_ix: smap2[_key_for_row(cyc, i, c_ref, c_cid)].append(i)

    late_items: List[LateGapItem] = []
    late_total = 0.0
    late_count = 0
    for key in set(pmap2) | set(smap2):
        ps, ss = pmap2.get(key, deque()), smap2.get(key, deque())
        while ps and ss:
            p_i, s_i = ps.popleft(), ss.popleft()
            p_ts, s_ts = cyc.loc[p_i, c_ts], cyc.loc[s_i, c_ts]
            if p_ts is not None and s_ts is not None:
                gap_min = (s_ts - p_ts).total_seconds() / 60.0
                if gap_min > float(threshold_minutes):
                    late_count += 1
                    late_total += gap_min
                    late_items.append(LateGapItem(
                        id=(str(cyc.loc[p_i, c_ref]) if c_ref else None),
                        placed_ts=_fmt(p_ts),
                        settled_ts=_fmt(s_ts),
                        gap_minutes=round(gap_min, 2),
                        placed_amount=round(float(cyc.loc[p_i, "_amt"]), 2),
                        settled_amount=round(float(cyc.loc[s_i, "_amt"]), 2),
                    ))
    row4 = Row4_Late(late_gap_count=late_count, late_gap_total_minutes=round(late_total, 2), items=late_items[:50])

    # ---- 5) En çok ÇEVRİM yapılan 3 oyun (Σ|PLACED|) ----
    top_wager_items: List[TopGame] = []
    if c_game:
        placed_by_game = cyc.loc[cyc["__r"] == "BET_PLACED"].groupby(c_game)["_amt"].apply(lambda s: float(s.abs().sum()))
        profit_by_game = cyc.groupby(c_game)["_amt"].apply(
            lambda s: float(
                s[(cyc.loc[s.index, "__r"] == "BET_PLACED")].sum() +
                s[(cyc.loc[s.index, "__r"] == "BET_SETTLED")].sum()
            )
        )
        if not placed_by_game.empty:
            order_wager = placed_by_game.sort_values(ascending=False).head(3).index
            for g in order_wager:
                top_wager_items.append(TopGame(
                    game_name=str(g),
                    wager=round(float(placed_by_game.get(g, 0.0)), 2),
                    profit=round(float(profit_by_game.get(g, 0.0)), 2),
                ))
    row5 = Row5_TopWager(items=top_wager_items)

    # ---- 6) En çok KÂR eden 3 oyun (ΣSETTLED + ΣPLACED) ----
    top_profit_items: List[TopGame] = []
    if c_game:
        profit_by_game = cyc.groupby(c_game)["_amt"].apply(
            lambda s: float(
                s[(cyc.loc[s.index, "__r"] == "BET_PLACED")].sum() +
                s[(cyc.loc[s.index, "__r"] == "BET_SETTLED")].sum()
            )
        )
        profit_by_game = profit_by_game[profit_by_game > 0].sort_values(ascending=False).head(3)
        for g, val in profit_by_game.items():
            wager_g = float(cyc.loc[(cyc[c_game] == g) & (cyc["__r"] == "BET_PLACED"), "_amt"].abs().sum())
            top_profit_items.append(TopGame(
                game_name=str(g),
                wager=round(wager_g, 2),
                profit=round(float(val), 2),
            ))
    row6 = Row6_TopProfit(items=top_profit_items)

    currency = (str(cyc[c_curr].iloc[0]) if c_curr and not cyc[c_curr].empty else None)

    return BriefResponse(
        filename=file.filename,
        cycle_index_from=int(start_cycle_index),
        cycle_index_to=int(end_cycle_index),
        member_id=member_val := str(df.iloc[s_idx][c_mb]),
        row1_last_op=last_op,
        row2_wager=row2,
        row3_open=row3,
        row4_late=row4,
        row5_top_wager=row5,
        row6_top_profit=row6,
        currency=currency
    )
