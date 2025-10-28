FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Railway $PORT verir; yoksa 8000'e düş.
ENV PORT=8000

# Dışarı bilgi amaçlı (zorunlu değil)
EXPOSE 8000

# En kritik satır: uvicorn'u $PORT'a bağla
CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"
