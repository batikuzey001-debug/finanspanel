from typing import Tuple
from app.services.parse import norm_reason, payment_str

def assign_source(cyc, idx: int, c_pm: str | None, c_dt: str | None, c_rs: str, fallback: bool=False) -> Tuple[str, str | None]:
    """
    Placed varsa placed anından, yoksa (fallback=True) settled anından geriye yürüyerek
    ilk finansal olaya göre kaynak tayini yapar.
      - DEPOSIT   => MAIN  (detay: payment/details)
      - BONUS_GIVEN => BONUS (detay: bonus adı/kodu)
      - ADJUSTMENT  => ADJUSTMENT (detay: payment/details)
    """
    j = idx
    first = cyc.index[0]
    while j >= first:
        reason = str(cyc.loc[j, "__r"] if "__r" in cyc.columns else norm_reason(cyc.loc[j, c_rs]))
        if reason in ("DEPOSIT", "BONUS_GIVEN", "ADJUSTMENT"):
            if reason == "DEPOSIT":
                return "MAIN", payment_str(cyc.loc[j], c_pm, c_dt)
            elif reason == "BONUS_GIVEN":
                det = str(cyc.loc[j, c_dt] or cyc.loc[j, c_rs] or "Bonus") if c_dt else str(cyc.loc[j, c_rs] or "Bonus")
                return "BONUS", (det.strip() or "Bonus")
            else:
                return "ADJUSTMENT", payment_str(cyc.loc[j], c_pm, c_dt)
        j -= 1
    return "MAIN", None
