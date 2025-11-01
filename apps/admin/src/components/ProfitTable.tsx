import React from "react";

const tl = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY", maximumFractionDigits: 2 });
const fmt = (n?: number | null) => (typeof n === "number" ? tl.format(n) : "-");

type Row = { ts: string; source: string; amount: number; detail?: string | null };
type Props = { filename: string; cycle_index: number; member_id: string; rows: Row[] };

export default function ProfitTable({ filename, cycle_index, member_id, rows }: Props) {
  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <div style={{ fontWeight: 800, fontSize: 16 }}>Kazanç Akışı</div>
        <div style={{ fontSize: 12, color: "#94a3b8" }}>
          {filename} • Cycle #{cycle_index} • Üye: {member_id}
        </div>
      </div>

      <div style={{ border: "1px solid #1f2937", borderRadius: 12, overflow: "hidden" }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "220px 200px 1fr 1fr",
            background: "#0f1520",
            padding: "10px 12px",
            fontSize: 12,
            color: "#94a3b8",
          }}
        >
          <div>Tarih</div>
          <div>Kaynak</div>
          <div>Miktar</div>
          <div>Detay (Bonus/Depozito)</div>
        </div>
        {rows.length ? (
          rows.map((r, i) => (
            <div
              key={i}
              style={{
                display: "grid",
                gridTemplateColumns: "220px 200px 1fr 1fr",
                padding: "10px 12px",
                borderTop: "1px solid #1f2937",
              }}
            >
              <div>{r.ts}</div>
              <div>
                {r.source === "MAIN"
                  ? "Ana Para"
                  : r.source === "BONUS"
                  ? "Bonus"
                  : r.source === "ADJUSTMENT"
                  ? "Adjustment"
                  : r.source}
              </div>
              <div
                style={{
                  color: (r.amount ?? 0) >= 0 ? "#34d399" : "#f87171",
                  fontWeight: 700,
                }}
              >
                {fmt(r.amount)}
              </div>
              <div style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {r.detail || "-"}
              </div>
            </div>
          ))
        ) : (
          <div style={{ padding: "12px", color: "#94a3b8" }}>Kayıt yok.</div>
        )}
      </div>
    </div>
  );
}
