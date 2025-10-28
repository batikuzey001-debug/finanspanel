import React, { useCallback, useState } from "react";

type Props = { onFile: (file: File) => void };

export default function Dropzone({ onFile }: Props) {
  const [hover, setHover] = useState(false);

  const onDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setHover(false);
    const f = e.dataTransfer.files?.[0];
    if (f) onFile(f);
  }, [onFile]);

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setHover(true); }}
      onDragLeave={() => setHover(false)}
      onDrop={onDrop}
      style={{
        border: `2px dashed ${hover ? "#555" : "#999"}`,
        borderRadius: 16,
        padding: 32,
        textAlign: "center",
      }}
    >
      <p style={{ marginBottom: 8 }}>Dosyayı buraya sürükle-bırak</p>
      <p style={{ marginTop: 0, fontSize: 12, opacity: 0.7 }}>.csv, .xlsx, .xls, .xlsm desteklenir</p>

      <input
        type="file"
        accept=".csv,.xlsx,.xls,.xlsm"
        style={{ display: "none" }}
        id="f"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
        }}
      />
      <label
        htmlFor="f"
        style={{
          cursor: "pointer",
          display: "inline-block",
          marginTop: 12,
          padding: "10px 16px",
          borderRadius: 12,
          border: "1px solid #ddd",
        }}
      >
        Dosya Seç
      </label>
    </div>
  );
}
