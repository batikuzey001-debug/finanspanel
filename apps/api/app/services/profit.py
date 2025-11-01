from typing import Tuple
from app.services.parse import norm_reason, payment_str

def assign_source(
    cyc,
    idx: int,
    c_pm: str | None,
    c_dt: str | None,
    c_rs: str,
    c_am: str | None,
    fallback: bool = False,
) -> Tuple[str, str | None]:
    """
    En yakın finansal olayı geriye doğru bul:
      - DEPOSIT         -> MAIN
      - BONUS_GIVEN     -> BONUS   (FREE_SPIN_GIVEN zaten BONUS_GIVEN’a normalize edildi)
      - ADJUSTMENT amt>0-> ADJUSTMENT (amt<=0 ise atla)
    Yoksa MAIN döner.
    """
    j = idx
    first = cyc.index[0]
    while j >= first:
        r = str(cyc.loc[j, "__r"] if "__r" in cyc.columns else norm_reason(cyc.loc[j, c_rs]))
        if r in ("DEPOSIT", "BONUS_GIVEN", "ADJUSTMENT"):
            if r == "DEPOSIT":
                return "MAIN", payment_str(cyc.loc[j], c_pm, c_dt)
            if r == "BONUS_GIVEN":
                det = str(cyc.loc[j, c_dt] or cyc.loc[j, c_rs] or "Bonus") if c_dt else str(cyc.loc[j, c_rs] or "Bonus")
                return "BONUS", (det.strip() or "Bonus")
            if r == "ADJUSTMENT":
                amt = float(cyc.loc[j, c_am]) if c_am is not None else 0.0
                if amt > 0:
                    return "ADJUSTMENT", payment_str(cyc.loc[j], c_pm, c_dt)
        j -= 1
    return "MAIN", None
