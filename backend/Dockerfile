# TerraTwin backend — FastAPI + Uvicorn
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONUTF8=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# BAT BUOC phai copy data/: trong do co anomaly_model.json (92 KB), thu ma lop
# hoc may can luc chay. Thieu no thi /api/anomaly-ml am tham tra None trong khi
# o may phat trien van chay tot - dung loai loi chi lo ra sau khi da trien khai.
COPY data ./data

# Noi CSDL SQLite se nam, tach khoi /app/data de volume khong che mat mo hinh.
RUN mkdir -p /app/var

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
