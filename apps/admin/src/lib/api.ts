const API = (import.meta.env.VITE_API_BASE_URL as string) || "http://localhost:8000";

export async function uploadFile(file: File) {
  const body = new FormData();
  body.append("file", file);
  const r = await fetch(`${API}/uploads`, { method: "POST", body });
  if (!r.ok) {
    const t = await r.text().catch(() => "");
    throw new Error(t || "Yükleme başarısız");
  }
  return r.json();
}
