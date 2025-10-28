#Image para Python con la version más reciente
FROM python:3.12-slim

#Path del diretioro
WORKDIR /app

COPY requirements.txt .

#Instalación de dependencias
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libgtk-3-0 \
    libasound2 \
    libx11-xcb1 \
    libxcb1 \
    libxss1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*
#instalacion de Playwright y sus navegadores
RUN pip install playwright \
    && playwright install chromium 

#Dependencias
COPY api/ ./api
COPY logs/ ./logs
COPY data/ ./data
COPY src/ ./src
COPY db/ ./db
COPY paths.py ./paths.py

#Exponer el puerto de la aplicación
EXPOSE 8000

#Comando para ejecutar la aplicación
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0","--port", "8000"]
