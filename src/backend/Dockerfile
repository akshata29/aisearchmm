FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
		build-essential \
		curl \
		ca-certificates \
	&& rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python deps (including gunicorn)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy application source
COPY . .

# Expose port configured via environment (default 8080)
EXPOSE 8080

# Use Gunicorn with aiohttp worker to run the app (wsgi.py creates the app instance)
ENV PORT=8080
CMD ["gunicorn", "wsgi:app", "-k", "aiohttp.GunicornWebWorker", "-b", "0.0.0.0:8080", "--workers", "1"]
