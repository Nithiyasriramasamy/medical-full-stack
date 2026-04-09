FROM python:3.11-slim

# Install system dependencies
# - tesseract-ocr: for medical report OCR
# - poppler-utils: for PDF to image conversion
# - libgl1: Still useful for some image operations
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils \
    libgl1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy everything
COPY . .

# Run with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--timeout", "120", "--workers", "2", "wsgi:app"]
