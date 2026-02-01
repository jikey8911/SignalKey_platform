FROM python:3.10-slim

WORKDIR /app

# Instalar dependencias del sistema si son necesarias (ej. gcc para algunas libs de python)
# RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

# Copiar requirements primero para aprovechar cache de Docker
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo el código
COPY . .

# Establecer PYTHONPATH para que encuentre los módulos 'api' desde la raíz
ENV PYTHONPATH=/app

# Exponer puerto
EXPOSE 8000

# Comando de arranque
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
