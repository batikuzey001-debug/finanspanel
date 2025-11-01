def build_key(df, idx: int, c_ref: str | None, c_cid: str | None) -> str:
    # Öncelik: Reference ID → BetCID → fallback (satır index)
    if c_ref:
        v = str(df.iloc[idx][c_ref]).strip()
        if v and v.lower() not in ("nan","none"): return f"R:{v}"
    if c_cid:
        v = str(df.iloc[idx][c_cid]).strip()
        if v and v.lower() not in ("nan","none"): return f"C:{v}"
    return f"F:{idx}"
