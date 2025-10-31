import React, { useState } from "react";
import Dropzone from "../components/Dropzone";

const tl = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY", maximumFractionDigits: 2 });
const fmt = (n?: number | null) => (typeof n === "number" ? tl.format(n) : "-");

const card: React.CSSProperties = { border: "1px solid #1f2937", borderRadius: 16, padding: 14, marginBottom: 14, background: "#151a23", boxShadow: "0 1px 8px rgba(0,0,0,0.25)" };
const box: React.CSSProperties  = { padding: 12, border: "1px solid #1f2937", borderRadius: 12, background: "#0f1520" };
const cap: React.CSSProperties  = { fontSize: 12, color: "#94a3b8", marginBottom: 4 };
const btnPrimary: React.CSSProperties = { marginTop: 16, padding: "11px 16px", borderRadius: 12, border: "1px solid #1f2937", cursor: "pointer", background: "linear-gradient(135deg, #0ea5e9, #6366f1)", color: "#fff", fontWeight: 700, letterSpacing: 0.3 };
const tiny: React.CSSProperties = { fontSize: 12, color: "#94a3b8" };
const selectStyle: React.CSSProperties = { width: "100%", padding: "10px 12px", borderRadius: 12, border: "1px solid #1f2937", background: "#0f1520", color: "#e5e7eb" };

const API = (import.meta.env.VITE_API_BASE_URL as string) || "http://localhost:8000";

/* --- Tipler --- */
type Summary = { filename: string; sheet_names: string[]; first_sheet: string | null; columns: string[]; row_count_sampled: number; row_count_exact?: number; };

type TopItem = { name: string; value: number };
type LateItem = { reference_id: string; placed_ts?: string | null; settled_ts?: string | null; gap_minutes?: number | null; reason: string };

type Report = {
  member_id: string;
  cycle_index?: number;
  cycle_start_at?: string | null;
  cycle_end_at?: string | null;
  last_operation_type: string;
  last_operation_ts: string | null;
  last_deposit_amount?: number | null;
  last_payment_method?: string | null;

  sum_adjustment: number;
  sum_withdrawal_approved: number;
  sum_withdrawal_declined: number;
  bonus_to_main_amount: number;

  total_wager: number;
  total_profit: number;
  requirement: number;
  remaining: number;

  unsettled_count: number;
  unsettled_amount: number;
  unsettled_reference_ids: string[];
  global_unsettled_count: number;
  global_unsettled_amount: number;

  late_missing_placed_count?: number;
  late_missing_placed_refs?: string[];
  late_gap_count?: number;
  late_gap_total_gap_minutes?: number;
  late_gap_details?: LateItem[];

  pre_deposit_unsettled_count?: number | null;
  pre_deposit_unsettled_amount?: number | null;

  bonus_name?: string | null;
  bonus_amount?: number | null;
  bonus_wager?: number | null;
  bonus_profit?: number | null;

  top_games: TopItem[];
  top_providers: TopItem[];
  currency?: string | null;
};

type ComputeResp = { filename: string; total_rows: number; reports: Report[]; };
type CycleEntry = { index: number; start_row: number; end_row: number; start_at: string; deposit_amount: number; payment_method?: string | null; label: string; };
type CyclesResp = { filename: string; total_rows: number; cycles: CycleEntry[] };

/* --- API yardımcıları --- */
async function uploadFile(file: File) {
  const body = new FormData();
  body.append("file", file);
  const r = await fetch(`${API}/uploads`, { method: "POST", body });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
async function listCycles(file: File): Promise<CyclesResp> {
  const body = new FormData();
  body.append("file", file);
  const r = await fetch(`${API}/uploads/cycles`, { method: "POST", body });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
async function computeCycle(file: File, cycleIndex?: number, thresholdMinutes = 5): Promise<ComputeResp> {
  const body = new FormData();
  body.append("file", file);
  if (typeof cycleIndex === "number") body.append("cycle_index", String(cycleIndex));
  body.append("threshold_minutes", String(thresholdMinutes));
  const r = await fetch(`${API}/uploads/compute`, { method: "POST", body });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

/* --- Bileşen --- */
export default function Upload() {
  const [file, setFile] = useState<File | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [cycles, setCycles] = useState<CycleEntry[] | null>(null);
  const [selectedCycle, setSelectedCycle] = useState<number | null>(null);
  const [res, setRes] = useState<ComputeResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const onFile = async (f: File) => {
    setFile(f); setSummary(null); setCycles(null); setSelectedCycle(null); setRes(null); setErr(null);
    setLoading(true);
    try {
      const s = await uploadFile(f); setSummary(s);
      const cy = await listCycles(f); setCycles(cy.cycles || []);
      if (cy.cycles?.length) setSelectedCycle(cy.cycles[cy.cycles.length - 1].index); // en yeni yatırım
    } catch (e: any) {
      setErr(e?.message || "Yükleme/Cycle hatası");
    } finally {
      setLoading(false);
    }
  };

  const onCompute = async () => {
    if (!file) return;
    setLoading(true); setErr(null); setRes(null);
    try {
      const r = await computeCycle(file, selectedCycle ?? undefined);
      setRes(r);
    } catch (e: any) {
      setErr(e?.message || "Hesaplama hatası");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      {/* Üst grid — Yükleme & Özet / Cycle seçimi */}
      <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 16 }}>
        <div style={card}>
          <Dropzone onFile={onFile} />

          {cycles && cycles.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={{ ...cap, marginBottom: 6 }}>Cycle Seç (Yalnızca Yatırımlar)</div>
              <select
                style={selectStyle}
                value={selectedCycle ?? ""}
                onChange={(e) => setSelectedCycle(e.target.value === "" ? null : Number(e.target.value))}
              >
                {cycles.map((c) => (
                  <option key={c.index} value={c.index}>
                    {c.label}
                  </option>
                ))}
              </select>
            </div>
          )}

          <button onClick={onCompute} style={btnPrimary} disabled={!file || loading}>
            {loading ? "İşleniyor…" : "Hesapla"}
          </button>

          {err && <p style={{ marginTop: 10, color: "#ef4444" }}>{err}</p>}
        </div>

        {summary && (
          <div style={card}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2,1fr)", gap: 12 }}>
              <div style={box}><div style={cap}>Dosya</div><div>{summary.filename}</div></div>
              <div style={box}><div style={cap}>Sheet</div><div>{summary.first_sheet} ({summary.sheet_names.length})</div></div>
              <div style={box}><div style={cap}>Kolon</div><div>{summary.columns.length}</div></div>
              <div style={box}><div style={cap}>Satır</div><div>{summary.row_count_exact ?? summary.row_count_sampled}</div></div>
            </div>
          </div>
        )}
      </div>

      {/* Sonuç Kartı */}
      {res && (
        <div style={{ marginTop: 16 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
            <div style={{ fontWeight: 800, fontSize: 16 }}>Sonuçlar</div>
            <div style={tiny}>{res.filename} • {res.total_rows} satır</div>
          </div>

          {res.reports.map((r) => (
            <div key={`${r.member_id}-${r.cycle_index ?? "c"}`} style={card}>
              {/* Başlık */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <div style={{ fontWeight: 800, fontSize: 16 }}>
                  Üye: {r.member_id}
                  {typeof r.cycle_index === "number" && (
                    <span style={{ marginLeft: 8, fontSize: 12, color: "#94a3b8" }}>
                      • Cycle # {r.cycle_index} {r.cycle_start_at ? `(${r.cycle_start_at} → ${r.cycle_end_at || "…"})` : ""}
                    </span>
                  )}
                </div>
                <div style={tiny}>{r.last_operation_type}{r.last_operation_ts ? ` • ${r.last_operation_ts}` : ""}</div>
              </div>

              {/* Satır 1: Yatırım / Yöntem / Birim */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12 }}>
                <div style={box}><div style={cap}>Yatırım</div><div>{fmt(r.last_deposit_amount)}</div></div>
                <div style={box}><div style={cap}>Yöntem</div><div style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.last_payment_method || "-"}</div></div>
                <div style={box}><div style={cap}>Birim</div><div>{r.currency || "TRY"}</div></div>
              </div>

              {/* Satır 2: Çevrim / Gereksinim / Kalan / Kâr */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginTop: 8 }}>
                <div style={box}><div style={cap}>Toplam Çevrim</div><div>{fmt(r.total_wager)}</div></div>
                <div style={box}><div style={cap}>Gereksinim (1x)</div><div>{fmt(r.requirement)}</div></div>
                <div style={box}><div style={cap}>Kalan</div><div>{fmt(r.remaining)}</div></div>
                <div style={box}><div style={cap}>Toplam Kâr</div><div style={{ color: r.total_profit >= 0 ? "#34d399" : "#f87171", fontWeight: 800 }}>{fmt(r.total_profit)}</div></div>
              </div>

              {/* Satır 3: Unsettled & Global */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12, marginTop: 8 }}>
                <div style={box}><div style={cap}>Unsettled (Cycle)</div><div>{r.unsettled_count} adet • {fmt(r.unsettled_amount)}</div></div>
                <div style={box}><div style={cap}>Unsettled (Global)</div><div>{r.global_unsettled_count} adet • {fmt(r.global_unsettled_amount)}</div></div>
                <div style={box}><div style={cap}>Bonus → Ana Para</div><div>{fmt(r.bonus_to_main_amount)}</div></div>
              </div>

              {/* Satır 4: LATE uyarıları */}
              {(r.late_missing_placed_count || r.late_gap_count) && (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 8 }}>
                  <div style={box}>
                    <div style={cap}>Geç Sonuçlanan — Eksik PLACED</div>
                    <div style={{ fontSize: 13 }}>
                      {r.late_missing_placed_count ?? 0} adet
                      {r.late_missing_placed_refs && r.late_missing_placed_refs.length > 0 && (
                        <ul style={{ margin: "6px 0 0 16px" }}>
                          {r.late_missing_placed_refs.slice(0, 8).map((id) => <li key={id}>{id}</li>)}
                        </ul>
                      )}
                    </div>
                  </div>
                  <div style={box}>
                    <div style={cap}>{`Geç Sonuçlanan — Süre > 5dk`}</div>
                    <div style={{ fontSize: 13 }}>
                      {r.late_gap_count ?? 0} adet • Toplam {r.late_gap_total_gap_minutes ?? 0} dk
                      {r.late_gap_details && r.late_gap_details.length > 0 && (
                        <ul style={{ margin: "6px 0 0 16px" }}>
                          {r.late_gap_details.slice(0, 5).map((it, i) => (
                            <li key={`${it.reference_id}-${i}`}>
                              #{it.reference_id} • {it.gap_minutes} dk
                              {it.placed_ts ? ` • P: ${it.placed_ts}` : ""}{it.settled_ts ? ` • S: ${it.settled_ts}` : ""}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Satır 5: Top 3 Oyun / Sağlayıcı */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 8 }}>
                <div style={box}>
                  <div style={cap}>En Kârlı 3 Oyun</div>
                  <ul style={{ margin: "6px 0 0 16px" }}>
                    {r.top_games.length ? r.top_games.map((g) => <li key={g.name}>{g.name}: {fmt(g.value)}</li>) : <li>-</li>}
                  </ul>
                </div>
                <div style={box}>
                  <div style={cap}>En Kârlı 3 Sağlayıcı</div>
                  <ul style={{ margin: "6px 0 0 16px" }}>
                    {r.top_providers.length ? r.top_providers.map((p) => <li key={p.name}>{p.name}: {fmt(p.value)}</li>) : <li>-</li>}
                  </ul>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
