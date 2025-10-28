import Upload from "./pages/Upload";

export default function App() {
  return (
    <div style={{ maxWidth: 960, margin: "24px auto", padding: 16 }}>
      <h1 style={{ fontSize: 28, fontWeight: 800, marginBottom: 6 }}>Çevrim Paneli</h1>
      <p style={{ opacity: 0.75, marginBottom: 20 }}>
        Dosyanı yükle, kolonları ve satır sayısını kontrol et. Sonraki adımda kural motorunu ekleyeceğiz.
      </p>
      <Upload />
    </div>
  );
}
