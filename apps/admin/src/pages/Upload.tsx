import React, { useState } from "react";
import Dropzone from "../components/Dropzone";
import { uploadFile } from "../lib/api";

type Summary = {
  filename: string;
  sheet_names: string[];
  first_sheet: string | null;
  columns: string[];
  row_count_sampled: number;
};

export default function Upload() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const handle = async (file: File) => {
    setLoading(true); setErr(null); setSummary(null);
    try {
      const res = await uploadFile(file);
      setSummary(res);
    } catch (e: any) {
      setErr(e?.message || "Yükleme hatası");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <Dropzone onFile={handle} />
      {loading && <p style={{ marginTop: 16 }}>Yükleniyor…</p>}
      {err && <p style={{ marginTop: 16, color: "#b00" }}>{err}</p>}
      {summary && (
        <div style={{ marginTop: 20 }}>
          <h3 style={{ fontSize: 18, fontWeight: 700 }}>Özet</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div style={{ padding: 12, border: "1px solid #eee", borderRadius: 12 }}>
              <div style={{ fontSize: 12, opacity: 0.7 }}>Dosya</div>
              <div>{summary.filename}</div>
            </div>
            <div style={{ padding: 12, border: "1px solid #eee", borderRadius: 12 }}>
              <div style={{ fontSize: 12, opacity: 0.7 }}>Sheet</div>
              <div>{summary.first_sheet} ({summary.sheet_names.length})</div>
            </div>
            <div style={{ padding: 12, border: "1px solid #eee", borderRadius: 12 }}>
              <div style={{ fontSize: 12, opacity: 0.7 }}>Kolon Sayısı</div>
              <div>{summary.columns.length}</div>
            </div>
            <div style={{ padding: 12, border: "1px solid #eee", borderRadius: 12 }}>
              <div style={{ fontSize: 12, opacity: 0.7 }}>Örnek Satır</div>
              <div>{summary.row_count_sampled}</div>
            </div>
          </div>

          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 6 }}>Kolonlar</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {summary.columns.map((c) => (
                <span key={c} style={{ fontSize: 12, padding: "6px 10px", border: "1px solid #eee", borderRadius: 999 }}>
                  {c}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
