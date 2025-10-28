const API = (import.meta.env.VITE_API_BASE_URL as string) || "http://localhost:8000";

export async function uploadFile(file: File) {
  const body = new FormData();
  body.append("file", file);
  const r = await fetch(`${API}/uploads`, { method: "POST", body });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function computeFile(file: File, params?: { date_from?: string; date_to?: string }) {
  const body = new FormData();
  body.append("file", file);
  if (params?.date_from) body.append("date_from", params.date_from);
  if (params?.date_to) body.append("date_to", params.date_to);
  const r = await fetch(`${API}/uploads/compute`, { method: "POST", body });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
