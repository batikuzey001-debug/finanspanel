from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from pydantic import BaseModel
from io import BytesIO
from typing import Optional, List, Dict, Any, Tuple

router = APIRouter()

# -------------------- MODELLER --------------------

class UploadSummary(BaseModel):
    filename: str
    sheet_names: List[str]
    first_sheet: Optional[str]
    columns: List[str]
    row_count_sampled: int
    row_count_exact: Optional[int] = None

class TopItem(BaseModel):
    name: str
    value: float

class MemberCycleReport(BaseModel):
    member_id: str

    # Son işlem bilgileri
    last_operation_type: str                       # "DEPOSIT" | "BONUS" | "OTHER" | "NONE"
    last_operation_ts: Optional[str]
    last_deposit_amount: Optional[float] = None
    last_bonus_name: Optional[str] = None
    last_bonus_amount: Optional[float] = None
    last_payment_method: Optional[str] = None

    # Çevrim ve gereksinim
    total_wager: float                             # cycle içindeki |BET_PLACED| toplamı
    total_profit: float                            # sum(SETTLED) + sum(PLACED)  (cycle)
    requirement: float                             # yatırımsa 1x deposit, değilse 0
    remaining: float                               # max(requirement - total_wager, 0)

    # Bonus özel alanlar
    bonus_wager: Optional[float] = None            # son bonusla yapılan toplam çevrim (bonus başlangıçlıysa)
    bonus_profit: Optional[float] = None           # bonus satırları içindeki kâr
    bonus_to_main_amount: Optional[float] = None   # YENİ: casino_bonus_achieved toplamı (bonus→ana para)

    # Unsettled (cycle) + GLOBAL
    unsettled_count: int
    unsettled_amount: float
    unsettled_reference_ids: List[str]
    global_unsettled_count: int
    global_unsettled_amount: float

    # DEPOSIT özel alanlar
    pre_deposit_unsettled_count: Optional[int] = None   # YENİ: sadece depozitten önceki açık bahis adedi
    pre_deposit_unsettled_amount: Optional[float] = None# YENİ: sadece depozitten önceki açık bahis tutarı
    balance_at_deposit: Optional[float] = None          # YENİ: yatırım satırındaki bakiye (Balance/Base/System)

    # Kârlı ilk 3 oyun/sağlayıcı
    top_games: List[TopItem]
    top_providers: List[TopItem]
    currency: Optional[str] = None

class ComputeResult(BaseModel):
    filename: str
    total_rows: int
    reports: List[MemberCycleReport]

# -------------------- YARDIMCI --------------------

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
    if s in {"bonus_given", "bonus given"}: return "BONUS"
    if s in {"casino_bonus_achieved", "casino bonus achieved"}: return "BONUS_ACHIEVED"
    if "placed" in s or "stake" in s or "wager" in s: return "BET_PLACED"
    if "settled" in s or "payout" in s or "result" in s: return "BET_SETTLED"
    if "withdrawal" in s: return "WITHDRAWAL"
    if "bonus" in s and "achiev" in s: return "BONUS_ACHIEVED"
    if "bonus" in s or "promo" in s: return "BONUS"
    return s.upper()

def _cycle_bounds(df, from_idx: int) -> Tuple[int, int]:
    """
    from_idx dahil; bir sonraki DEPOSIT/BONUS gelene kadar devam.
    Dönen: (start_idx, end_exclusive_idx)
    """
    types = df["__reason_type"].values
    start = from_idx
    end = len(df)
    for i in range(from_idx + 1, len(df)):
        if types[i] in ("DEPOSIT", "BONUS"):
            end = i
            break
    return start, end

# -------------------- ENDPOINTLER --------------------

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

@router.post("/compute", response_model=ComputeResult)
async def compute(
    file: UploadFile = File(...),
    date_from: Optional[str] = Form(None),
    date_to: Optional[str] = Form(None),
):
    """
    Son yatırım/bonus bazlı 'cycle' tespiti ve rapor:
      - DEPOSIT ise: requirement = deposit_amount (1x), remaining hesaplanır. 
        + Sadece DEPOSIT öncesi UNSETTLED hesaplanır (pre_deposit_*), balance_at_deposit döner.
      - BONUS ise: bonus bilgisi + bonusla yapılan toplam çevrim (bonus_wager) + bonustan ana paraya geçen tutar (BONUS_ACHIEVED toplamı).
      - Placed/Settled eşleşmesi ile cycle UNSETTLED + GLOBAL UNSETTLED.
      - Oyun/sağlayıcı bazında kâr, ilk 3 pozitif kârlı item.
    """
    import pandas as pd  # type: ignore
    import numpy as np   # type: ignore

    df, _, _ = _read_dataframe_sync(file)
    total_rows = int(len(df))

    # Gerekli kolonlar
    col_ts = _col(df, "Date & Time", "Date", "timestamp", "time")
    col_member = _col(df, "Player ID", "member_id", "User ID", "Account ID")
    col_reason = _col(df, "Reason", "Description", "Event")
    col_ref = _col(df, "Reference ID", "Ref ID", "Bet ID", "Ticket")
    col_game = _col(df, "Game Name", "Game")
    col_provider = _col(df, "Game Provider", "Provider")
    col_amount = _col(df, "Amount", "Base Amount", "Bet Amount", "Stake")
    col_payment = _col(df, "Payment Method", "Method")
    col_details = _col(df, "Details", "Note")
    col_currency = _col(df, "Currency", "Base Currency", "System Currency")
    col_balance = _col(df, "Balance", "Base Balance", "System Balance")  # depozitoda bakiyeyi yakalamak için

    missing = [("Date & Time", col_ts), ("Player ID", col_member), ("Reason", col_reason), ("Amount", col_amount)]
    missing = [name for name, v in missing if not v]
    if missing:
        raise HTTPException(status_code=422, detail=f"Eksik kolon(lar): {', '.join(missing)}")

    # Temizlik ve tip dönüşümü
    df[col_ts] = _to_dt(df[col_ts])
    df[col_amount] = pd.to_numeric(df[col_amount], errors="coerce").fillna(0.0)
    for c in [col_ref, col_game, col_provider, col_payment, col_details, col_currency]:
        if c: df[c] = df[c].astype(str)
    if col_balance:
        df[col_balance] = pd.to_numeric(df[col_balance], errors="coerce")

    # Tarih filtresi (opsiyonel)
    if date_from:
        df = df[df[col_ts] >= pd.to_datetime(date_from, errors="coerce", dayfirst=True)]
    if date_to:
        df = df[df[col_ts] <= pd.to_datetime(date_to, errors="coerce", dayfirst=True)]

    # Reason normalizasyonu
    df["__reason_type"] = df[col_reason].apply(_norm_reason)

    # Sırala
    df = df.sort_values(col_ts).reset_index(drop=True)

    # GLOBAL UNSETTLED (tüm dosya geneli, üye bazında)
    global_unsettled_map: Dict[str, Tuple[int, float]] = {}
    if col_ref:
        placed_mask_all = df["__reason_type"] == "BET_PLACED"
        settled_mask_all = df["__reason_type"] == "BET_SETTLED"
        for member_id, g_all in df.groupby(col_member, sort=False):
            placed_rids = set(g_all.loc[placed_mask_all.reindex(g_all.index, fill_value=False) & g_all[col_ref].notna(), col_ref].astype(str))
            settled_rids = set(g_all.loc[settled_mask_all.reindex(g_all.index, fill_value=False) & g_all[col_ref].notna(), col_ref].astype(str))
            diff = placed_rids - settled_rids
            amt = float(np.abs(g_all.loc[placed_mask_all.reindex(g_all.index, fill_value=False) & g_all[col_ref].isin(diff), col_amount]).sum()) if diff else 0.0
            global_unsettled_map[str(member_id)] = (len(diff), round(amt, 2))

    reports: List[MemberCycleReport] = []

    for member_id, g in df.groupby(col_member, sort=False):
        g = g.sort_values(col_ts).reset_index(drop=True)
        # Son DEPOSIT ve SON BONUS index'leri
        deposit_idx = g.index[g["__reason_type"] == "DEPOSIT"].tolist()
        bonus_idx = g.index[g["__reason_type"] == "BONUS"].tolist()

        last_dep_i = deposit_idx[-1] if deposit_idx else None
        last_bonus_i = bonus_idx[-1] if bonus_idx else None

        # Son işlem hangisi?
        last_op_i = None
        last_op_type = "NONE"
        if last_dep_i is not None and (last_bonus_i is None or last_dep_i >= last_bonus_i):
            last_op_i = last_dep_i
            last_op_type = "DEPOSIT"
        elif last_bonus_i is not None:
            last_op_i = last_bonus_i
            last_op_type = "BONUS"

        # Varsayılan alanlar
        last_ts = None
        deposit_amt = None
        bonus_name = None
        bonus_amt = None
        last_pay_method = None
        balance_at_deposit = None

        if last_op_i is None:
            # Hiç yatırım/bonus yok → tüm veri tek açık cycle; requirement 0
            cycle_start, cycle_end = 0, len(g)
        else:
            cycle_start, cycle_end = _cycle_bounds(g, last_op_i)
            last_ts = str(g.loc[last_op_i, col_ts]) if col_ts and (g.loc[last_op_i, col_ts] is not None) else None

            if last_op_type == "DEPOSIT":
                deposit_amt = float(g.loc[last_op_i, col_amount])
                pm = str(g.loc[last_op_i, col_payment]) if col_payment else ""
                dt = str(g.loc[last_op_i, col_details]) if col_details else ""
                last_pay_method = " / ".join([x for x in [pm, dt] if x]).strip() or None
                if col_balance:
                    balance_at_deposit = float(g.loc[last_op_i, col_balance]) if g.loc[last_op_i, col_balance] == g.loc[last_op_i, col_balance] else None
            else:  # BONUS
                bonus_amt = float(g.loc[last_op_i, col_amount])
                rtxt = str(g.loc[last_op_i, col_reason] or "")
                dtxt = str(g.loc[last_op_i, col_details] or "") if col_details else ""
                bonus_name = (dtxt or rtxt).strip() or "Bonus"

        cycle = g.iloc[cycle_start:cycle_end].copy()

        # Mask'ler
        placed_mask = cycle["__reason_type"] == "BET_PLACED"
        settled_mask = cycle["__reason_type"] == "BET_SETTLED"

        # Çevrim (mutlak placed toplamı) ve profit
        total_wager = float((cycle.loc[placed_mask, col_amount].abs()).sum())
        total_profit = float(cycle.loc[settled_mask, col_amount].sum() + cycle.loc[placed_mask, col_amount].sum())

        # Requirement/Remaining
        requirement = float(deposit_amt) if (last_op_type == "DEPOSIT" and deposit_amt is not None) else 0.0
        remaining = float(max(requirement - total_wager, 0.0))

        # Cycle UNSETTLED
        unsettled_ids: List[str] = []
        unsettled_amount = 0.0
        if col_ref:
            placed_rids_c = set(cycle.loc[placed_mask & cycle[col_ref].notna(), col_ref].astype(str))
            settled_rids_c = set(cycle.loc[settled_mask & cycle[col_ref].notna(), col_ref].astype(str))
            diff_c = sorted(list(placed_rids_c - settled_rids_c))
            unsettled_ids = diff_c
            if diff_c:
                unsettled_amount = float(cycle.loc[placed_mask & cycle[col_ref].isin(diff_c), col_amount].abs().sum())

        # GLOBAL UNSETTLED (önceden hazırlandı)
        gu_count, gu_amount = global_unsettled_map.get(str(member_id), (0, 0.0))

        # DEPOSIT ise: yalnızca DEPOSIT ÖNCESİ UNSETTLED hesapla (isteğine uygun)
        pre_dep_count = None
        pre_dep_amount = None
        if last_op_type == "DEPOSIT" and last_op_i is not None and col_ref:
            pre = g.iloc[:last_op_i]  # depozitodan ÖNCEKİ satırlar
            placed_pre = pre[pre["__reason_type"] == "BET_PLACED"]
            settled_pre = pre[pre["__reason_type"] == "BET_SETTLED"]
            if not placed_pre.empty:
                placed_r = set(placed_pre.loc[placed_pre[col_ref].notna(), col_ref].astype(str))
                settled_r = set(settled_pre.loc[settled_pre[col_ref].notna(), col_ref].astype(str))
                diff_pre = placed_r - settled_r
                pre_dep_count = int(len(diff_pre))
                pre_dep_amount = float(placed_pre.loc[placed_pre[col_ref].isin(diff_pre), col_amount].abs().sum()) if diff_pre else 0.0

        # BONUS ise: bonustan ana paraya geçen tutar (BONUS_ACHIEVED)
        bonus_to_main_amount = None
        if last_op_type == "BONUS":
            ach = cycle[cycle["__reason_type"] == "BONUS_ACHIEVED"]
            if not ach.empty:
                bonus_to_main_amount = float(ach[col_amount].sum())

        # Oyun/sağlayıcı bazında kâr (ilk 3 pozitif)
        top_games: List[TopItem] = []
        top_providers: List[TopItem] = []
        if col_game:
            gp = cycle.groupby(col_game)[col_amount].apply(
                lambda s: float(
                    s[cycle.loc[s.index, "__reason_type"] == "BET_SETTLED"].sum()
                    + s[cycle.loc[s.index, "__reason_type"] == "BET_PLACED"].sum()
                )
            )
            gp = gp[gp > 0].sort_values(ascending=False).head(3)
            top_games = [TopItem(name=str(k), value=round(float(v), 2)) for k, v in gp.items()]
        if col_provider:
            pp = cycle.groupby(col_provider)[col_amount].apply(
                lambda s: float(
                    s[cycle.loc[s.index, "__reason_type"] == "BET_SETTLED"].sum()
                    + s[cycle.loc[s.index, "__reason_type"] == "BET_PLACED"].sum()
                )
            )
            pp = pp[pp > 0].sort_values(ascending=False).head(3)
            top_providers = [TopItem(name=str(k), value=round(float(v), 2)) for k, v in pp.items()]

        # Para birimi (varsa)
        currency = (str(cycle[col_currency].iloc[0]) if col_currency and not cycle[col_currency].empty else None)

        reports.append(MemberCycleReport(
            member_id=str(member_id),
            last_operation_type=last_op_type,
            last_operation_ts=last_ts,
            last_deposit_amount=(float(deposit_amt) if deposit_amt is not None else None),
            last_bonus_name=(str(bonus_name) if bonus_name else None),
            last_bonus_amount=(float(bonus_amt) if bonus_amt is not None else None),
            last_payment_method=last_pay_method,

            total_wager=round(total_wager, 2),
            total_profit=round(total_profit, 2),
            requirement=round(requirement, 2),
            remaining=round(remaining, 2),

            bonus_wager=(round(float(total_wager), 2) if (last_op_type == "BONUS") else None),
            bonus_profit=(round(float(total_profit), 2) if (last_op_type == "BONUS") else None),
            bonus_to_main_amount=(round(float(bonus_to_main_amount), 2) if bonus_to_main_amount is not None else None),

            unsettled_count=len(unsettled_ids),
            unsettled_amount=round(float(unsettled_amount), 2),
            unsettled_reference_ids=unsettled_ids[:50],

            global_unsettled_count=int(gu_count),
            global_unsettled_amount=float(gu_amount),

            pre_deposit_unsettled_count=(int(pre_dep_count) if pre_dep_count is not None else None),
            pre_deposit_unsettled_amount=(round(float(pre_dep_amount), 2) if pre_dep_amount is not None else None),
            balance_at_deposit=(round(float(balance_at_deposit), 2) if balance_at_deposit is not None else None),

            top_games=top_games,
            top_providers=top_providers,
            currency=currency
        ))

    # Çıkış
    return ComputeResult(
        filename=file.filename,
        total_rows=total_rows,
        reports=sorted(reports, key=lambda r: (-r.total_wager, r.member_id))
    )
