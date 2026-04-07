# comenzar desde el contenedor con python 3.11 slim
FROM python:3.11-slim

# establecer el directorio de trabajo en /app
WORKDIR /app

# copiar todo al directorio de trabajo
COPY . .

# instalar dependencias
RUN pip install --no-cache-dir -r requirements.txt

# exponer el puerto 8000 (por defecto uvicorn)
EXPOSE 8000

# ejecutar la aplicación (main:app = archivo main.py, variable app)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
