# Imagen unica para el backend (FastAPI) y el frontend (Streamlit): comparten
# las mismas dependencias Python. El comando real lo define cada servicio en
# docker-compose.yml.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY ui/ ./ui/

EXPOSE 8000 8501

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
