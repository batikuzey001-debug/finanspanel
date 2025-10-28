# Finans Panel — Çevrim Yükleme v0.1

Bu sürüm **dosya yükleme** yapar, Excel/CSV'den **sheet/kolon/satır özetini** döner.

- API (FastAPI): `/uploads` endpoint'i
- Admin (React/Vite): Sürükle-bırak yükleme ve özet kartları

## Lokal Geliştirme
**API**
```bash
cd apps/api
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
