from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from pydantic import BaseModel
from io import BytesIO
from typing import Optional, List, Dict, Any, Tuple

router = APIRouter()

# ===================== MODELLER =====================

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
    label: str  # "tarih • tutar ₺ • [yöntem]"

class CyclesResponse(BaseModel):
    filename: str
    total_rows: int
    cycles: List[CycleEntry]

class TopItem(BaseModel):
    name: str
    value: float

class BetItem(BaseModel):
    reference_id: Optional[str] = None
    placed_ts: Optional[str] = None
    settled_ts: Optional[str] = None
    gap_minutes: Optional[float] = None
    placed_amount: Optional[float] = None
    settled_amount: Optional[float] = None

class MemberCycleReport(BaseModel):
    member_id: str
    cycle_index: int
    cycle_start_at: Optional[str]
    cycle_end_at: Optional[str]

    # Deposit başı
    last_operation_type: str
    last_operation_ts: Optional[str]
    last_deposit_amount: Optional[float] = None
    last_payment_method: Optional[str] = None

    # Finansal akış
    sum_adjustment: float
    sum_withdrawal_approved: float
    sum_withdrawal_declined: float
    bonus_to_main_amount: float

    # Çevrim & kâr (genel)
    total_wager: float
    total_profit: float
    requirement: float
    remaining: float

    # Kaynağa göre (ana para / bonus / adjustment)
    main_wager: float
    main_profit: float
    bonus_wager: float
    bonus_profit: float
    adjustment_wager: float
    adjustment_profit: float

    # Açık & Geç sonuçlanan (adet + toplam ₺ + detay listeleri)
    open_count: int
    open_amount: float
    open_list: List[BetItem]

    late_missing_count: int
    late_missing_amount: float
    late_missing_list: List[BetItem]

    late_gap_count: int
    late_gap_total_gap_minutes: float
    late_gap_list: List[BetItem]

    # Global unsettled (bilgi)
    global_unsettled_count: int
    global_unsettled_amount: float

    # Deposit öncesi açık (bilgi)
    pre_deposit_unsettled_count: int
    pre_deposit_unsettled_amount: float

    # Bonus meta (bilgi)
    bonus_name: Optional[str] = None
    bonus_amount: Optional[float] = None

    # Top-3 (kâra göre)
    top_games: List[TopItem]
    top_providers: List[TopItem]

    currency: Optional[str] = None

class ComputeResult(BaseModel):
    filename: str
    total_rows: int
    reports: List[MemberCycleReport]


# ===================== YARDIMCI =====================

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
            sheet_names = xls.sheet_names
            first_sheet = sheet_names[0] if sheet_names else None
            if not first_sheet:
                raise ValueError("Çalışma sayfası bulunamadı")
            df = pd.read_excel(xls, sheet_name=first_sheet)
        elif name.endswith(".csv"):
            df = pd.read_csv(BytesIO(content))
            sheet_names = ["csv"]
            first_sheet = "csv"
        else:
            raise HTTPException(status_code=400, detail="Desteklenmeyen dosya türü")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Dosya okunamadı: {e}")

    df.columns = [str(c).strip() for c in df.columns]
    return df, sheet_names, (sheet_names[0] if sheet_names else None)

def _col(df, *cands: str) -> Optional[str]:
    cols_lower = {c.lower(): c for c in df.columns}
    for cand in cands:
        c = cand.lower()
        if c in cols_lower:
            return cols_lower[c]
    for c in df.columns:
        for cand in cands:
            if c.lower().replace(" ", "") == cand.lower().replace(" ", ""):
                return c
    return None

def _to_dt(series):
    import pandas as pd  # type: ignore
    return pd.to_datetime(series, errors="coerce", dayfirst=True)

def _norm_reason(v: Any) -> str:
    if not isinstance(v, str):
        return ""
    s = v.strip().lower()
    if s in {"bet_placed", "bet placed"}: return "BET_PLACED"
    if s in {"bet_settled", "bet settled"}: return "BET_SETTLED"
    if s in {"deposit", "yatırım", "yatirim"}: return "DEPOSIT"
    if s in {"bonus_given", "bonus given"}: return "BONUS_GIVEN"
    if s in {"casino_bonus_achieved", "casino bonus achieved"}: return "BONUS_ACHIEVED"
    if "placed" in s or "stake" in s or "wager" in s: return "BET_PLACED"
    if "settled" in s or "payout" in s or "result" in s: return "BET_SETTLED"
    if "withdrawal_decline" in s: return "WITHDRAWAL_DECLINE"
    if "withdrawal" in s: return "WITHDRAWAL"
    if "adjust" in s: return "ADJUSTMENT"
    if "bonus" in s and "achiev" in s: return "BONUS_ACHIEVED"
    if "bonus" in s: return "BONUS_GIVEN"
    return s.upper()

def _currency_column(df) -> Optional[str]:
    return _col(df, "Currency", "Base Currency", "System Currency")

def _amount_column(df) -> str:
    col_amount = _col(df, "Amount", "Base Amount", "Bet Amount", "Stake")
    if not col_amount:
        raise HTTPException(status_code=422, detail="Amount kolonları bulunamadı")
    return col_amount

def _payment_str(row, col_payment: Optional[str], col_details: Optional[str]) -> Optional[str]:
    pm = str(row[col_payment]).strip() if col_payment and row.get(col_payment) is not None else ""
    dt = str(row[col_details]).strip() if col_details and row.get(col_details) is not None else ""
    s = " / ".join([x for x in [pm, dt] if x])
    return s or None

def _fmt(ts_val) -> Optional[str]:
    try:
        return str(ts_val) if ts_val is not None else None
    except Exception:
        return None


# ===================== ENDPOINTLER =====================

@router.post("", response_model=UploadSummary)
async def upload_file(file: UploadFile = File(...)):
    df, sheet_names, first_sheet = _read_dataframe_sync(file)
    return UploadSummary(
        filename=file.filename,
        sheet_names=sheet_names,
        first_sheet=first_sheet,
        columns=[str(c) for c in df.columns],
        row_count_sampled=min(len(df), 5000),
        row_count_exact=int(len(df)),
    )

@router.post("/cycles", response_model=CyclesResponse)
async def list_cycles(file: UploadFile = File(...), member_id: Optional[str] = Form(None)):
    """
    Yalnızca DEPOSIT satırlarından cycle üretir (Deposit → next Deposit).
    Dropdown etiketi: "{tarih} • {tutar} ₺ • [yöntem]".
    """
    import pandas as pd  # type: ignore
    df, _, _ = _read_dataframe_sync(file)

    col_ts = _col(df, "Date & Time", "Date", "timestamp", "time")
    col_member = _col(df, "Player ID", "member_id", "User ID", "Account ID")
    col_reason = _col(df, "Reason", "Description", "Event")
    col_amount = _amount_column(df)
    col_payment = _col(df, "Payment Method", "Method")
    col_details = _col(df, "Details", "Note")

    for name, col in [("Date & Time", col_ts), ("Player ID", col_member), ("Reason", col_reason)]:
        if not col:
            raise HTTPException(status_code=422, detail=f"Eksik kolon: {name}")

    df[col_ts] = _to_dt(df[col_ts])
    df[col_amount] = pd.to_numeric(df[col_amount], errors="coerce").fillna(0.0)
    df["__reason_type"] = df[col_reason].apply(_norm_reason)
    df = df.sort_values(col_ts).reset_index(drop=True)

    if member_id:
        df = df[df[col_member].astype(str) == str(member_id)].reset_index(drop=True)

    cycles: List[CycleEntry] = []
    dep_idx = df.index[df["__reason_type"] == "DEPOSIT"].tolist()
    if not dep_idx:
        return CyclesResponse(filename=file.filename, total_rows=int(len(df)), cycles=[])

    for i, s_idx in enumerate(dep_idx):
        e_idx = dep_idx[i + 1] if i + 1 < len(dep_idx) else len(df)
        row = df.iloc[s_idx]
        start_at = _fmt(row[col_ts])
        deposit_amount = float(row[col_amount])
        pay = _payment_str(row, col_payment, col_details)
        label = f"{start_at} • {deposit_amount:,.2f} ₺" + (f" • [{pay}]" if pay else "")
        cycles.append(CycleEntry(
            index=i,
            start_row=int(s_idx),
            end_row=int(e_idx),
            start_at=start_at or "",
            deposit_amount=round(deposit_amount, 2),
            payment_method=pay,
            label=label
        ))

    return CyclesResponse(filename=file.filename, total_rows=int(len(df)), cycles=cycles)

@router.post("/compute", response_model=ComputeResult)
async def compute(
    file: UploadFile = File(...),
    cycle_index: Optional[int] = Form(None),     # Seçilen DEPOSIT cycle index'i
    member_id: Optional[str] = Form(None),
    threshold_minutes: int = Form(5),            # LATE eşiği (dk)
):
    import pandas as pd  # type: ignore
    import numpy as np   # type: ignore

    df, _, _ = _read_dataframe_sync(file)
    total_rows = int(len(df))

    col_ts = _col(df, "Date & Time", "Date", "timestamp", "time")
    col_member = _col(df, "Player ID", "member_id", "User ID", "Account ID")
    col_reason = _col(df, "Reason", "Description", "Event")
    col_ref = _col(df, "Reference ID", "Ref ID", "Bet ID", "Ticket")
    col_betcid = _col(df, "BetCID", "Bet CID")
    col_game = _col(df, "Game Name", "Game")
    col_provider = _col(df, "Game Provider", "Provider")
    col_amount = _amount_column(df)
    col_payment = _col(df, "Payment Method", "Method")
    col_details = _col(df, "Details", "Note")
    col_currency = _currency_column(df)
    col_balance = _col(df, "Balance", "Base Balance", "System Balance")

    for name, col in [("Date & Time", col_ts), ("Player ID", col_member), ("Reason", col_reason)]:
        if not col:
            raise HTTPException(status_code=422, detail=f"Eksik kolon: {name}")

    # Normalize
    df[col_ts] = _to_dt(df[col_ts])
    df[col_amount] = pd.to_numeric(df[col_amount], errors="coerce").fillna(0.0)
    for c in [col_ref, col_betcid, col_game, col_provider, col_payment, col_details, col_currency]:
        if c: df[c] = df[c].astype(str)

    df["__reason_type"] = df[col_reason].apply(_norm_reason)
    df = df.sort_values(col_ts).reset_index(drop=True)

    if member_id:
        df = df[df[col_member].astype(str) == str(member_id)].reset_index(drop=True)

    # Deposit bazlı cycle sınırları
    dep_idx = df.index[df["__reason_type"] == "DEPOSIT"].tolist()
    if not dep_idx:
        raise HTTPException(status_code=422, detail="Bu dosyada DEPOSIT bulunamadı.")
    bounds: List[Tuple[int, int]] = []
    for i, s in enumerate(dep_idx):
        e = dep_idx[i + 1] if i + 1 < len(dep_idx) else len(df)
        bounds.append((int(s), int(e)))

    if cycle_index is None:
        cycle_index = len(bounds) - 1
    if cycle_index < 0 or cycle_index >= len(bounds):
        raise HTTPException(status_code=400, detail=f"Geçersiz cycle_index: {cycle_index}")

    start_idx, end_idx = bounds[cycle_index]
    cycle = df.iloc[start_idx:end_idx].copy()

    # Başlangıç
    dep_row = df.iloc[start_idx]
    cycle_start_at = _fmt(dep_row[col_ts])
    cycle_end_at = _fmt(df.iloc[end_idx - 1][col_ts]) if end_idx - 1 >= start_idx else None
    deposit_amount = float(dep_row[col_amount])
    payment_method = _payment_str(dep_row, col_payment, col_details)
    balance_at_deposit = float(dep_row[col_balance]) if col_balance and pd.notna(dep_row[col_balance]) else None

    # Bonus meta (deposit'ten sonra görülen ilk BONUS_GIVEN)
    bonus_name = None
    bonus_amount = None
    sub_after = cycle.iloc[1:] if len(cycle) > 1 else cycle.iloc[0:0]
    if not sub_after.empty:
        bg = sub_after[sub_after["__reason_type"] == "BONUS_GIVEN"]
        if not bg.empty:
            b_row = bg.iloc[0]
            bonus_amount = float(b_row[col_amount])
            bonus_name = (str(b_row[col_details] or b_row[col_reason]) if col_details else str(b_row[col_reason])).strip() or "Bonus"

    # Mask'ler
    placed_mask = cycle["__reason_type"] == "BET_PLACED"
    settled_mask = cycle["__reason_type"] == "BET_SETTLED"
    adj_mask = cycle["__reason_type"] == "ADJUSTMENT"
    wdr_mask = cycle["__reason_type"] == "WITHDRAWAL"
    wdr_dec_mask = cycle["__reason_type"] == "WITHDRAWAL_DECLINE"
    bon_ach_mask = cycle["__reason_type"] == "BONUS_ACHIEVED"

    # Finansal akış
    sum_adjustment = float(cycle.loc[adj_mask, col_amount].sum()) if adj_mask.any() else 0.0
    sum_withdrawal_approved = float(cycle.loc[wdr_mask, col_amount].sum()) if wdr_mask.any() else 0.0
    sum_withdrawal_declined = float(cycle.loc[wdr_dec_mask, col_amount].sum()) if wdr_dec_mask.any() else 0.0
    bonus_to_main_amount = float(cycle.loc[bon_ach_mask, col_amount].sum()) if bon_ach_mask.any() else 0.0

    # ====== Bahis eşleştirme anahtarı (REF → BetCID → fallback) ======
    def rid_at(i):
        if col_ref and isinstance(cycle.iloc[i][col_ref], str) and cycle.iloc[i][col_ref].strip():
            return f"R:{cycle.iloc[i][col_ref]}"
        if col_betcid and isinstance(cycle.iloc[i][col_betcid], str) and cycle.iloc[i][col_betcid].strip():
            return f"C:{cycle.iloc[i][col_betcid]}"
        # Fallback: oyun+id+yakın zaman (dakika)
        g = cycle.iloc[i][col_game] if col_game else ""
        t = cycle.iloc[i][col_ts]
        return f"F:{g}|{t}"

    # placed/settled listeleri (index'ler)
    placed_ix = cycle.index[placed_mask].tolist()
    settled_ix = cycle.index[settled_mask].tolist()

    # Anahtar → index listesi
    from collections import defaultdict, deque
    p_map: Dict[str, deque] = defaultdict(deque)
    s_map: Dict[str, deque] = defaultdict(deque)
    for i in placed_ix:
        p_map[rid_at(cycle.index.get_loc(i))].append(i)
    for i in settled_ix:
        s_map[rid_at(cycle.index.get_loc(i))].append(i)

    # Pairing by order (placed ↔ settled)
    pairs: List[Tuple[int, int]] = []  # (p_i, s_i)
    for key in set(list(p_map.keys()) + list(s_map.keys())):
        ps, ss = p_map.get(key, deque()), s_map.get(key, deque())
        while ps and ss:
            pairs.append((ps.popleft(), ss.popleft()))
    # Kalanlar
    unpaired_p = [(k, list(v)) for k, v in p_map.items() if v]
    unpaired_s = [(k, list(v)) for k, v in s_map.items() if v]

    # ====== Kaynak ataması (ana para / bonus / adjustment) ======
    # Her placed için, ondan ÖNCEKİ en yakın finansal olayı bul: DEPOSIT / BONUS_GIVEN / ADJUSTMENT
    fin_mask = cycle["__reason_type"].isin(["DEPOSIT", "BONUS_GIVEN", "ADJUSTMENT"])
    fin_ix = cycle.index[fin_mask].tolist()
    fin_types = {i: cycle.loc[i, "__reason_type"] for i in fin_ix}

    def source_for(idx: int) -> str:
        # geriye doğru tara
        src = "MAIN"  # default
        for j in range(idx, start_idx - 1, -1):
            row = cycle.loc[j]
            t = row["__reason_type"]
            if t in ("DEPOSIT", "BONUS_GIVEN", "ADJUSTMENT"):
                if t == "DEPOSIT": src = "MAIN"
                elif t == "BONUS_GIVEN": src = "BONUS"
                else: src = "ADJUSTMENT"
                break
        return src

    # Toplamlar
    total_wager = float(cycle.loc[placed_mask, col_amount].abs().sum())
    total_profit = float(cycle.loc[settled_mask, col_amount].sum() + cycle.loc[placed_mask, col_amount].sum())

    main_wager = bonus_wager = adjustment_wager = 0.0
    main_profit = bonus_profit = adjustment_profit = 0.0

    # Çiftler (tamamlanan bahisler) üzerinden profit'i yaz
    for p_i, s_i in pairs:
        src = source_for(cycle.index.get_loc(p_i))
        p_amt = float(cycle.loc[p_i, col_amount])
        s_amt = float(cycle.loc[s_i, col_amount])
        net = p_amt + s_amt
        abs_p = abs(p_amt)
        if src == "MAIN":
            main_wager += abs_p
            main_profit += net
        elif src == "BONUS":
            bonus_wager += abs_p
            bonus_profit += net
        else:
            adjustment_wager += abs_p
            adjustment_profit += net

    # Açık bahisler (placed olup eşleşmeyenler)
    open_list: List[BetItem] = []
    open_amount = 0.0
    open_count = 0
    for key, ix_list in unpaired_p:
        for p_i in ix_list:
            open_count += 1
            amt = float(abs(cycle.loc[p_i, col_amount]))
            open_amount += amt
            open_list.append(BetItem(
                reference_id=(cycle.loc[p_i, col_ref] if col_ref else None),
                placed_ts=_fmt(cycle.loc[p_i, col_ts]),
                placed_amount=round(amt, 2)
            ))

    # Geç sonuçlanan — missing placed (settled var, placed yok)
    late_missing_list: List[BetItem] = []
    late_missing_amount = 0.0
    late_missing_count = 0
    for key, ix_list in unpaired_s:
        for s_i in ix_list:
            late_missing_count += 1
            amt = float(cycle.loc[s_i, col_amount])
            late_missing_amount += amt
            late_missing_list.append(BetItem(
                reference_id=(cycle.loc[s_i, col_ref] if col_ref else None),
                settled_ts=_fmt(cycle.loc[s_i, col_ts]),
                settled_amount=round(amt, 2)
            ))

    # Geç sonuçlanan — gap > threshold (eşleşen çiftlerde)
    late_gap_list: List[BetItem] = []
    late_gap_total = 0.0
    late_gap_count = 0
    for p_i, s_i in pairs:
        p_ts = cycle.loc[p_i, col_ts]
        s_ts = cycle.loc[s_i, col_ts]
        if p_ts is not None and s_ts is not None:
            gap_min = (s_ts - p_ts).total_seconds() / 60.0
            if gap_min > float(threshold_minutes):
                late_gap_count += 1
                late_gap_total += gap_min
                late_gap_list.append(BetItem(
                    reference_id=(cycle.loc[p_i, col_ref] if col_ref else None),
                    placed_ts=_fmt(p_ts),
                    settled_ts=_fmt(s_ts),
                    gap_minutes=round(float(gap_min), 2),
                    placed_amount=round(float(cycle.loc[p_i, col_amount]), 2),
                    settled_amount=round(float(cycle.loc[s_i, col_amount]), 2),
                ))

    # Global unsettled (tüm dosyada)
    global_unsettled_count = 0
    global_unsettled_amount = 0.0
    if col_ref:
        placed_all = df["__reason_type"] == "BET_PLACED"
        settled_all = df["__reason_type"] == "BET_SETTLED"
        placed_rids_all = set(df.loc[placed_all & df[col_ref].notna(), col_ref].astype(str))
        settled_rids_all = set(df.loc[settled_all & df[col_ref].notna(), col_ref].astype(str))
        diff_all = placed_rids_all - settled_rids_all
        global_unsettled_count = len(diff_all)
        if diff_all:
            global_unsettled_amount = float(df.loc[placed_all & df[col_ref].isin(diff_all), col_amount].abs().sum())

    # Pre-deposit unsettled (bilgi)
    pre_dep_unset_count = 0
    pre_dep_unset_amount = 0.0
    if col_ref and start_idx > 0:
        pre = df.iloc[:start_idx]
        p_mask = pre["__reason_type"] == "BET_PLACED"
        s_mask = pre["__reason_type"] == "BET_SETTLED"
        r_p = set(pre.loc[p_mask & pre[col_ref].notna(), col_ref].astype(str))
        r_s = set(pre.loc[s_mask & pre[col_ref].notna(), col_ref].astype(str))
        diff_pre = r_p - r_s
        pre_dep_unset_count = len(diff_pre)
        if diff_pre:
            pre_dep_unset_amount = float(pre.loc[p_mask & pre[col_ref].isin(diff_pre), col_amount].abs().sum())

    # Top-3 kârlı oyun/sağlayıcı (net > 0)
    def net_by(group_col):
        g = cycle.groupby(group_col)[col_amount].apply(
            lambda s: float(
                s[cycle.loc[s.index, "__reason_type"] == "BET_SETTLED"].sum() +
                s[cycle.loc[s.index, "__reason_type"] == "BET_PLACED"].sum()
            )
        )
        g = g[g > 0].sort_values(ascending=False).head(3)
        return [TopItem(name=str(k), value=round(float(v), 2)) for k, v in g.items()]

    top_games = net_by(col_game) if col_game else []
    top_providers = net_by(col_provider) if col_provider else []
    currency = (str(cycle[col_currency].iloc[0]) if col_currency and not cycle[col_currency].empty else None)
    member_val = str(dep_row[col_member])

    requirement = float(deposit_amount)
    remaining = float(max(requirement - total_wager, 0.0))

    report = MemberCycleReport(
        member_id=member_val,
        cycle_index=int(cycle_index),
        cycle_start_at=cycle_start_at,
        cycle_end_at=cycle_end_at,

        last_operation_type="DEPOSIT",
        last_operation_ts=cycle_start_at,
        last_deposit_amount=round(float(deposit_amount), 2),
        last_payment_method=payment_method,

        sum_adjustment=round(float(sum_adjustment), 2),
        sum_withdrawal_approved=round(float(sum_withdrawal_approved), 2),
        sum_withdrawal_declined=round(float(sum_withdrawal_declined), 2),
        bonus_to_main_amount=round(float(bonus_to_main_amount), 2),

        total_wager=round(float(total_wager), 2),
        total_profit=round(float(total_profit), 2),
        requirement=round(float(requirement), 2),
        remaining=round(float(remaining), 2),

        main_wager=round(main_wager, 2),
        main_profit=round(main_profit, 2),
        bonus_wager=round(bonus_wager, 2),
        bonus_profit=round(bonus_profit, 2),
        adjustment_wager=round(adjustment_wager, 2),
        adjustment_profit=round(adjustment_profit, 2),

        open_count=int(open_count),
        open_amount=round(open_amount, 2),
        open_list=open_list[:50],

        late_missing_count=int(late_missing_count),
        late_missing_amount=round(late_missing_amount, 2),
        late_missing_list=late_missing_list[:50],

        late_gap_count=int(late_gap_count),
        late_gap_total_gap_minutes=round(float(late_gap_total), 2),
        late_gap_list=late_gap_list[:50],

        global_unsettled_count=int(global_unsettled_count),
        global_unsettled_amount=round(float(global_unsettled_amount), 2),

        pre_deposit_unsettled_count=int(pre_dep_unset_count),
        pre_deposit_unsettled_amount=round(float(pre_dep_unset_amount), 2),

        bonus_name=bonus_name,
        bonus_amount=(round(float(bonus_amount), 2) if bonus_amount is not None else None),

        top_games=top_games,
        top_providers=top_providers,
        currency=currency
    )

    return ComputeResult(filename=file.filename, total_rows=total_rows, reports=[report])
