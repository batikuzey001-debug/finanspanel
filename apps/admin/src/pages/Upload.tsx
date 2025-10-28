import React, { useState } from "react";
import Dropzone from "../components/Dropzone";
import { uploadFile, computeFile } from "../lib/api";

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
  total_wager: number;
  total_profit: number;
  requirement: number;
  remaining: number;
  bonus_wager?: number | null;
  bonus_profit?: number | null;
  unsettled_count: number;
  unsettled_amount: number;
  unsettled_reference_ids: string[];
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
          <h3 style={{ fontSize: 18, fontWeight: 700 }}>Özet</h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12 }}>
            <div style={{ padding: 12, border: "1px solid #eee", borderRadius: 12 }}>
              <div style={{ fontSize: 12, opacity: 0.7 }}>Dosya</div>
              <div>{summary.filename}</div>
            </div>
            <div style={{ padding: 12, border: "1px solid #eee", borderRadius: 12 }}>
              <div style={{ fontSize: 12, opacity: 0.7 }}>Sheet</div>
              <div>{summary.first_sheet} ({summary.sheet_names.length})</div>
            </div>
            <div style={{ padding: 12, border: "1px solid #eee", borderRadius: 12 }}>
              <div style={{ fontSize: 12, opacity: 0.7 }}>Kolon</div>
              <div>{summary.columns.length}</div>
            </div>
            <div style={{ padding: 12, border: "1px solid #eee", borderRadius: 12 }}>
              <div style={{ fontSize: 12, opacity: 0.7 }}>Satır</div>
              <div>{summary.row_count_exact ?? summary.row_count_sampled}</div>
            </div>
          </div>

          <button onClick={onCompute} style={{ marginTop: 16, padding: "10px 16px", borderRadius: 10, border: "1px solid #ddd", cursor: "pointer" }}>
            Hesapla
          </button>

          {res && (
            <div style={{ marginTop: 24 }}>
              <h3 style={{ fontSize: 18, fontWeight: 700 }}>Sonuç (İlk 10)</h3>
              {res.reports.slice(0,10).map((r) => (
                <div key={r.member_id} style={{ border: "1px solid #eee", borderRadius: 12, padding: 12, marginBottom: 10 }}>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8 }}>
                    <div><b>Üye</b><div>{r.member_id}</div></div>
                    <div><b>Son İşlem</b><div>{r.last_operation_type} {r.last_operation_ts ? `(${r.last_operation_ts})` : ""}</div></div>
                    <div><b>Yatırım</b><div>{r.last_deposit_amount ?? "-"}</div></div>
                    <div><b>Bonus</b><div>{r.last_bonus_name ? `${r.last_bonus_name} (${r.last_bonus_amount ?? 0})` : "-"}</div></div>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8, marginTop: 8 }}>
                    <div><b>Çevrim</b><div>{r.total_wager}</div></div>
                    <div><b>Gereksinim</b><div>{r.requirement}</div></div>
                    <div><b>Kalan</b><div>{r.remaining}</div></div>
                    <div><b>Kâr</b><div>{r.total_profit}</div></div>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8, marginTop: 8 }}>
                    <div>
                      <b>Bonus Çevrim</b>
                      <div>{r.bonus_wager ?? "-"}</div>
                    </div>
                    <div>
                      <b>Unsettled</b>
                      <div>{r.unsettled_count} adet, {r.unsettled_amount}</div>
                    </div>
                    <div>
                      <b>Para Birimi</b>
                      <div>{r.currency ?? "-"}</div>
                    </div>
                  </div>

                  <div style={{ marginTop: 8, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                    <div>
                      <b>En Kârlı 3 Oyun</b>
                      <ul style={{ margin: 6 }}>
                        {r.top_games.length ? r.top_games.map((g) => <li key={g.name}>{g.name}: {g.value}</li>) : <li>-</li>}
                      </ul>
                    </div>
                    <div>
                      <b>En Kârlı 3 Sağlayıcı</b>
                      <ul style={{ margin: 6 }}>
                        {r.top_providers.length ? r.top_providers.map((p) => <li key={p.name}>{p.name}: {p.value}</li>) : <li>-</li>}
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
