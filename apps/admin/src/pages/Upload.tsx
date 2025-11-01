import React, { useState } from "react";
import Dropzone from "../components/Dropzone";

const API = (import.meta.env.VITE_API_BASE_URL as string) || "http://localhost:8000";
const tl = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY", maximumFractionDigits: 2 });
const fmt = (n?: number | null) => (typeof n === "number" ? tl.format(n) : "-");

const card: React.CSSProperties = { border: "1px solid #1f2937", borderRadius: 16, padding: 14, marginBottom: 14, background: "#151a23", boxShadow: "0 1px 8px rgba(0,0,0,0.25)" };
const box: React.CSSProperties  = { padding: 12, border: "1px solid #1f2937", borderRadius: 12, background: "#0f1520" };
const cap: React.CSSProperties  = { fontSize: 12, color: "#94a3b8", marginBottom: 4 };
const btn: React.CSSProperties  = { marginTop: 16, padding: "11px 16px", borderRadius: 12, border: "1px solid #1f2937", cursor: "pointer", background: "linear-gradient(135deg, #0ea5e9, #6366f1)", color: "#fff", fontWeight: 700 };

type Summary = { filename: string; sheet_names: string[]; first_sheet: string | null; columns: string[]; row_count_sampled: number; row_count_exact?: number; };
type CycleEntry = { index: number; start_row: number; end_row: number; start_at: string; deposit_amount: number; payment_method?: string | null; label: string; };
type CyclesResp = { filename: string; total_rows: number; cycles: CycleEntry[] };
type ProfitRow = { ts: string; source: "MAIN"|"BONUS"|"ADJUSTMENT"|string; amount: number; detail?: string|null };
type ProfitResp = { filename: string; cycle_index: number; member_id: string; rows: ProfitRow[] };

async function uploadFile(file: File) {
  const body = new FormData(); body.append("file", file);
  const r = await fetch(`${API}/uploads`, { method: "POST", body });
  if (!r.ok) throw new Error(await r.text()); return r.json();
}
async function listCycles(file: File): Promise<CyclesResp> {
  const body = new FormData(); body.append("file", file);
  const r = await fetch(`${API}/uploads/cycles`, { method: "POST", body });
  if (!r.ok) throw new Error(await r.text()); return r.json();
}
async function profitStream(file: File, cycleIndex?: number): Promise<ProfitResp> {
  const body = new FormData(); body.append("file", file);
  if (typeof cycleIndex === "number") body.append("cycle_index", String(cycleIndex));
  const r = await fetch(`${API}/uploads/profit-stream`, { method: "POST", body });
  if (!r.ok) throw new Error(await r.text()); return r.json();
}

export default function Upload() {
  const [file, setFile] = useState<File | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [cycles, setCycles] = useState<CycleEntry[] | null>(null);
  const [selectedCycle, setSelectedCycle] = useState<number | null>(null);
  const [profits, setProfits] = useState<ProfitResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const onFile = async (f: File) => {
    setFile(f); setSummary(null); setCycles(null); setSelectedCycle(null); setProfits(null); setErr(null);
    setLoading(true);
    try {
      const s = await uploadFile(f); setSummary(s);
      const cy = await listCycles(f); setCycles(cy.cycles || []);
      if (cy.cycles?.length) setSelectedCycle(cy.cycles[cy.cycles.length-1].index); // en yeni yatırım
    } catch (e: any) {
      setErr(e?.message || "Yükleme/Cycle hatası");
    } finally { setLoading(false); }
  };

  const onCompute = async () => {
    if (!file) return;
    setLoading(true); setErr(null); setProfits(null);
    try {
      const p = await profitStream(file, selectedCycle ?? undefined);
      setProfits(p);
    } catch (e: any) {
      setErr(e?.message || "Hesaplama hatası");
    } finally { setLoading(false); }
  };

  return (
    <div>
      {/* Üst grid: Yükleme + Cycle seçimi */}
      <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 16 }}>
        <div style={card}>
          <Dropzone onFile={onFile} />
          {cycles && cycles.length>0 && (
            <div style={{ marginTop: 12 }}>
              <div style={{ ...cap, marginBottom: 6 }}>Cycle Seç (Yalnızca Yatırımlar)</div>
              <select
                value={selectedCycle ?? ""}
                onChange={(e)=>setSelectedCycle(e.target.value===""?null:Number(e.target.value))}
                style={{ width:"100%", padding:"10px 12px", borderRadius:12, border:"1px solid #1f2937", background:"#0f1520", color:"#e5e7eb" }}
              >
                {cycles.map(c => <option key={c.index} value={c.index}>{c.label}</option>)}
              </select>
            </div>
          )}
          <button onClick={onCompute} style={btn} disabled={!file || loading}>{loading ? "İşleniyor…" : "Hesapla"}</button>
          {err && <p style={{ marginTop: 10, color: "#ef4444" }}>{err}</p>}
        </div>

        {summary && (
          <div style={card}>
            <div style={{ display:"grid", gridTemplateColumns:"repeat(2,1fr)", gap:12 }}>
              <div style={box}><div style={cap}>Dosya</div><div>{summary.filename}</div></div>
              <div style={box}><div style={cap}>Sheet</div><div>{summary.first_sheet} ({summary.sheet_names.length})</div></div>
              <div style={box}><div style={cap}>Kolon</div><div>{summary.columns.length}</div></div>
              <div style={box}><div style={cap}>Satır</div><div>{summary.row_count_exact ?? summary.row_count_sampled}</div></div>
            </div>
          </div>
        )}
      </div>

      {/* Kazanç Akışı (Tarih – Kaynak – Miktar – Detay) */}
      {profits && (
        <div style={{ marginTop: 16 }}>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:8 }}>
            <div style={{ fontWeight:800, fontSize:16 }}>Kazanç Akışı</div>
            <div style={{ fontSize:12, color:"#94a3b8" }}>{profits.filename} • Cycle #{profits.cycle_index} • Üye: {profits.member_id}</div>
          </div>

          <div style={{ border:"1px solid #1f2937", borderRadius:12, overflow:"hidden" }}>
            {/* Header */}
            <div style={{ display:"grid", gridTemplateColumns:"220px 200px 1fr 1fr", background:"#0f1520", padding:"10px 12px", fontSize:12, color:"#94a3b8" }}>
              <div>Tarih</div>
              <div>Kaynak</div>
              <div>Miktar</div>
              <div>Detay (Bonus/Depozito)</div>
            </div>
            {/* Rows */}
            {profits.rows.length ? profits.rows.map((r,idx)=>(
              <div key={idx} style={{ display:"grid", gridTemplateColumns:"220px 200px 1fr 1fr", padding:"10px 12px", borderTop:"1px solid #1f2937" }}>
                <div>{r.ts}</div>
                <div>{r.source==="MAIN" ? "Ana Para" : r.source==="BONUS" ? "Bonus" : r.source==="ADJUSTMENT" ? "Adjustment" : r.source}</div>
                <div style={{ color: (r.amount ?? 0) >= 0 ? "#34d399" : "#f87171", fontWeight:700 }}>{fmt(r.amount)}</div>
                <div style={{ whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>{r.detail || "-"}</div>
              </div>
            )) : (
              <div style={{ padding:"12px", color:"#94a3b8" }}>Kayıt yok.</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
