import React from "react";

const tl = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY", maximumFractionDigits: 2 });
const fmt = (n?: number | null) => (typeof n === "number" ? tl.format(n) : "-");

const wrap: React.CSSProperties = { border: "1px solid #1f2937", borderRadius: 16, padding: 14, background: "#151a23", boxShadow: "0 1px 8px rgba(0,0,0,0.25)" };
const row: React.CSSProperties  = { display: "grid", gap: 12, marginTop: 10 };
const box: React.CSSProperties  = { padding: 12, border: "1px solid #1f2937", borderRadius: 12, background: "#0f1520" };
const cap: React.CSSProperties  = { fontSize: 12, color: "#94a3b8", marginBottom: 4 };

type Row1 = { type: "DEPOSIT"|"BONUS"|"ADJUSTMENT"|string; ts: string; amount: number; method?: string|null; bonus_detail?: string|null; bonus_kind?: string|null };
type Row2 = { window_from: string; window_to?: string|null; wager_total: number; wager_count: number };
type OpenItem = { id?: string|null; placed_ts?: string|null; amount?: number|null };
type LateItem = { id?: string|null; placed_ts?: string|null; settled_ts?: string|null; gap_minutes?: number|null; placed_amount?: number|null; settled_amount?: number|null };
type Row3 = { open_total_amount: number; open_count: number; items: OpenItem[] };
type Row4 = { late_gap_count: number; late_gap_total_minutes: number; items: LateItem[] };
type TopGame = { game_name: string; wager: number; profit: number };
type Row5 = { items: TopGame[] };

type Brief = {
  filename: string;
  cycle_index: number;
  member_id: string;
  row1_last_op: Row1;
  row2_wager: Row2;
  row3_open: Row3;
  row4_late: Row4;
  row5_top_games: Row5;
  currency?: string|null;
};

export default function BriefCard({ data }: { data: Brief }) {
  const r1 = data.row1_last_op, r2 = data.row2_wager, r3 = data.row3_open, r4 = data.row4_late, r5 = data.row5_top_games;
  return (
    <div style={wrap}>
      {/* Header */}
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom: 6 }}>
        <div style={{ fontWeight: 800, fontSize: 16 }}>Özet (Brief) • Üye: {data.member_id}</div>
        <div style={{ fontSize: 12, color: "#94a3b8" }}>{data.filename} • Cycle #{data.cycle_index}</div>
      </div>

      {/* 1) Son İşlem & Kaynak */}
      <div style={row}>
        <div style={box}>
          <div style={cap}>1) Son İşlem & Kaynak</div>
          <div style={{ display: "grid", gridTemplateColumns: "200px 1fr 1fr", gap: 12 }}>
            <div><b>Tür</b><div>{r1.type === "DEPOSIT" ? "Yatırım" : r1.type === "BONUS" ? "Bonus" : "Adjustment"}</div></div>
            <div><b>Tarih</b><div>{r1.ts}</div></div>
            <div><b>Tutar</b><div>{fmt(r1.amount)}</div></div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 8 }}>
            <div><b>Detay</b><div style={{ opacity: 0.95 }}>{r1.type === "BONUS" ? (r1.bonus_detail || "-") : (r1.method || "-")}</div></div>
            <div><b>Bonus Türü</b><div>{r1.type === "BONUS" ? (r1.bonus_kind || "other") : "-"}</div></div>
          </div>
        </div>
      </div>

      {/* 2) Toplam Çevrim (bu işleme bağlı pencere) */}
      <div style={row}>
        <div style={box}>
          <div style={cap}>2) Toplam Çevrim (pencere)</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
            <div><b>Başlangıç</b><div>{r2.window_from}</div></div>
            <div><b>Bitiş</b><div>{r2.window_to || "—"}</div></div>
            <div><b>Çevrim</b><div>{fmt(r2.wager_total)} <span style={{ fontSize: 12, color: "#94a3b8" }}>({r2.wager_count} bahis)</span></div></div>
          </div>
        </div>
      </div>

      {/* 3) Sonuçlanmamış İşlemler */}
      <div style={row}>
        <div style={box}>
          <div style={cap}>3) Sonuçlanmamış İşlemler</div>
          <div><b>Toplam</b> {r3.open_count} adet • {fmt(r3.open_total_amount)}</div>
          {r3.items?.length ? (
            <ul style={{ margin: "6px 0 0 16px" }}>
              {r3.items.slice(0, 12).map((it, i) => (
                <li key={`o-${i}`}>#{it.id || "-"} • {it.placed_ts || "-"} • {fmt(it.amount ?? 0)}</li>
              ))}
            </ul>
          ) : <div style={{ color:"#94a3b8", marginTop: 6 }}>Kayıt yok.</div>}
        </div>
      </div>

      {/* 4) Gecikmeli Sonuçlanan (>5dk) */}
      <div style={row}>
        <div style={box}>
          <div style={cap}>4) Gecikmeli Sonuçlanan İşlemler (>5dk)</div>
          <div><b>Toplam</b> {r4.late_gap_count} adet • {Math.round(r4.late_gap_total_minutes)} dk</div>
          {r4.items?.length ? (
            <ul style={{ margin: "6px 0 0 16px" }}>
              {r4.items.slice(0, 12).map((it, i) => (
                <li key={`l-${i}`}>#{it.id || "-"} • P:{it.placed_ts || "-"} → S:{it.settled_ts || "-"} • {it.gap_minutes} dk • {fmt(it.placed_amount ?? 0)} → {fmt(it.settled_amount ?? 0)}</li>
              ))}
            </ul>
          ) : <div style={{ color:"#94a3b8", marginTop: 6 }}>Kayıt yok.</div>}
        </div>
      </div>

      {/* 5) En Çok Çevrim Yapılan 3 Oyun (kâr/zarar) */}
      <div style={row}>
        <div style={box}>
          <div style={cap}>5) En Çok Çevrim Yapılan 3 Oyun (kâr/zarar)</div>
          {r5.items?.length ? (
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap: 12 }}>
              {r5.items.map((g, i) => (
                <div key={i} style={{ border:"1px dashed #263244", borderRadius:10, padding:10 }}>
                  <div style={{ fontWeight: 700, marginBottom: 4 }}>{g.game_name}</div>
                  <div>Çevrim: {fmt(g.wager)}</div>
                  <div>Kâr/Zarar: <b style={{ color: g.profit >= 0 ? "#34d399" : "#f87171" }}>{fmt(g.profit)}</b></div>
                </div>
              ))}
            </div>
          ) : <div style={{ color:"#94a3b8" }}>Kayıt yok.</div>}
        </div>
      </div>
    </div>
  );
}
