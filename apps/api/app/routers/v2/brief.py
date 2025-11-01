from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from pydantic import BaseModel
from typing import Optional, List, Tuple, Dict
from app.services.parse import read_df, col, to_dt, norm_reason, payment_str
from app.services.matchers import build_key
import pandas as pd
from collections import defaultdict, deque

router = APIRouter()

# ---------- MODELLER ----------
class Row1_LastOp(BaseModel):
    type: str
    ts: str
    amount: float
    method: Optional[str] = None
    bonus_detail: Optional[str] = None
    bonus_kind: Optional[str] = None

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

class GameLine(BaseModel):
    game_name: str
    wager: float        # Bahis (toplam çevrim)
    profit: float       # Kazanç (yalnızca SETTLED toplamı)
    ggr: float          # GGR = Kazanç - Bahis

class Row5_TopWager(BaseModel):
    items: List[GameLine]

class Row6_TopProfit(BaseModel):
    items: List[GameLine]

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


# ---------- HELPERS ----------
def _start_bounds(df: pd.DataFrame, reason_col: str, amt_col: str) -> List[Tuple[int, int]]:
    """Cycle başlangıcı: DEPOSIT | BONUS_GIVEN (FREE_SPIN_GIVEN normalize) | ADJUSTMENT(>0)."""
    starts = df.index[
        (df[reason_col].isin(["DEPOSIT", "BONUS_GIVEN"])) |
        ((df[reason_col] == "ADJUSTMENT") & (df[amt_col] > 0))
    ].tolist()
    if not starts:
        return [(0, len(df))]
    bounds: List[Tuple[int, int]] = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(df)
        bounds.append((int(s), int(e)))
    return bounds

def _bonus_kind(txt: str) -> str:
    s = (txt or "").lower()
    if any(k in s for k in ["trial", "deneme"]): return "trial"
    if any(k in s for k in ["free", "freespin", "spin"]): return "freespin"
    if any(k in s for k in ["cashback", "kayıp", "kayip", "loss"]): return "cashback"
    if any(k in s for k in ["deposit", "yatırım", "yatirim"]): return "deposit"
    return "other"

def _fmt(ts) -> str:
    return str(ts) if ts is not None else ""

def _key(df, i, c_ref, c_cid) -> str:
    vref = str(df.loc[i, c_ref]).strip() if c_ref and pd.notna(df.loc[i, c_ref]) else ""
    if vref and vref.lower() not in ("nan", "none"): return f"R:{vref}"
    vbc = str(df.loc[i, c_cid]).strip() if c_cid and pd.notna(df.loc[i, c_cid]) else ""
    if vbc and vbc.lower() not in ("nan", "none"): return f"C:{vbc}"
    return f"F:{i}"


# ---------- ENDPOINT ----------
@router.post("", response_model=BriefResponse)
async def brief(
    file: UploadFile = File(...),
    start_cycle_index: Optional[int] = Form(None),
    end_cycle_index: Optional[int] = Form(None),
    cycle_index: Optional[int] = Form(None),  # backward compat (tek seçim → start=end)
    member_id: Optional[str] = Form(None),
    threshold_minutes: int = Form(5),
):
    # --- read & normalize ---
    df, _ = read_df(file)

    c_ts = col(df, "Date & Time", "Date", "timestamp", "time")
    c_mb = col(df, "Player ID", "member_id", "User ID", "Account ID")
    c_rs = col(df, "Reason", "Description", "Event")
    c_am = col(df, "Amount", "Base Amount", "Bet Amount", "Stake")
    c_ref = col(df, "Reference ID", "Ref ID", "Bet ID", "Ticket")
    c_cid = col(df, "BetCID", "Bet CID")
    c_pm = col(df, "Payment Method", "Method")
    c_det = col(df, "Details", "Note")
    c_game = col(df, "Game Name", "Game")
    c_curr = col(df, "Currency", "Base Currency", "System Currency")

    for name, c in [("Date & Time", c_ts), ("Player ID", c_mb), ("Reason", c_rs), ("Amount", c_am)]:
        if not c:
            raise HTTPException(status_code=422, detail=f"Eksik kolon: {name}")

    df[c_ts] = to_dt(df[c_ts])
    df = df.sort_values(c_ts).reset_index(drop=True)
    df["__r"] = df[c_rs].apply(norm_reason)
    df["_amt"] = pd.to_numeric(df[c_am], errors="coerce").fillna(0.0)

    if member_id:
        df = df[df[c_mb].astype(str) == str(member_id)].reset_index(drop=True)
    if len(df) == 0:
        raise HTTPException(status_code=422, detail="Filtre sonrası satır yok.")

    # --- cycle aralığı (BAŞLANGIÇ..BİTİŞ dahil) ---
    bounds = _start_bounds(df, "__r", "_amt")
    total = len(bounds)

    if start_cycle_index is None and cycle_index is not None:
        start_cycle_index = cycle_index
        end_cycle_index = cycle_index if end_cycle_index is None else end_cycle_index

    if start_cycle_index is None:
        start_cycle_index = total - 1
    if end_cycle_index is None:
        end_cycle_index = start_cycle_index

    if not (0 <= start_cycle_index < total):
        raise HTTPException(status_code=400, detail="Geçersiz start_cycle_index")
    if not (start_cycle_index <= end_cycle_index < total):
        raise HTTPException(status_code=400, detail="Geçersiz end_cycle_index")

    s_idx = bounds[start_cycle_index][0]
    e_idx = bounds[end_cycle_index][1]  # ✅ BAŞLANGIÇ..BİTİŞ aralığı
    cyc = df.iloc[s_idx:e_idx].copy()
    member_val = str(df.iloc[s_idx][c_mb])

    # 1) Son İşlem & Kaynak (Tür → Tutar → Tarih → Kaynak/Detay → Bonus Türü)
    fin_any = cyc["__r"].isin(["DEPOSIT", "BONUS_GIVEN", "ADJUSTMENT"])
    fin_valid = (cyc["__r"].isin(["DEPOSIT", "BONUS_GIVEN"])) | ((cyc["__r"] == "ADJUSTMENT") & (cyc["_amt"] > 0))
    if fin_valid.any():
        last_i = cyc.index[fin_valid][-1]
        r = cyc.loc[last_i]
        rtype = "BONUS" if r["__r"] == "BONUS_GIVEN" else r["__r"]
        method = payment_str(r, c_pm, c_det) if rtype in ("DEPOSIT", "ADJUSTMENT") else None
        bonus_detail = ((str(r[c_det] or r[c_rs]) if c_det else str(r[c_rs])) if rtype == "BONUS" else None)
        bonus_kind = (_bonus_kind(str(r[c_det] or r[c_rs])) if rtype == "BONUS" else None)
        last_op = Row1_LastOp(
            type=rtype, ts=_fmt(r[c_ts]), amount=round(float(r["_amt"]), 2),
            method=method, bonus_detail=(bonus_detail.strip() if isinstance(bonus_detail, str) else None),
            bonus_kind=bonus_kind
        )
        win_from = r[c_ts]
        start_for_next = last_i
    else:
        win_from = cyc.iloc[0][c_ts]
        last_op = Row1_LastOp(type="DEPOSIT", ts=_fmt(win_from), amount=0.0, method=None)
        start_for_next = cyc.index[0]

    # 2) Pencere: başlangıç → sonraki finansal (varsa) yoksa aralık sonu
    if fin_any.any():
        nxt = cyc.index[(cyc.index > start_for_next) & fin_any]
        win_to = cyc.loc[nxt[0], c_ts] if len(nxt) else cyc.iloc[-1][c_ts]
    else:
        win_to = cyc.iloc[-1][c_ts]

    in_win = (cyc[c_ts] >= win_from) & (cyc[c_ts] <= win_to)
    placed_win = (cyc["__r"] == "BET_PLACED") & in_win
    wager_total = float(cyc.loc[placed_win, "_amt"].abs().sum())
    row2 = Row2_Wager(
        window_from=_fmt(win_from),
        window_to=_fmt(win_to),
        wager_total=round(wager_total, 2),
        wager_count=int(placed_win.sum()),
    )

    # 3) Açık işlemler
    placed_ix = cyc.index[cyc["__r"] == "BET_PLACED"].tolist()
    settled_ix = cyc.index[cyc["__r"] == "BET_SETTLED"].tolist()
    pmap: Dict[str, deque] = defaultdict(deque)
    smap: Dict[str, deque] = defaultdict(deque)
    for i in placed_ix:  pmap[_key(cyc, i, c_ref, c_cid)].append(i)
    for i in settled_ix: smap[_key(cyc, i, c_ref, c_cid)].append(i)
    for key in set(pmap) | set(smap):
        ps, ss = pmap.get(key, deque()), smap.get(key, deque())
        while ps and ss:
            ps.popleft(); ss.popleft()
    open_items: List[OpenItem] = []
    open_total = 0.0
    for _, q in pmap.items():
        for ip in q:
            amt = float(cyc.loc[ip, "_amt"])
            open_total += abs(amt)
            open_items.append(OpenItem(id=(str(cyc.loc[ip, c_ref]) if c_ref else None),
                                       placed_ts=_fmt(cyc.loc[ip, c_ts]),
                                       amount=round(abs(amt), 2)))
    row3 = Row3_Open(open_total_amount=round(open_total, 2), open_count=len(open_items), items=open_items[:50])

    # 4) Geç sonuçlanan (>5dk)
    pmap2: Dict[str, deque] = defaultdict(deque)
    smap2: Dict[str, deque] = defaultdict(deque)
    for i in placed_ix:  pmap2[_key(cyc, i, c_ref, c_cid)].append(i)
    for i in settled_ix: smap2[_key(cyc, i, c_ref, c_cid)].append(i)
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

    # 5) En çok ÇEVRİM (Bahis/Kazanç/GGR) — Kazanç = yalnızca SETTLED toplamı
    top_wager_items: List[GameLine] = []
    if c_game:
        wager_by_game = cyc.loc[cyc["__r"] == "BET_PLACED"].groupby(c_game)["_amt"].apply(lambda s: float(s.abs().sum()))
        revenue_by_game = cyc.loc[cyc["__r"] == "BET_SETTLED"].groupby(c_game)["_amt"].sum() if (cyc["__r"] == "BET_SETTLED").any() else pd.Series(dtype=float)
        order_wager = (wager_by_game.sort_values(ascending=False).head(3).index) if not wager_by_game.empty else []
        for g in order_wager:
            w = float(wager_by_game.get(g, 0.0))
            rev = float(revenue_by_game.get(g, 0.0))
            top_wager_items.append(GameLine(game_name=str(g), wager=round(w, 2), profit=round(rev, 2), ggr=round(rev - w, 2)))
    row5 = Row5_TopWager(items=top_wager_items)

    # 6) En çok KÂR (Bahis/Kazanç/GGR) — sıralama GGR’ye göre
    top_profit_items: List[GameLine] = []
    if c_game:
        # aynı hesaplamalar
        wager_by_game2 = cyc.loc[cyc["__r"] == "BET_PLACED"].groupby(c_game)["_amt"].apply(lambda s: float(s.abs().sum()))
        revenue_by_game2 = cyc.loc[cyc["__r"] == "BET_SETTLED"].groupby(c_game)["_amt"].sum() if (cyc["__r"] == "BET_SETTLED").any() else pd.Series(dtype=float)
        # GGR haritası
        ggr_map: Dict[str, float] = {}
        all_games = set(wager_by_game2.index) | set(revenue_by_game2.index)
        for g in all_games:
            w = float(wager_by_game2.get(g, 0.0))
            rev = float(revenue_by_game2.get(g, 0.0))
            ggr_map[str(g)] = rev - w
        # en çok kârlı 3 oyun
        for g, ggr_val in sorted(ggr_map.items(), key=lambda x: x[1], reverse=True)[:3]:
            w = float(wager_by_game2.get(g, 0.0))
            rev = float(revenue_by_game2.get(g, 0.0))
            top_profit_items.append(GameLine(game_name=str(g), wager=round(w, 2), profit=round(rev, 2), ggr=round(ggr_val, 2)))
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
