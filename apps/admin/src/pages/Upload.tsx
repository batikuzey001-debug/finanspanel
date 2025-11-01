import React, { useState } from "react";
import Dropzone from "../components/Dropzone";
import BriefCard from "../components/BriefCard";

const API = (import.meta.env.VITE_API_BASE_URL as string) || "http://localhost:8000";

type Summary    = { filename: string; sheet_names: string[]; first_sheet: string | null; columns: string[]; row_count_exact: number; };
type CycleEntry = { index: number; start_row: number; end_row: number; start_at: string; label: string; };
type CyclesResp = { filename: string; total_rows: number; cycles: CycleEntry[] };

async function uploadSummaryV2(file: File): Promise<Summary> {
  const body = new FormData(); body.append("file", file);
  const r = await fetch(`${API}/v2/upload-summary`, { method: "POST", body });
  if (!r.ok) throw new Error(await r.text()); return r.json();
}
async function listCycles(file: File): Promise<CyclesResp> {
  const body = new FormData(); body.append("file", file);
  const r = await fetch(`${API}/v2/cycles`, { method: "POST", body });
  if (!r.ok) throw new Error(await r.text()); return r.json();
}
async function briefAPI(file: File, startIdx?: number|null, endIdx?: number|null) {
  const body = new FormData(); body.append("file", file);
  if (startIdx !== null && startIdx !== undefined) body.append("start_cycle_index", String(startIdx));
  if (endIdx   !== null && endIdx   !== undefined)   body.append("end_cycle_index",   String(endIdx));
  const r = await fetch(`${API}/v2/brief`, { method: "POST", body });
  if (!r.ok) throw new Error(await r.text()); return r.json();
}

const card: React.CSSProperties = { border: "1px solid #1f2937", borderRadius: 16, padding: 14, marginBottom: 14, background: "#151a23" };
const box:  React.CSSProperties = { padding: 12, border: "1px solid #1f2937", borderRadius: 12, background: "#0f1520" };
const cap:  React.CSSProperties = { fontSize: 12, color: "#94a3b8", marginBottom: 4 };
const btn:  React.CSSProperties = { marginTop: 16, padding: "11px 16px", borderRadius: 12, border: "1px solid #1f2937", cursor: "pointer", background: "linear-gradient(135deg, #0ea5e9, #6366f1)", color: "#fff", fontWeight: 700 };

export default function Upload() {
  const [file, setFile] = useState<File | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [cycles, setCycles] = useState<CycleEntry[] | null>(null);
  const [startCycle, setStartCycle] = useState<number | null>(null);
  const [endCycle,   setEndCycle]   = useState<number | null>(null);
  const [brief, setBrief] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const onFile = async (f: File) => {
    setFile(f); setSummary(null); setCycles(null); setStartCycle(null); setEndCycle(null); setBrief(null); setErr(null);
    setLoading(true);
    try {
      const s = await uploadSummaryV2(f); setSummary(s);
      const cy = await listCycles(f); setCycles(cy.cycles || []);
      if (cy.cycles?.length) {
        const last = cy.cycles[cy.cycles.length-1].index;
        setStartCycle(last);
        setEndCycle(last); // varsayılan: tek cycle
      }
    } catch (e: any) { setErr(e?.message || "Yükleme/Cycle hatası"); }
    finally { setLoading(false); }
  };

  const onCompute = async () => {
    if (!file) return;
    setLoading(true); setErr(null); setBrief(null);
    try { const b = await briefAPI(file, startCycle, endCycle ?? startCycle); setBrief(b); }
    catch (e: any) { setErr(e?.message || "Hesaplama hatası"); }
    finally { setLoading(false); }
  };

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 16 }}>
        <div style={card}>
          <Dropzone onFile={onFile} />

          {cycles && cycles.length>0 && (
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap: 10, marginTop: 12 }}>
              <div>
                <div style={{ ...cap, marginBottom: 6 }}>Başlangıç Cycle</div>
                <select
                  value={startCycle ?? ""}
                  onChange={(e)=> {
                    const v = e.target.value === "" ? null : Number(e.target.value);
                    setStartCycle(v);
                    if (v !== null && (endCycle === null || (endCycle as number) < v)) setEndCycle(v);
                  }}
                  style={{ width:"100%", padding:"10px 12px", borderRadius:12, border:"1px solid #1f2937", background:"#0f1520", color:"#e5e7eb" }}
                >
                  {cycles.map(c => <option key={c.index} value={c.index}>{c.label}</option>)}
                </select>
              </div>
              <div>
                <div style={{ ...cap, marginBottom: 6 }}>Bitiş Cycle</div>
                <select
                  value={endCycle ?? ""}
                  onChange={(e)=> setEndCycle(e.target.value === "" ? null : Number(e.target.value))}
                  style={{ width:"100%", padding:"10px 12px", borderRadius:12, border:"1px solid #1f2937", background:"#0f1520", color:"#e5e7eb" }}
                >
                  {cycles.filter(c => startCycle===null || c.index >= startCycle).map(c => (
                    <option key={c.index} value={c.index}>{c.label}</option>
                  ))}
                </select>
              </div>
            </div>
          )}

          <button onClick={onCompute} style={btn} disabled={!file || loading}>
            {loading ? "İşleniyor…" : "Hesapla"}
          </button>

          {err && <p style={{ marginTop: 10, color: "#ef4444" }}>{err}</p>}
        </div>

        {summary && (
          <div style={card}>
            <div style={{ display:"grid", gridTemplateColumns:"repeat(2,1fr)", gap:12 }}>
              <div style={{ padding: 12, border: "1px solid #1f2937", borderRadius: 12, background: "#0f1520" }}>
                <div style={cap}>Dosya</div><div>{summary.filename}</div>
              </div>
              <div style={{ padding: 12, border: "1px solid #1f2937", borderRadius: 12, background: "#0f1520" }}>
                <div style={cap}>Sheet</div><div>{summary.first_sheet} ({summary.sheet_names.length})</div>
              </div>
              <div style={{ padding: 12, border: "1px solid #1f2937", borderRadius: 12, background: "#0f1520" }}>
                <div style={cap}>Kolon</div><div>{summary.columns.length}</div>
              </div>
              <div style={{ padding: 12, border: "1px solid #1f2937", borderRadius: 12, background: "#0f1520" }}>
                <div style={cap}>Satır</div><div>{summary.row_count_exact}</div>
              </div>
            </div>
          </div>
        )}
      </div>

      {brief && (
        <div style={{ marginTop: 16 }}>
          <BriefCard data={brief} />
        </div>
      )}
    </div>
  );
}
