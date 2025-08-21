#Image para Python con la version más reciente
FROM python:3.12-slim

#Path del diretioro
WORKDIR /app

COPY requirements.txt .

#Instalación de dependencias
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

#Dependencias
COPY api/ ./api
COPY logs/ ./logs
COPY data/ ./data
COPY src/ ./src
COPY db/ ./db

#Exponer el puerto de la aplicación
EXPOSE 8000

#Comando para ejecutar la aplicación
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0","--port", "8000","--reload"]
