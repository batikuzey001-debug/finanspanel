import React, { useState } from "react";
import Dropzone from "../components/Dropzone";
import { uploadFile, computeFile } from "../lib/api";

const tl = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY", maximumFractionDigits: 2 });
const fmt = (n?: number | null) => (typeof n === "number" ? tl.format(n) : "-");

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
      <Dropzone onFile={onFile} />
      {loading && <p style={{ marginTop: 16 }}>İşleniyor…</p>}
      {err && <p style={{ marginTop: 16, color: "#b00" }}>{err}</p>}

      {summary && (
        <div style={{ marginTop: 20 }}>
          <h3 style={{ fontSize: 18, fontWeight: 700, marginBottom: 8 }}>Özet</h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12 }}>
            <div style={box}><div style={cap}>Dosya</div><div>{summary.filename}</div></div>
            <div style={box}><div style={cap}>Sheet</div><div>{summary.first_sheet} ({summary.sheet_names.length})</div></div>
            <div style={box}><div style={cap}>Kolon</div><div>{summary.columns.length}</div></div>
            <div style={box}><div style={cap}>Satır</div><div>{summary.row_count_exact ?? summary.row_count_sampled}</div></div>
          </div>

          <button onClick={onCompute} style={btn}>Hesapla</button>

          {res && (
            <div style={{ marginTop: 24 }}>
              <h3 style={{ fontSize: 18, fontWeight: 700, marginBottom: 8 }}>Sonuç (ilk 20)</h3>
              {res.reports.slice(0, 20).map((r) => (
                <div key={r.member_id} style={card}>
                  {/* Üst başlık */}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                    <div style={{ fontWeight: 800, fontSize: 16 }}>Üye: {r.member_id}</div>
                    <div style={{ fontSize: 12, opacity: 0.7 }}>{r.last_operation_type}{r.last_operation_ts ? ` • ${r.last_operation_ts}` : ""}</div>
                  </div>

                  {/* 1. satır: Yatırım/Bonus */}
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12 }}>
                    <div style={box}>
                      <div style={cap}>Yatırım Tutarı</div>
                      <div>{fmt(r.last_deposit_amount)}</div>
                    </div>
                    <div style={box}>
                      <div style={cap}>Yatırım Yöntemi</div>
                      <div style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {r.last_payment_method || "-"}
                      </div>
                    </div>
                    <div style={box}>
                      <div style={cap}>Bonus</div>
                      <div>{r.last_bonus_name ? `${r.last_bonus_name} (${fmt(r.last_bonus_amount||0)})` : "-"}</div>
                    </div>
                    <div style={box}>
                      <div style={cap}>Para Birimi</div>
                      <div>{r.currency || "TRY"}</div>
                    </div>
                  </div>

                  {/* 2. satır: Çevrim/Gereksinim/Kalan/Kâr */}
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginTop: 8 }}>
                    <div style={box}><div style={cap}>Toplam Çevrim</div><div>{fmt(r.total_wager)}</div></div>
                    <div style={box}><div style={cap}>Gereksinim (1x)</div><div>{fmt(r.requirement)}</div></div>
                    <div style={box}><div style={cap}>Kalan Çevrim</div><div>{fmt(r.remaining)}</div></div>
                    <div style={box}>
                      <div style={cap}>Toplam Kâr</div>
                      <div style={{ color: r.total_profit >= 0 ? "#0a7d2b" : "#b00020", fontWeight: 700 }}>
                        {fmt(r.total_profit)}
                      </div>
                    </div>
                  </div>

                  {/* 3. satır: Unsettled */}
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12, marginTop: 8 }}>
                    <div style={box}><div style={cap}>Unsettled (Cycle)</div><div>{r.unsettled_count} adet, {fmt(r.unsettled_amount)}</div></div>
                    <div style={box}><div style={cap}>Unsettled (Global)</div><div>{r.global_unsettled_count} adet, {fmt(r.global_unsettled_amount)}</div></div>
                    <div style={box}><div style={cap}>Bonus Çevrim</div><div>{r.bonus_wager != null ? fmt(r.bonus_wager) : "-"}</div></div>
                  </div>

                  {/* 4. satır: Top 3 Oyun / Sağlayıcı */}
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 8 }}>
                    <div style={box}>
                      <div style={cap}>En Kârlı 3 Oyun</div>
                      <ul style={{ margin: 6 }}>
                        {r.top_games.length ? r.top_games.map((g) => <li key={g.name}>{g.name}: {fmt(g.value)}</li>) : <li>-</li>}
                      </ul>
                    </div>
                    <div style={box}>
                      <div style={cap}>En Kârlı 3 Sağlayıcı</div>
                      <ul style={{ margin: 6 }}>
                        {r.top_providers.length ? r.top_providers.map((p) => <li key={p.name}>{p.name}: {fmt(p.value)}</li>) : <li>-</li>}
                      </ul>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const box: React.CSSProperties = { padding: 12, border: "1px solid #eee", borderRadius: 12, background: "#fff" };
const cap: React.CSSProperties = { fontSize: 12, opacity: 0.7, marginBottom: 4 };
const btn: React.CSSProperties = { marginTop: 16, padding: "10px 16px", borderRadius: 12, border: "1px solid #ddd", cursor: "pointer", background: "#111", color: "#fff" };
const card: React.CSSProperties = { border: "1px solid #e9e9e9", borderRadius: 16, padding: 14, marginBottom: 14, background: "#fafafa", boxShadow: "0 1px 6px rgba(0,0,0,0.05)" };
