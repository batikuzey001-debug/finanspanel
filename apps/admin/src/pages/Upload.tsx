import React, { useState } from "react";
import Dropzone from "../components/Dropzone";
import { uploadFile /*, computeFile*/ } from "../lib/api"; // computeFile kullanmayacağız; cycle seçimiyle lokalde çağıracağız.

const tl = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY", maximumFractionDigits: 2 });
const fmt = (n?: number | null) => (typeof n === "number" ? tl.format(n) : "-");

/** Koyu tema stilleri (mevcutlarla uyumlu) */
const card: React.CSSProperties = { border: "1px solid #1f2937", borderRadius: 16, padding: 14, marginBottom: 14, background: "#151a23", boxShadow: "0 1px 8px rgba(0,0,0,0.25)" };
const box: React.CSSProperties  = { padding: 12, border: "1px solid #1f2937", borderRadius: 12, background: "#0f1520" };
const cap: React.CSSProperties  = { fontSize: 12, color: "#94a3b8", marginBottom: 4 };
const btnPrimary: React.CSSProperties = { marginTop: 16, padding: "11px 16px", borderRadius: 12, border: "1px solid #1f2937", cursor: "pointer", background: "linear-gradient(135deg, #0ea5e9, #6366f1)", color: "#fff", fontWeight: 700, letterSpacing: 0.3 };
const tiny: React.CSSProperties = { fontSize: 12, color: "#94a3b8" };
const selectStyle: React.CSSProperties = { width: "100%", padding: "10px 12px", borderRadius: 12, border: "1px solid #1f2937", background: "#0f1520", color: "#e5e7eb" };

/** API tabanı — lib/api.ts değiştirmeden burada da kullanıyoruz */
const API = (import.meta.env.VITE_API_BASE_URL as string) || "http://localhost:8000";

/** Tipler */
type Summary = {
  filename: string;
  sheet_names: string[];
  first_sheet: string | null;
  columns: string[];
  row_count_sampled: number;
  row_count_exact?: number;
};

type TopItem = { name: string; value: number };

type LateItem = {
  reference_id: string;
  placed_ts?: string | null;
  settled_ts?: string | null;
  gap_minutes?: number | null;
  reason: "missing_placed" | "gap_over_threshold" | string;
};

type Report = {
  member_id: string;
  /** Cycle & işlem bağlamı */
  last_operation_type: string;
  last_operation_ts: string | null;
  last_deposit_amount?: number | null;
  last_bonus_name?: string | null;
  last_bonus_amount?: number | null;
  last_payment_method?: string | null;

  /** Çevrim & kâr */
  total_wager: number;
  total_profit: number;
  requirement: number;
  remaining: number;

  /** Bonus alanları (opsiyonel) */
  bonus_wager?: number | null;
  bonus_profit?: number | null;
  bonus_to_main_amount?: number | null;

  /** Unsettled */
  unsettled_count: number;
  unsettled_amount: number;
  unsettled_reference_ids: string[];

  /** Global unsettled */
  global_unsettled_count: number;
  global_unsettled_amount: number;

  /** Deposit öncesi açıklar (ops.) */
  pre_deposit_unsettled_count?: number | null;
  pre_deposit_unsettled_amount?: number | null;
  balance_at_deposit?: number | null;

  /** LATE uyarıları (ops.) */
  late_missing_placed_count?: number;
  late_missing_placed_refs?: string[];
  late_gap_count?: number;
  late_gap_total_gap_minutes?: number;
  late_gap_details?: LateItem[];

  /** Top 3 */
  top_games: TopItem[];
  top_providers: TopItem[];

  /** Diğer */
  currency?: string | null;

  /** Cycle meta (ops.) */
  cycle_index?: number;
  cycle_start_at?: string | null;
  cycle_end_at?: string | null;
};

type ComputeResp = { filename: string; total_rows: number; reports: Report[]; };

type CycleEntry = {
  index: number;
  start_row: number;
  end_row: number;
  start_at: string;
  deposit_amount: number;
  payment_method?: string | null;
  bonus_after_deposit?: string | null;
  label: string; // "tarih • tutar • (Bonus: ... ) • [yöntem]"
};

type CyclesResp = { filename: string; total_rows: number; cycles: CycleEntry[] };

/** API çağrıları — bu dosyada lokal tanımlandı (lib/api.ts'e dokunmuyoruz) */
async function listCycles(file: File, memberId?: string): Promise<CyclesResp> {
  const body = new FormData();
  body.append("file", file);
  if (memberId) body.append("member_id", memberId);
  const r = await fetch(`${API}/uploads/cycles`, { method: "POST", body });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function computeCycle(file: File, cycleIndex?: number, memberId?: string, thresholdMinutes = 5): Promise<ComputeResp> {
  const body = new FormData();
  body.append("file", file);
  if (typeof cycleIndex === "number") body.append("cycle_index", String(cycleIndex));
  if (memberId) body.append("member_id", memberId);
  body.append("threshold_minutes", String(thresholdMinutes));
  const r = await fetch(`${API}/uploads/compute`, { method: "POST", body });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export default function Upload() {
  const [file, setFile] = useState<File | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);

  /** Cycle kontrolü için durumlar */
  const [cycles, setCycles] = useState<CycleEntry[] | null>(null);
  const [selectedCycle, setSelectedCycle] = useState<number | null>(null);

  /** Hesap sonucu */
  const [res, setRes] = useState<ComputeResp | null>(null);

  /** UI durum */
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const onFile = async (f: File) => {
    setFile(f);
    setSummary(null);
    setRes(null);
    setErr(null);
    setCycles(null);
    setSelectedCycle(null);

    setLoading(true);
    try {
      // 1) Özet
      const s = await uploadFile(f);
      setSummary(s);

      // 2) Cycle listesi
      const cy = await listCycles(f);
      setCycles(cy.cycles || []);

      // Varsayılan: en güncel yatırımı otomatik seç (son index)
      if (cy.cycles && cy.cycles.length) {
        setSelectedCycle(cy.cycles[cy.cycles.length - 1].index);
      }
    } catch (e: any) {
      setErr(e?.message || "Yükleme/Cycle hatası");
    } finally {
      setLoading(false);
    }
  };

  const onCompute = async () => {
    if (!file) return;
    setLoading(true);
    setErr(null);
    setRes(null);
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
      {/* Üst grid: Yükleme & Özet/Cycle seçimi */}
      <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 16 }}>
        <div style={card}>
          <Dropzone onFile={onFile} />

          {/* Cycle seçimi (dosya yüklendiyse ve cycle varsa) */}
          {cycles && cycles.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={{ ...cap, marginBottom: 6 }}>Cycle Seç</div>
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

      {/* Sonuçlar */}
      {res && (
        <div style={{ marginTop: 16 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
            <div style={{ fontWeight: 800, fontSize: 16 }}>Sonuçlar</div>
            <div style={tiny}>{res.filename} • {res.total_rows} satır</div>
          </div>

          {res.reports.slice(0, 30).map((r) => (
            <div key={`${r.member_id}-${r.cycle_index ?? "c"}`} style={card}>
              {/* Başlık + cycle meta */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <div style={{ fontWeight: 800, fontSize: 16 }}>
                  Üye: {r.member_id}
                  {typeof r.cycle_index === "number" && (
                    <span style={{ marginLeft: 8, fontSize: 12, color: "#94a3b8" }}>
                      {/* "#" + {r.cycle_index} ifadesini açık yazalım */}
                      • Cycle # {r.cycle_index} {r.cycle_start_at ? `(${r.cycle_start_at} → ${r.cycle_end_at || "…"})` : ""}
                    </span>
                  )}
                </div>
                <div style={tiny}>
                  {r.last_operation_type}{r.last_operation_ts ? ` • ${r.last_operation_ts}` : ""}
                </div>
              </div>

              {/* 1. satır: Yatırım/Bonus/Birim */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12 }}>
                <div style={box}><div style={cap}>Yatırım</div><div>{fmt(r.last_deposit_amount)}</div></div>
                <div style={box}><div style={cap}>Yöntem</div><div style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.last_payment_method || "-"}</div></div>
                <div style={box}><div style={cap}>Bonus</div><div>{r.last_bonus_name ? `${r.last_bonus_name} (${fmt(r.last_bonus_amount||0)})` : "-"}</div></div>
                <div style={box}><div style={cap}>Birim</div><div>{r.currency || "TRY"}</div></div>
              </div>

              {/* 2. satır: Çevrim/Gereksinim/Kalan/Kâr */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginTop: 8 }}>
                <div style={box}><div style={cap}>Toplam Çevrim</div><div>{fmt(r.total_wager)}</div></div>
                <div style={box}><div style={cap}>Gereksinim (1x)</div><div>{fmt(r.requirement)}</div></div>
                <div style={box}><div style={cap}>Kalan</div><div>{fmt(r.remaining)}</div></div>
                <div style={box}>
                  <div style={cap}>Toplam Kâr</div>
                  <div style={{ color: r.total_profit >= 0 ? "#34d399" : "#f87171", fontWeight: 800 }}>{fmt(r.total_profit)}</div>
                </div>
              </div>

              {/* 3. satır: Unsettled/Bonus */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12, marginTop: 8 }}>
                <div style={box}><div style={cap}>Unsettled (Cycle)</div><div>{r.unsettled_count} adet • {fmt(r.unsettled_amount)}</div></div>
                <div style={box}><div style={cap}>Unsettled (Global)</div><div>{r.global_unsettled_count} adet • {fmt(r.global_unsettled_amount)}</div></div>
                <div style={box}>
                  <div style={cap}>{r.last_operation_type === "BONUS" ? "Bonus → Ana Para" : "Bonus Çevrim"}</div>
                  <div>
                    {r.last_operation_type === "BONUS"
                      ? (r.bonus_to_main_amount != null ? fmt(r.bonus_to_main_amount) : "-")
                      : (r.bonus_wager != null ? fmt(r.bonus_wager) : "-")}
                  </div>
                </div>
              </div>

              {/* 4. satır: DEPOSIT özel alanlar */}
              {r.last_operation_type === "DEPOSIT" && (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12, marginTop: 8 }}>
                  <div style={box}><div style={cap}>Depozitodan Önce UNSETTLED</div><div>{r.pre_deposit_unsettled_count ?? 0} adet • {fmt(r.pre_deposit_unsettled_amount ?? 0)}</div></div>
                  <div style={box}><div style={cap}>Yatırım Anı Bakiyesi</div><div>{fmt(r.balance_at_deposit)}</div></div>
                  <div style={box}><div style={cap}>Bonus Çevrim</div><div>-</div></div>
                </div>
              )}

              {/* 5. satır: LATE uyarıları (varsa) */}
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
                    {/* Buradaki > karakterini JSX stringi olarak güvenceye alıyoruz */}
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

              {/* 6. satır: Top 3 Oyun / Sağlayıcı */}
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
