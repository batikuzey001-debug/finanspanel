def build_key(df, idx: int, c_ref: str | None, c_cid: str | None) -> str:
    """
    df: cycle DataFrame
    idx: satırın LABEL index'i (df.index değeridir) -> loc kullanılmalı.
    Öncelik: Reference ID -> BetCID -> fallback (benzersiz label)
    """
    try:
        row = df.loc[idx]  # <-- iloc değil, loc kullan
    except Exception:
        # Etikete erişilemezse (çok nadir), fallback
        return f"F:{idx}"

    if c_ref:
        v = str(row.get(c_ref, "")).strip()
        if v and v.lower() not in ("nan", "none"):
            return f"R:{v}"

    if c_cid:
        v = str(row.get(c_cid, "")).strip()
        if v and v.lower() not in ("nan", "none"):
            return f"C:{v}"

    # Fallback: benzersiz label kullan
    return f"F:{idx}"
