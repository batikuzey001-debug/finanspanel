import React, { useState } from "react";
import Dropzone from "../components/Dropzone";
import { uploadFile, computeFile } from "../lib/api";

const tl = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY", maximumFractionDigits: 2 });
const fmt = (n?: number | null) => (typeof n === "number" ? tl.format(n) : "-");

/** UI styles — koyu tema */
const card: React.CSSProperties = {
  border: "1px solid #1f2937",
  borderRadius: 16,
  padding: 14,
  marginBottom: 14,
  background: "#151a23",
  boxShadow: "0 1px 8px rgba(0,0,0,0.25)",
};
const box: React.CSSProperties = {
  padding: 12,
  border: "1px solid #1f2937",
  borderRadius: 12,
  background: "#0f1520",
};
const cap: React.CSSProperties = { fontSize: 12, color: "#94a3b8", marginBottom: 4 };
const btnPrimary: React.CSSProperties = {
  marginTop: 16,
  padding: "11px 16px",
  borderRadius: 12,
  border: "1px solid #1f2937",
  cursor: "pointer",
  background: "linear-gradient(135deg, #0ea5e9, #6366f1)",
  color: "#fff",
  fontWeight: 700,
  letterSpacing: 0.3,
};
const tiny: React.CSSProperties = { fontSize: 12, color: "#94a3b8" };

type Summary = {
  filename: string;
  sheet_names: string[];
  first_sheet: string | null;
  columns: string[];
  row_count_sampled: number;
  row_count_exact?: number;
};

type TopItem = { name: string; value: number };
type Report = {
  member_id: string;
  last_operation_type: string;
  last_operation_ts: string | null;
  last_deposit_amount?: number | null;
  last_bonus_name?: string | null;
  last_bonus_amount?: number | null;
  last_payment_method?: string | null;

  total_wager: number;
  total_profit: number;
  requirement: number;
  remaining: number;

  bonus_wager?: number | null;
  bonus_profit?: number | null;

  unsettled_count: number;
  unsettled_amount: number;
  unsettled_reference_ids: string[];

  global_unsettled_count: number;
  global_unsettled_amount: number;

  top_games: TopItem[];
  top_providers: TopItem[];
  currency?: string | null;
};

type ComputeResp = {
  filename: string;
  total_rows: number;
  reports: Report[];
};

export default function Upload() {
  const [file, setFile] = useState<File | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [res, setRes] = useState<ComputeResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const onFile = async (f: File) => {
    setFile(f); setSummary(null); setRes(null); setErr(null);
    setLoading(true);
    try {
      const s = await uploadFile(f);
      setSummary(s);
    } catch (e: any) {
      setErr(e?.message || "Yükleme hatası");
    } finally {
      setLoading(false);
    }
  };

  const onCompute = async () => {
    if (!file) return;
    setLoading(true); setErr(null); setRes(null);
    try {
      const r = await computeFile(file);
      setRes(r);
    } catch (e: any) {
      setErr(e?.message || "Hesaplama hatası");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      {/* Üst blok — dosya yükleme + özet */}
      <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 16 }}>
        <div style={card}>
          <Dropzone onFile={onFile} />
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

      {/* Sonuç kartları */}
      {res && (
        <div style={{ marginTop: 16 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
            <div style={{ fontWeight: 800, fontSize: 16 }}>Sonuçlar</div>
            <div style={tiny}>{res.filename} • {res.total_rows} satır</div>
          </div>

          {res.reports.slice(0, 30).map((r) => (
            <div key={r.member_id} style={card}>
              {/* Başlık */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <div style={{ fontWeight: 800, fontSize: 16 }}>Üye: {r.member_id}</div>
                <div style={tiny}>{r.last_operation_type}{r.last_operation_ts ? ` • ${r.last_operation_ts}` : ""}</div>
              </div>

              {/* Satır 1: Yatırım/Bonus/Para Birimi */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12 }}>
                <div style={box}><div style={cap}>Yatırım Tutarı</div><div>{fmt(r.last_deposit_amount)}</div></div>
                <div style={box}><div style={cap}>Yöntem</div><div style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.last_payment_method || "-"}</div></div>
                <div style={box}><div style={cap}>Bonus</div><div>{r.last_bonus_name ? `${r.last_bonus_name} (${fmt(r.last_bonus_amount||0)})` : "-"}</div></div>
                <div style={box}><div style={cap}>Birim</div><div>{r.currency || "TRY"}</div></div>
              </div>

              {/* Satır 2: Çevrim/Gereksinim/Kalan/Kâr */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginTop: 8 }}>
                <div style={box}><div style={cap}>Toplam Çevrim</div><div>{fmt(r.total_wager)}</div></div>
                <div style={box}><div style={cap}>Gereksinim (1x)</div><div>{fmt(r.requirement)}</div></div>
                <div style={box}><div style={cap}>Kalan</div><div>{fmt(r.remaining)}</div></div>
                <div style={box}>
                  <div style={cap}>Toplam Kâr</div>
                  <div style={{ color: r.total_profit >= 0 ? "#34d399" : "#f87171", fontWeight: 800 }}>
                    {fmt(r.total_profit)}
                  </div>
                </div>
              </div>

              {/* Satır 3: Unsettled & Bonus Çevrim */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12, marginTop: 8 }}>
                <div style={box}><div style={cap}>Unsettled (Cycle)</div><div>{r.unsettled_count} adet • {fmt(r.unsettled_amount)}</div></div>
                <div style={box}><div style={cap}>Unsettled (Global)</div><div>{r.global_unsettled_count} adet • {fmt(r.global_unsettled_amount)}</div></div>
                <div style={box}><div style={cap}>Bonus Çevrim</div><div>{r.bonus_wager != null ? fmt(r.bonus_wager) : "-"}</div></div>
              </div>

              {/* Satır 4: Top 3 Oyun / Sağlayıcı */}
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
