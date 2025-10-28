import Upload from "./pages/Upload";

export default function App() {
  return (
    <div style={{ maxWidth: 1160, margin: "0 auto", padding: "24px 20px", color: "#e5e7eb" }}>
      {/* Header */}
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <img
          src="https://i.ibb.co/mrqYR1kh/Gambler-ON-Logo.png"
          alt="GamblerON"
          style={{ height: 42, objectFit: "contain", filter: "drop-shadow(0 2px 12px rgba(0,0,0,.6))" }}
        />
        <div />
      </header>

      {/* Ana içerik */}
      <Upload />
    </div>
  );
}
