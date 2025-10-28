from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from io import BytesIO
from typing import Optional, List, Dict, Any
import re

router = APIRouter()

# ---------- MODELLER ----------

class UploadSummary(BaseModel):
    filename: str
    sheet_names: List[str]
    first_sheet: Optional[str]
    columns: List[str]
    row_count_sampled: int
    row_count_exact: Optional[int] = None  # v0.2: tam satır

class ComputeParams(BaseModel):
    # tarih filtresi opsiyonel; varsa bu aralıkta hesaplarız
    date_from: Optional[str] = None  # ISO veya 'dd.MM.yyyy'
    date_to: Optional[str] = None
    # product ağırlıkları ileride eklenecek; şimdilik tüm "placed" satırlarını %100 sayıyoruz

class MemberSummary(BaseModel):
    member_id: str
    total_rows: int
    total_wager: float              # Toplam çevrim (placed toplamı; mutlak değer)
    unsettled_count: int            # placed olup settled olmayan referans sayısı
    unsettled_reference_ids: List[str]
    last_operation: Optional[Dict[str, Any]]  # {"type": "DEPOSIT|BONUS|OTHER", "amount": float, "ts": "..."}
    top_game: Optional[Dict[str, Any]]        # {"game_name": str, "wager": float}
    currency: Optional[str] = None

class ComputeResult(BaseModel):
    filename: str
    total_rows: int
    members: List[MemberSummary]


# ---------- YARDIMCI ----------

def _read_dataframe(file: UploadFile):
    """Excel/CSV okur, ilk sheet'i döner, Pandas'ı lazy import eder."""
    try:
        import pandas as pd  # type: ignore
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pandas yüklenemedi: {e}")

    name = (file.filename or "").lower()
    content = file.file.read() if hasattr(file, "file") else None
    if content is None:
        content = getattr(file, "spooled", None) or (await file.read())  # type: ignore
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

    # Kolon adlarını normalize
    df.columns = [str(c).strip() for c in df.columns]
    return df, sheet_names, (sheet_names[0] if sheet_names else None)


def _col(df, *cands: str) -> Optional[str]:
    """Verilen aday kolonlardan ilk bulunanı döner (case-insens)."""
    cols_lower = {c.lower(): c for c in df.columns}
    for c in cands:
        key = c.lower()
        if key in cols_lower:
            return cols_lower[key]
    # gevşek eşleşme
    for c in df.columns:
        for cand in cands:
            if c.lower().replace(" ", "") == cand.lower().replace(" ", ""):
                return c
    return None


def _to_datetime(series):
    import pandas as pd  # type: ignore
    return pd.to_datetime(series, errors="coerce", dayfirst=True)  #  dd.MM.yyyy de destekler


def _is_reason(val: str, needle: str) -> bool:
    """Reason alanında 'bet placed', 'bet settled', 'deposit', 'bonus' gibi sinyalleri esnek yakala."""
    if not isinstance(val, str):
        return False
    v = val.strip().lower()
    n = needle.lower()
    if n == "placed":
        return ("placed" in v) or ("bet place" in v) or ("stake" in v)
    if n == "settled":
        return ("settled" in v) or ("result" in v) or ("payout" in v)
    if n == "deposit":
        return ("deposit" in v) or ("yatırım" in v) or ("yatir" in v)
    if n == "bonus":
        return ("bonus" in v) or ("prom" in v)
    return n in v


# ---------- ENDPOINTLER ----------

@router.post("", response_model=UploadSummary)
async def upload_file(file: UploadFile = File(...)):
    # Sadece özet (v0.1 + satır tam sayısı)
    df, sheet_names, first_sheet = _read_dataframe(file)
    cols = [str(c) for c in df.columns]
    return UploadSummary(
        filename=file.filename,
        sheet_names=sheet_names,
        first_sheet=first_sheet,
        columns=cols,
        row_count_sampled=min(len(df), 5000),
        row_count_exact=int(len(df)),
    )


@router.post("/compute", response_model=ComputeResult)
async def compute(file: UploadFile = File(...), params: ComputeParams = File(None)):
    """
    v0.2: Çevrim ön-izleme.
    - Toplam satır (tam)
    - Member bazlı: toplam çevrim (placed toplamı), unsettled referanslar (placed olup settled olmayan),
      son işlem (deposit/bonus/other), en çok çevrim yapılan oyun.
    """
    import pandas as pd  # type: ignore
    import numpy as np   # type: ignore

    df, _, _ = _read_dataframe(file)
    total_rows = int(len(df))

    # Kolon eşleştirme (dosyana göre otomatik):
    col_ts = _col(df, "Date & Time", "Date", "timestamp", "time")
    col_member = _col(df, "Player ID", "member_id", "User ID", "Account ID")
    col_reason = _col(df, "Reason", "Description", "Event")
    col_bet_type = _col(df, "Bet Type", "Product")
    col_game = _col(df, "Game Name", "Game")
    col_ref = _col(df, "Reference ID", "Ref ID", "Bet ID", "Ticket")
    col_amount = _col(df, "Amount", "Base Amount", "Bet Amount", "Stake")

    if not all([col_ts, col_member, col_reason, col_amount]):
        missing = [("Date & Time", col_ts), ("Player ID", col_member), ("Reason", col_reason), ("Amount", col_amount)]
        missing = [name for name, val in missing if not val]
        raise HTTPException(status_code=422, detail=f"Eksik kolon(lar): {', '.join(missing)}")

    # Tip dönüşümleri
    df[col_ts] = _to_datetime(df[col_ts])
    df[col_amount] = pd.to_numeric(df[col_amount], errors="coerce").fillna(0.0)

    # Tarih filtresi opsiyonel
    if params and (params.date_from or params.date_to):
        dfrom = pd.to_datetime(params.date_from, errors="coerce", dayfirst=True) if params.date_from else None
        dto = pd.to_datetime(params.date_to, errors="coerce", dayfirst=True) if params.date_to else None
        if dfrom is not None:
            df = df[df[col_ts] >= dfrom]
        if dto is not None:
            df = df[df[col_ts] <= dto]

    # Esnek sinyaller
    def is_placed(s: pd.Series) -> pd.Series:
        return s.astype(str).str.lower().apply(lambda x: _is_reason(x, "placed"))

    def is_settled(s: pd.Series) -> pd.Series:
        return s.astype(str).str.lower().apply(lambda x: _is_reason(x, "settled"))

    def is_deposit(s: pd.Series) -> pd.Series:
        return s.astype(str).str.lower().apply(lambda x: _is_reason(x, "deposit"))

    def is_bonus(s: pd.Series) -> pd.Series:
        return s.astype(str).str.lower().apply(lambda x: _is_reason(x, "bonus"))

    # ÇEVRİM: tüm "placed" satırlarının mutlak tutar toplamı (ürün ağırlıkları v0.3'te)
    placed_mask = is_placed(df[col_reason])
    df["__wager"] = np.abs(df.loc[placed_mask, col_amount]).fillna(0.0)
    df["__wager"] = df["__wager"].fillna(0.0)

    # UNSETTLED: Reference ID bazlı kontrol (placed = var & settled = yok)
    unsettled_rids: List[str] = []
    if col_ref:
        placed_rids = set(df.loc[placed_mask & df[col_ref].notna(), col_ref].astype(str))
        settled_rids = set(df.loc[is_settled(df[col_reason]) & df[col_ref].notna(), col_ref].astype(str))
        unsettled_rids = sorted(list(placed_rids - settled_rids))

    # SON İŞLEM (yatırım/bonus/other): en yakın (son) satır
    df["__is_deposit"] = is_deposit(df[col_reason])
    df["__is_bonus"]   = is_bonus(df[col_reason])

    # En çok çevrim yapılan oyun (game name'e göre)
    if col_game:
        game_wagers = df.groupby(col_game)["__wager"].sum().sort_values(ascending=False)
        global_top_game = game_wagers.index[0] if not game_wagers.empty else None
    else:
        global_top_game = None

    # Member bazlı derleme
    results: List[MemberSummary] = []
    for member_id, g in df.groupby(col_member):
        total_rows_member = int(len(g))
        total_wager_member = float(g["__wager"].sum())

        # member bazlı unsettled
        member_unsettled: List[str] = []
        if col_ref:
            rids_p = set(g.loc[placed_mask.reindex(g.index, fill_value=False) & g[col_ref].notna(), col_ref].astype(str))
            rids_s = set(g.loc[is_settled(g[col_reason]) & g[col_ref].notna(), col_ref].astype(str))
            member_unsettled = sorted(list(rids_p - rids_s))

        # Son işlem
        g_sorted = g.sort_values(col_ts, ascending=False)
        last_op = None
        for _, row in g_sorted.iterrows():
            if row["__is_deposit"]:
                last_op = {"type": "DEPOSIT", "amount": float(row[col_amount]), "ts": str(row[col_ts])}
                break
            if row["__is_bonus"]:
                last_op = {"type": "BONUS", "amount": float(row[col_amount]), "ts": str(row[col_ts])}
                break
        if last_op is None and not g_sorted.empty:
            r0 = g_sorted.iloc[0]
            last_op = {"type": "OTHER", "amount": float(r0[col_amount]), "ts": str(r0[col_ts])}

        # En çok çevrim yaptığı oyun (bu üyede)
        top_game = None
        if col_game:
            mg = g.groupby(col_game)["__wager"].sum().sort_values(ascending=False)
            if not mg.empty:
                top_game = {"game_name": str(mg.index[0]), "wager": float(mg.iloc[0])}

        # Para birimi (varsa)
        col_curr = _col(g, "Currency", "Base Currency", "System Currency")
        currency = str(g[col_curr].iloc[0]) if col_curr and not g[col_curr].empty else None

        results.append(MemberSummary(
            member_id=str(member_id),
            total_rows=total_rows_member,
            total_wager=round(total_wager_member, 2),
            unsettled_count=len(member_unsettled),
            unsettled_reference_ids=member_unsettled[:50],  # çok uzamasın
            last_operation=last_op,
            top_game=top_game,
            currency=currency
        ))

    # Çıkış
    return ComputeResult(
        filename=file.filename,
        total_rows=total_rows,
        members=sorted(results, key=lambda x: (-x.total_wager, x.member_id)),
    )
