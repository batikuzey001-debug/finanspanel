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
    Kaynak tayini:
      - Geriye doğru ilk finansal olayı bul.
      - DEPOSIT      -> MAIN      (detay: payment/details)
      - BONUS_GIVEN  -> BONUS     (detay: bonus adı/kodu - Details/Reason)
      - ADJUSTMENT   -> ADJUSTMENT *sadece tutar > 0 ise*; tutar <= 0 ise atla (negatif manuel düşüm).
    Eğer hiçbir finansal olay yoksa MAIN döner.
    """
    j = idx
    first = cyc.index[0]
    while j >= first:
        reason = str(cyc.loc[j, "__r"] if "__r" in cyc.columns else norm_reason(cyc.loc[j, c_rs]))
        if reason in ("DEPOSIT", "BONUS_GIVEN", "ADJUSTMENT"):
            if reason == "DEPOSIT":
                return "MAIN", payment_str(cyc.loc[j], c_pm, c_dt)
            if reason == "BONUS_GIVEN":
                det = str(cyc.loc[j, c_dt] or cyc.loc[j, c_rs] or "Bonus") if c_dt else str(cyc.loc[j, c_rs] or "Bonus")
                return "BONUS", (det.strip() or "Bonus")
            # ADJUSTMENT: negatifse kaynak sayma, bir önceki olaya bak
            if reason == "ADJUSTMENT":
                if c_am is not None:
                    try:
                        amt = float(cyc.loc[j, c_am])
                    except Exception:
                        amt = 0.0
                else:
                    amt = 0.0
                if amt > 0:
                    return "ADJUSTMENT", payment_str(cyc.loc[j], c_pm, c_dt)
                # negatif/0 ise bu olayı atla
        j -= 1
    return "MAIN", None
