from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from pydantic import BaseModel
from io import BytesIO
from typing import Optional, List, Dict, Any, Tuple

router = APIRouter()

# =========================================================
# MODELLER
# =========================================================

class UploadSummary(BaseModel):
    filename: str
    sheet_names: List[str]
    first_sheet: Optional[str]
    columns: List[str]
    row_count_sampled: int
    row_count_exact: Optional[int] = None

class CycleEntry(BaseModel):
    index: int                       # cycle index (0..n-1)
    start_row: int                   # df index (inclusive)
    end_row: int                     # df index (exclusive)
    start_at: str                    # deposit timestamp (iso str)
    deposit_amount: float
    payment_method: Optional[str] = None
    bonus_after_deposit: Optional[str] = None    # varsa: "BonusName (Amount) @ ts"
    label: str                       # UI'da dropdown'da gösterilecek metin (tarih • tutar • (bonus ...))

class CyclesResponse(BaseModel):
    filename: str
    total_rows: int
    cycles: List[CycleEntry]

class TopItem(BaseModel):
    name: str
    value: float

class LateItem(BaseModel):
    reference_id: str
    placed_ts: Optional[str] = None
    settled_ts: Optional[str] = None
    gap_minutes: Optional[float] = None
    reason: str                     # "missing_placed" | "gap_over_threshold"

class MemberCycleReport(BaseModel):
    member_id: str

    # Cycle bilgisi
    cycle_index: int
    cycle_start_at: Optional[str]
    cycle_end_at: Optional[str]

    # Son işlem bağlamı (cycle başı deposit)
    last_operation_type: str                       # "DEPOSIT"
    last_operation_ts: Optional[str]
    last_deposit_amount: Optional[float] = None
    last_payment_method: Optional[str] = None

    # Finansal akış (cycle içi)
    sum_adjustment: float
    sum_withdrawal_approved: float
    sum_withdrawal_declined: float
    bonus_to_main_amount: float

    # Çevrim ve gereksinim
    total_wager: float                             # Σ |BET_PLACED|
    total_profit: float                            # Σ(SETTLED) + Σ(PLACED)
    requirement: float                             # 1x deposit
    remaining: float                               # max(requirement - total_wager, 0)

    # Unsettled (cycle) + GLOBAL
    unsettled_count: int
    unsettled_amount: float
    unsettled_reference_ids: List[str]
    global_unsettled_count: int
    global_unsettled_amount: float

    # LATE uyarıları (cycle)
    late_missing_placed_count: int
    late_missing_placed_refs: List[str]
    late_gap_count: int
    late_gap_total_gap_minutes: float
    late_gap_details: List[LateItem]

    # Deposit öncesi açık kupon (sadece bilgi—son cycle mantığını bozmaz)
    pre_deposit_unsettled_count: int
    pre_deposit_unsettled_amount: float

    # Bonus bilgisi (cycle içinde deposit'ten sonra görülen ilk bonus)
    bonus_name: Optional[str] = None
    bonus_amount: Optional[float] = None
    bonus_wager: Optional[float] = None
    bonus_profit: Optional[float] = None

    # Kârlı ilk 3
    top_games: List[TopItem]
    top_providers: List[TopItem]

    currency: Optional[str] = None

class ComputeResult(BaseModel):
    filename: str
    total_rows: int
    reports: List[MemberCycleReport]


# =========================================================
# YARDIMCI
# =========================================================

def _read_dataframe_sync(file: UploadFile):
    """Excel/CSV okur, ilk sheet'i döner (sync)."""
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
            raise HTTPException(status_code=400, detail="Desteklenmeyen dosya türü (.csv/.xlsx/.xls/.xlsm)")
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
    # boşlukları silerek gevşek eşleşme
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
    # net etiketleri önce
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
    # Amount öncelik; yoksa Base Amount
    col_amount = _col(df, "Amount", "Base Amount", "Bet Amount", "Stake")
    if not col_amount:
        raise HTTPException(status_code=422, detail="Amount kolonları bulunamadı")
    return col_amount

def _payment_str(row, col_payment: Optional[str], col_details: Optional[str]) -> Optional[str]:
    pm = str(row[col_payment]).strip() if col_payment and row.get(col_payment) is not None else ""
    dt = str(row[col_details]).strip() if col_details and row.get(col_details) is not None else ""
    s = " / ".join([x for x in [pm, dt] if x])
    return s or None

def _pair_placed_settled(cycle_df, col_ref: Optional[str], col_ts: str) -> Tuple[Dict[str, List[int]], Dict[str, List[int]]]:
    """
    Aynı Reference ID için placed/settled index listeleri.
    Reference ID boş/NaN olanlar eşleşmeye girmez.
    """
    import pandas as pd  # type: ignore
    placed_map: Dict[str, List[int]] = {}
    settled_map: Dict[str, List[int]] = {}
    if not col_ref:
        return placed_map, settled_map

    ref_series = cycle_df[col_ref].astype(str)
    reason = cycle_df["__reason_type"]

    for i, (rid, r) in enumerate(zip(ref_series, reason)):
        if rid.lower() in ("", "nan", "none"):
            continue
        if r == "BET_PLACED":
            placed_map.setdefault(rid, []).append(i)
        elif r == "BET_SETTLED":
            settled_map.setdefault(rid, []).append(i)

    # Indexler zaman sıralı zaten; yine de güvence
    for rid in placed_map:
        placed_map[rid].sort(key=lambda ix: cycle_df.iloc[ix][col_ts])
    for rid in settled_map:
        settled_map[rid].sort(key=lambda ix: cycle_df.iloc[ix][col_ts])

    return placed_map, settled_map

def _format_t(ts_val) -> Optional[str]:
    try:
        return str(ts_val) if ts_val is not None else None
    except Exception:
        return None


# =========================================================
# ENDPOINTLER
# =========================================================

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
    Yatırım bazlı cycle listesi (UI dropdown için).
    - Cycle = Deposit satırından bir sonraki Deposit'e kadar.
    - Label: "{ts} • {deposit_amount} ₺ • (Bonus: {amount})"
    - Bonus: deposit'ten sonra görülen ilk BONUS_GIVEN bilgisinden türetilir.
    - member_id verilirse sadece o oyuncunun cycle'ları döner.
    """
    import pandas as pd  # type: ignore
    df, _, _ = _read_dataframe_sync(file)

    col_ts = _col(df, "Date & Time", "Date", "timestamp", "time")
    col_member = _col(df, "Player ID", "member_id", "User ID", "Account ID")
    col_reason = _col(df, "Reason", "Description", "Event")
    col_amount = _amount_column(df)
    col_payment = _col(df, "Payment Method", "Method")
    col_details = _col(df, "Details", "Note")

    missing = [("Date & Time", col_ts), ("Player ID", col_member), ("Reason", col_reason)]
    missing = [name for name, v in missing if not v]
    if missing:
        raise HTTPException(status_code=422, detail=f"Eksik kolon(lar): {', '.join(missing)}")

    df[col_ts] = _to_dt(df[col_ts])
    df[col_amount] = pd.to_numeric(df[col_amount], errors="coerce").fillna(0.0)
    df["__reason_type"] = df[col_reason].apply(_norm_reason)
    df = df.sort_values(col_ts).reset_index(drop=True)

    if member_id:
        df = df[df[col_member].astype(str) == str(member_id)].reset_index(drop=True)

    cycles: List[CycleEntry] = []
    dep_idx = df.index[df["__reason_type"] == "DEPOSIT"].tolist()
    if not dep_idx:
        # Deposit yoksa "tek açık cycle" üretmeyelim; UI cycle gerektiriyor.
        return CyclesResponse(filename=file.filename, total_rows=int(len(df)), cycles=[])

    for i, s_idx in enumerate(dep_idx):
        e_idx = dep_idx[i + 1] if i + 1 < len(dep_idx) else len(df)
        row = df.iloc[s_idx]
        start_at = _format_t(row[col_ts])
        deposit_amount = float(row[col_amount])
        pay = _payment_str(row, col_payment, col_details)

        # deposit'ten sonra görülen ilk bonus_given (etiket)
        bonus_label = None
        sub = df.iloc[s_idx + 1:e_idx]
        if not sub.empty:
            bg = sub[sub["__reason_type"] == "BONUS_GIVEN"]
            if not bg.empty:
                b_row = bg.iloc[0]
                b_amount = float(b_row[col_amount])
                b_name = str(b_row[col_details] or b_row[col_reason] or "Bonus").strip() if col_details else str(b_row[col_reason] or "Bonus")
                b_ts = _format_t(b_row[col_ts])
                bonus_label = f"{b_name} ({b_amount:,.2f} ₺) @ {b_ts}"

        label = f"{start_at} • {deposit_amount:,.2f} ₺"
        if bonus_label:
            label += f" • (Bonus: {bonus_label})"
        if pay:
            label += f" • [{pay}]"

        cycles.append(CycleEntry(
            index=i,
            start_row=int(s_idx),
            end_row=int(e_idx),
            start_at=start_at or "",
            deposit_amount=round(deposit_amount, 2),
            payment_method=pay,
            bonus_after_deposit=bonus_label,
            label=label
        ))

    return CyclesResponse(filename=file.filename, total_rows=int(len(df)), cycles=cycles)

@router.post("/compute", response_model=ComputeResult)
async def compute(
    file: UploadFile = File(...),
    cycle_index: Optional[int] = Form(None),              # Seçilen cycle (list_cycles'tan gelen index)
    member_id: Optional[str] = Form(None),                # İstenirse tek oyuncu
    threshold_minutes: int = Form(5),                     # LATE tespiti için eşik
):
    """
    Seçilen cycle'dan itibaren (Deposit → next Deposit) tüm metrikleri hesaplar:
      - Finansal akış: adjustment / withdrawal / bonus_achieved
      - Çevrim (Σ|BET_PLACED|), kâr (Σ settled + Σ placed), requirement=1x deposit
      - Unsettled (cycle + global)
      - LATE (missing placed + gap>threshold)
      - Bonus meta (varsa): isim/kod, tutar, bonus_wager/profit
      - Kârlı top3 oyun/sağlayıcı
    """
    import pandas as pd  # type: ignore
    import numpy as np   # type: ignore

    df, _, _ = _read_dataframe_sync(file)
    total_rows = int(len(df))

    col_ts = _col(df, "Date & Time", "Date", "timestamp", "time")
    col_member = _col(df, "Player ID", "member_id", "User ID", "Account ID")
    col_reason = _col(df, "Reason", "Description", "Event")
    col_ref = _col(df, "Reference ID", "Ref ID", "Bet ID", "Ticket")
    col_game = _col(df, "Game Name", "Game")
    col_provider = _col(df, "Game Provider", "Provider")
    col_amount = _amount_column(df)
    col_payment = _col(df, "Payment Method", "Method")
    col_details = _col(df, "Details", "Note")
    col_currency = _currency_column(df)
    col_balance = _col(df, "Balance", "Base Balance", "System Balance")

    missing = [("Date & Time", col_ts), ("Player ID", col_member), ("Reason", col_reason)]
    missing = [name for name, v in missing if not v]
    if missing:
        raise HTTPException(status_code=422, detail=f"Eksik kolon(lar): {', '.join(missing)}")

    # Tip dönüşümleri
    df[col_ts] = _to_dt(df[col_ts])
    df[col_amount] = pd.to_numeric(df[col_amount], errors="coerce").fillna(0.0)
    for c in [col_ref, col_game, col_provider, col_payment, col_details, col_currency]:
        if c: df[c] = df[c].astype(str)

    df["__reason_type"] = df[col_reason].apply(_norm_reason)
    df = df.sort_values(col_ts).reset_index(drop=True)

    # MEMBER filtresi
    if member_id:
        df = df[df[col_member].astype(str) == str(member_id)].reset_index(drop=True)

    # Cycle sınırlarını üret
    dep_idx = df.index[df["__reason_type"] == "DEPOSIT"].tolist()
    if not dep_idx:
        raise HTTPException(status_code=422, detail="Bu dosyada DEPOSIT bulunamadı; cycle için yatırım gerekli.")

    cycles_bounds: List[Tuple[int, int]] = []
    for i, s_idx in enumerate(dep_idx):
        e_idx = dep_idx[i + 1] if i + 1 < len(dep_idx) else len(df)
        cycles_bounds.append((int(s_idx), int(e_idx)))

    # cycle_index yoksa: en son yatırımı al
    if cycle_index is None:
        cycle_index = len(cycles_bounds) - 1
    if cycle_index < 0 or cycle_index >= len(cycles_bounds):
        raise HTTPException(status_code=400, detail=f"Geçersiz cycle_index: {cycle_index}")

    start_idx, end_idx = cycles_bounds[cycle_index]
    cycle = df.iloc[start_idx:end_idx].copy()

    # Başlangıç satırı (deposit)
    dep_row = df.iloc[start_idx]
    cycle_start_at = _format_t(dep_row[col_ts])
    cycle_end_at = _format_t(df.iloc[end_idx - 1][col_ts]) if end_idx - 1 >= start_idx else None
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

    # Çevrim ve kâr
    total_wager = float(cycle.loc[placed_mask, col_amount].abs().sum())
    total_profit = float(cycle.loc[settled_mask, col_amount].sum() + cycle.loc[placed_mask, col_amount].sum())

    requirement = float(deposit_amount)
    remaining = float(max(requirement - total_wager, 0.0))

    # Unsettled (cycle)
    unsettled_ids: List[str] = []
    unsettled_amount = 0.0
    if col_ref:
        placed_rids_c = set(cycle.loc[placed_mask & cycle[col_ref].notna(), col_ref].astype(str))
        settled_rids_c = set(cycle.loc[settled_mask & cycle[col_ref].notna(), col_ref].astype(str))
        diff_c = sorted(list(placed_rids_c - settled_rids_c))
        unsettled_ids = diff_c
        if diff_c:
            unsettled_amount = float(cycle.loc[placed_mask & cycle[col_ref].isin(diff_c), col_amount].abs().sum())

    # Global unsettled (dosyanın tamamında)
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

    # Pre-deposit unsettled (deposit'tan önceki açıklar, bilgi amaçlı)
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

    # Bonus çevrimi & kâr (deposit'ten sonra bonus verilmişse)
    bonus_wager = None
    bonus_profit = None
    if bonus_name is not None:
        # bonus verildiği andan cycle sonuna kadar
        idx_bonus = sub_after.index[sub_after["__reason_type"] == "BONUS_GIVEN"]
        if len(idx_bonus):
            b0 = int(idx_bonus[0]) - start_idx  # cycle içi relative index
            sub_b = cycle.iloc[b0:]
            pm_b = sub_b["__reason_type"] == "BET_PLACED"
            sm_b = sub_b["__reason_type"] == "BET_SETTLED"
            bonus_wager = float(sub_b.loc[pm_b, col_amount].abs().sum())
            bonus_profit = float(sub_b.loc[sm_b, col_amount].sum() + sub_b.loc[pm_b, col_amount].sum())

    # LATE tespit: missing placed + gap>threshold
    late_missing_placed_refs: List[str] = []
    late_gap_details: List[LateItem] = []
    late_gap_total = 0.0

    placed_map, settled_map = _pair_placed_settled(cycle, col_ref, col_ts)
    # reference id yoksa "geç" analizi id'siz satırlara uygulanmaz
    if col_ref:
        for rid, s_idxs in settled_map.items():
            p_idxs = placed_map.get(rid, [])
            # pairing by order
            max_pairs = max(len(p_idxs), len(s_idxs))
            for k in range(max_pairs):
                p_i = p_idxs[k] if k < len(p_idxs) else None
                s_i = s_idxs[k] if k < len(s_idxs) else None
                if p_i is None and s_i is not None:
                    # settled var, placed yok
                    late_missing_placed_refs.append(rid)
                elif p_i is not None and s_i is not None:
                    # gap ölç
                    p_ts = cycle.iloc[p_i][col_ts]
                    s_ts = cycle.iloc[s_i][col_ts]
                    if p_ts is not None and s_ts is not None:
                        gap_min = (s_ts - p_ts).total_seconds() / 60.0
                        if gap_min > float(threshold_minutes):
                            late_gap_details.append(LateItem(
                                reference_id=rid,
                                placed_ts=_format_t(p_ts),
                                settled_ts=_format_t(s_ts),
                                gap_minutes=round(float(gap_min), 2),
                                reason="gap_over_threshold"
                            ))
                            late_gap_total += gap_min
                # if p_i not None and s_i None durumunu "open" zaten üstte ele aldık

    # Kârlı top 3 (pozitif net)
    top_games: List[TopItem] = []
    top_providers: List[TopItem] = []
    if col_game:
        gp = cycle.groupby(col_game)[col_amount].apply(
            lambda s: float(
                s[cycle.loc[s.index, "__reason_type"] == "BET_SETTLED"].sum() +
                s[cycle.loc[s.index, "__reason_type"] == "BET_PLACED"].sum()
            )
        )
        gp = gp[gp > 0].sort_values(ascending=False).head(3)
        top_games = [TopItem(name=str(k), value=round(float(v), 2)) for k, v in gp.items()]
    if col_provider:
        pp = cycle.groupby(col_provider)[col_amount].apply(
            lambda s: float(
                s[cycle.loc[s.index, "__reason_type"] == "BET_SETTLED"].sum() +
                s[cycle.loc[s.index, "__reason_type"] == "BET_PLACED"].sum()
            )
        )
        pp = pp[pp > 0].sort_values(ascending=False).head(3)
        top_providers = [TopItem(name=str(k), value=round(float(v), 2)) for k, v in pp.items()]

    # Para birimi (varsa)
    currency = (str(cycle[col_currency].iloc[0]) if col_currency and not cycle[col_currency].empty else None)

    # Rapor (tek üye bağlamı — cycle deposit satırı kime aitse oradan alınıyor)
    member_val = str(dep_row[col_member])

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

        unsettled_count=len(unsettled_ids),
        unsettled_amount=round(float(unsettled_amount), 2),
        unsettled_reference_ids=unsettled_ids[:50],

        global_unsettled_count=int(global_unsettled_count),
        global_unsettled_amount=round(float(global_unsettled_amount), 2),

        late_missing_placed_count=len(late_missing_placed_refs),
        late_missing_placed_refs=late_missing_placed_refs[:50],
        late_gap_count=len(late_gap_details),
        late_gap_total_gap_minutes=round(float(late_gap_total), 2),
        late_gap_details=late_gap_details[:50],

        pre_deposit_unsettled_count=int(pre_dep_unset_count),
        pre_deposit_unsettled_amount=round(float(pre_dep_unset_amount), 2),

        bonus_name=bonus_name,
        bonus_amount=(round(float(bonus_amount), 2) if bonus_amount is not None else None),
        bonus_wager=(round(float(bonus_wager), 2) if bonus_wager is not None else None),
        bonus_profit=(round(float(bonus_profit), 2) if bonus_profit is not None else None),

        top_games=top_games,
        top_providers=top_providers,
        currency=currency
    )

    return ComputeResult(
        filename=file.filename,
        total_rows=total_rows,
        reports=[report]
    )
