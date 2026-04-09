# Use Python 3.11-slim as base for better performance and smaller size
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV FLASK_APP=backend/app.py
ENV PORT=10000

# Install system dependencies
# - tesseract-ocr: for medical report OCR
# - poppler-utils: for PDF to image conversion
# - libgl1-mesa-glx, libglib2.0-0: for OpenCV (cv2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirement file from backend first to leverage Docker cache
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project
COPY . .

# Ensure upload directory exists
RUN mkdir -p backend/uploads

# Expose the port Render expects
EXPOSE 10000

# Run with Gunicorn for production
# Using --timeout 120 because OCR/Plotly generation can take time
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--timeout", "120", "--workers", "2", "wsgi:app"]
