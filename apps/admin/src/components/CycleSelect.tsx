import React from "react";

type Cycle = { index: number; label: string };

type Props = {
  cycles: Cycle[];
  selected: number | null;
  onChange: (idx: number | null) => void;
  disabled?: boolean;
};

export default function CycleSelect({ cycles, selected, onChange, disabled }: Props) {
  if (!cycles?.length) return null;
  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ fontSize: 12, color: "#94a3b8", marginBottom: 6 }}>Cycle Seç (Yalnız Yatırımlar)</div>
      <select
        value={selected ?? ""}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
        disabled={disabled}
        style={{
          width: "100%",
          padding: "10px 12px",
          borderRadius: 12,
          border: "1px solid #1f2937",
          background: "#0f1520",
          color: "#e5e7eb",
        }}
      >
        {cycles.map((c) => (
          <option key={c.index} value={c.index}>
            {c.label}
          </option>
        ))}
      </select>
    </div>
  );
}
