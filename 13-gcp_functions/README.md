# Funciones de Google Cloud Functions

Todas las funciones se activan con el evento `google.storage.object.finalize`, es decir, cada vez que se sube un archivo al bucket de Cloud Storage configurado (`pf3882ejemploseventos`).

---

## 1. `moderar_imagen` — Moderación de contenido inapropiado

**Archivo:** `moderador/main.py`

Analiza cada imagen subida al bucket usando la API de **Cloud Vision** para detectar contenido inapropiado (adulto, violencia, contenido explícito o médico). Si la imagen supera el umbral `LIKELY` en alguna de esas categorías, le aplica un filtro de **desenfoque gaussiano** (Gaussian Blur) antes de guardarla. Si la imagen es segura, la copia sin modificaciones.

El resultado se almacena en la carpeta `vision/` dentro del mismo bucket. Para evitar bucles infinitos, la función ignora imágenes que ya estén en esa carpeta.

**Flujo:**

1. Recibe el evento con el nombre del archivo y el bucket.
2. Llama a `safe_search_detection` de Vision AI.
3. Si el contenido es inapropiado → aplica blur y guarda en `vision/<archivo>`.
4. Si el contenido es seguro → guarda la imagen original en `vision/<archivo>`.

---

## 2. `detectar_rostros` — Detección de rostros en imágenes

**Archivo:** `rostros/main.py`

Analiza cada imagen usando la API de **Cloud Vision** para detectar rostros humanos. Si la imagen **no contiene ningún rostro**, le dibuja encima el texto `"FALTA ROSTRO"` en color rojo y la guarda en la carpeta `rostros/`. Si sí contiene rostros, no modifica la imagen (solo registra en el log).

La función omite imágenes que ya estén en la carpeta `rostros/` para evitar reprocesamiento.

**Flujo:**

1. Recibe el evento con el nombre del archivo y el bucket.
2. Llama a `face_detection` de Vision AI.
3. Sin rostros → dibuja texto de advertencia y guarda en `rostros/<archivo>`.
4. Con rostros → no realiza cambios.

---

## 3. `crear_thumbnail` — Generación de miniaturas

**Archivo:** `thumbnails/main.py`

Genera una versión reducida (miniatura) de cada imagen subida al bucket. El ancho máximo del thumbnail es **300 píxeles** (manteniendo la proporción original). La miniatura se guarda en la carpeta `thumbnails/` dentro del mismo bucket.

La función omite archivos que ya estén en `thumbnails/` para evitar crear miniaturas de miniaturas.

**Flujo:**

1. Recibe el evento con el nombre del archivo y el bucket.
2. Descarga la imagen original desde GCS.
3. Redimensiona la imagen a un máximo de 300×300 px.
4. Guarda la miniatura en formato JPEG en `thumbnails/<archivo>`.

---

## 4. `etiquetas_imagen_vision` — Etiquetado con Vision AI y almacenamiento en BigQuery

**Archivo:** `vision_biquery/main.py`

Analiza cada imagen con la API de **Cloud Vision** para obtener etiquetas descriptivas (ej. "perro", "playa", "auto"). Luego inserta cada etiqueta detectada como un registro en una tabla de **BigQuery**, junto con el nombre del archivo, el bucket, la puntuación de confianza y la marca de tiempo.

**Dataset y tabla de destino en BigQuery:**

- Dataset: `vision_data`
- Tabla: `etiquetas_imagen`

**Esquema de la tabla:**

| Campo       | Tipo      | Modo     |
| ----------- | --------- | -------- |
| `file_name` | STRING    | REQUIRED |
| `bucket`    | STRING    | REQUIRED |
| `label`     | STRING    | REQUIRED |
| `score`     | FLOAT64   | REQUIRED |
| `timestamp` | TIMESTAMP | REQUIRED |

**Flujo:**

1. Recibe el evento con el nombre del archivo y el bucket.
2. Llama a `label_detection` de Vision AI.
3. Por cada etiqueta detectada, construye un registro con nombre, bucket, etiqueta, puntuación y timestamp.
4. Inserta todos los registros en BigQuery con `insert_rows_json`.

---

## Resumen comparativo

| Función                   | Trigger         | Servicio usado           | Salida                               |
| ------------------------- | --------------- | ------------------------ | ------------------------------------ |
| `moderar_imagen`          | Subida a bucket | Vision AI, Cloud Storage | Imagen (con blur o sin) en `vision/` |
| `detectar_rostros`        | Subida a bucket | Vision AI, Cloud Storage | Imagen anotada en `rostros/`         |
| `crear_thumbnail`         | Subida a bucket | Cloud Storage            | Miniatura en `thumbnails/`           |
| `etiquetas_imagen_vision` | Subida a bucket | Vision AI, BigQuery      | Registros en tabla de BigQuery       |
