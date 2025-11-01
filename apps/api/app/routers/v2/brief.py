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

class Row5_TopGames(BaseModel):
    items: List[TopGame]

class BriefResponse(BaseModel):
    filename: str
    cycle_index: int
    member_id: str
    row1_last_op: Row1_LastOp
    row2_wager: Row2_Wager
    row3_open: Row3_Open
    row4_late: Row4_Late
    row5_top_games: Row5_TopGames
    currency: Optional[str] = None


# ------------------ YARDIMCI ------------------

def _bounds_deposits(df, reason_col: str) -> List[Tuple[int, int]]:
    deps = df.index[df[reason_col] == "DEPOSIT"].tolist()
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
    cycle_index: Optional[int] = Form(None),
    member_id: Optional[str] = Form(None),
    threshold_minutes: int = Form(5),
):
    """
    ÇEVRİM PANELİ BRIEF — 5 satırlık özet:
      1) Son işlem (deposit/bonus/adjustment) + detay (bonus türü, yöntem)
      2) Bu işleme bağlı çevrim penceresi (son işlem ts → sonraki finansal olaya kadar) wager toplamı
      3) Açık işlemler (placed var, settled yok) — id, tarih, miktar
      4) Geç sonuçlanan işlemler (gap > 5dk) — id, tarihler, miktarlar
      5) En çok çevrim yapılan ilk 3 oyun (wager & profit)
    """
    import pandas as pd  # type: ignore
    import numpy as np   # type: ignore

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
    # Member filter
    if member_id:
        df = df[df[c_mb].astype(str) == str(member_id)].reset_index(drop=True)
    if len(df) == 0:
        raise HTTPException(status_code=422, detail="Filtre sonrası satır yok.")

    # Cycle: yalnız yatırımlar
    bounds = _bounds_deposits(df, "__r")
    if not bounds:
        raise HTTPException(status_code=422, detail="Bu dosyada DEPOSIT yok.")
    if cycle_index is None:
        cycle_index = len(bounds) - 1
    if not (0 <= cycle_index < len(bounds)):
        raise HTTPException(status_code=400, detail=f"Geçersiz cycle_index: {cycle_index}")
    s_idx, e_idx = bounds[cycle_index]
    cyc = df.iloc[s_idx:e_idx].copy()

    # ---- 1) Son işlem (finansal event) ----
    fin_mask = cyc["__r"].isin(["DEPOSIT", "BONUS_GIVEN", "ADJUSTMENT"])
    if not fin_mask.any():
        # cycle'da finansal yoksa, önceki satırı referans almayalım; minimal bilgi
        last_op = Row1_LastOp(type="DEPOSIT", ts=_fmt(cyc.iloc[0][c_ts]), amount=0.0)
        window_from_ts = cyc.iloc[0][c_ts]
        window_to_ts = cyc.iloc[-1][c_ts] if len(cyc) else None
    else:
        last_fin_idx = cyc.index[fin_mask][-1]  # en son finansal
        row = cyc.loc[last_fin_idx]
        rtype = row["__r"]
        amt = float(pd.to_numeric(row[c_am], errors="coerce") if c_am else 0.0)
        ts = row[c_ts]
        method = payment_str(row, c_pay, c_det) if rtype in ("DEPOSIT", "ADJUSTMENT") else None
        bonus_detail = (str(row[c_det] or row[c_rs]) if c_det else str(row[c_rs])) if rtype == "BONUS_GIVEN" else None
        bonus_kind = _bonus_kind_from_text(bonus_detail or "") if rtype == "BONUS_GIVEN" else None

        last_op = Row1_LastOp(
            type="BONUS" if rtype == "BONUS_GIVEN" else rtype,  # BONUS_GIVEN -> BONUS
            ts=_fmt(ts),
            amount=round(amt, 2),
            method=method,
            bonus_detail=(bonus_detail.strip() if isinstance(bonus_detail, str) else None),
            bonus_kind=bonus_kind,
        )

        # Pencere: bu finansal ts → sonraki finansal ts (cycle sonuna kadar)
        next_fin = cyc.index[(cyc.index > last_fin_idx) & fin_mask]
        window_from_ts = ts
        window_to_ts = cyc.loc[next_fin[0], c_ts] if len(next_fin) else (cyc.iloc[-1][c_ts] if len(cyc) else None)

    # ---- 2) Bu pencere için wager toplamı ----
    in_window = (cyc[c_ts] >= window_from_ts) & (cyc[c_ts] <= (window_to_ts if window_to_ts is not None else cyc.iloc[-1][c_ts]))
    placed_win = (cyc["__r"] == "BET_PLACED") & in_window
    wager_total = float(pd.to_numeric(cyc.loc[placed_win, c_am], errors="coerce").abs().sum()) if c_am else 0.0
    wager_count = int(placed_win.sum())
    row2 = Row2_Wager(
        window_from=_fmt(window_from_ts),
        window_to=_fmt(window_to_ts) if window_to_ts is not None else None,
        wager_total=round(wager_total, 2),
        wager_count=wager_count,
    )

    # ---- 3) Açık işlemler (placed var, settled yok) ----
    from collections import defaultdict, deque
    placed_ix = cyc.index[cyc["__r"] == "BET_PLACED"].tolist()
    settled_ix = cyc.index[cyc["__r"] == "BET_SETTLED"].tolist()
    pmap: Dict[str, deque] = defaultdict(deque)
    smap: Dict[str, deque] = defaultdict(deque)
    for i in placed_ix:  pmap[_key_for_row(cyc, i, c_ref, c_cid)].append(i)
    for i in settled_ix: smap[_key_for_row(cyc, i, c_ref, c_cid)].append(i)

    # pair by order
    for key in list(set(pmap.keys()) | set(smap.keys())):
        ps, ss = pmap.get(key, deque()), smap.get(key, deque())
        while ps and ss:
            ps.popleft(); ss.popleft()   # eşleşenleri çıkar

    open_items: List[OpenItem] = []
    open_total = 0.0
    for key, q in pmap.items():
        for idx_p in q:
            amt = float(pd.to_numeric(cyc.loc[idx_p, c_am], errors="coerce") or 0.0)
            open_total += abs(amt)
            open_items.append(OpenItem(
                id=(str(cyc.loc[idx_p, c_ref]) if c_ref else None),
                placed_ts=_fmt(cyc.loc[idx_p, c_ts]),
                amount=round(abs(amt), 2),
            ))
    row3 = Row3_Open(open_total_amount=round(open_total, 2), open_count=len(open_items), items=open_items[:50])

    # ---- 4) Geç sonuçlanan (gap > 5dk) — eşleşenlerde ----
    # yeniden pair edelim
    pmap2: Dict[str, deque] = defaultdict(deque)
    smap2: Dict[str, deque] = defaultdict(deque)
    for i in placed_ix:  pmap2[_key_for_row(cyc, i, c_ref, c_cid)].append(i)
    for i in settled_ix: smap2[_key_for_row(cyc, i, c_ref, c_cid)].append(i)

    late_items: List[LateGapItem] = []
    late_total = 0.0
    late_count = 0
    for key in list(set(pmap2.keys()) | set(smap2.keys())):
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
                        placed_amount=round(float(pd.to_numeric(cyc.loc[p_i, c_am], errors="coerce") or 0.0), 2),
                        settled_amount=round(float(pd.to_numeric(cyc.loc[s_i, c_am], errors="coerce") or 0.0), 2),
                    ))
    row4 = Row4_Late(late_gap_count=late_count, late_gap_total_minutes=round(late_total, 2), items=late_items[:50])

    # ---- 5) En çok çevrim yapılan 3 oyun (wager & profit) ----
    top_items: List[TopGame] = []
    if c_game:
        # wager = Σ|PLACED|; profit = Σ(SETTLED + PLACED)
        cyc["_amt"] = pd.to_numeric(cyc[c_am], errors="coerce").fillna(0.0)
        placed_by_game = cyc.loc[cyc["__r"] == "BET_PLACED"].groupby(c_game)["_amt"].apply(lambda s: float(s.abs().sum()))
        profit_by_game = cyc.groupby(c_game)["_amt"].apply(
            lambda s: float(s[(cyc.loc[s.index, "__r"] == "BET_PLACED")].sum() +
                            s[(cyc.loc[s.index, "__r"] == "BET_SETTLED")].sum()))
        if not placed_by_game.empty:
            order = placed_by_game.sort_values(ascending=False).head(3).index
            for g in order:
                top_items.append(TopGame(
                    game_name=str(g),
                    wager=round(float(placed_by_game.get(g, 0.0)), 2),
                    profit=round(float(profit_by_game.get(g, 0.0)), 2),
                ))
    row5 = Row5_TopGames(items=top_items)

    currency = (str(cyc[c_curr].iloc[0]) if c_curr and not cyc[c_curr].empty else None)
    member_val = str(df.iloc[s_idx][c_mb])

    return BriefResponse(
        filename=file.filename,
        cycle_index=int(cycle_index),
        member_id=member_val,
        row1_last_op=last_op,
        row2_wager=row2,
        row3_open=row3,
        row4_late=row4,
        row5_top_games=row5,
        currency=currency
    )
