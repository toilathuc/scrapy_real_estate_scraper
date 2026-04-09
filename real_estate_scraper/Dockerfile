FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV SCRAPY_SETTINGS_MODULE=real_estate_scraper.settings

WORKDIR /app

# Install Python dependencies first to leverage Docker layer caching.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
	&& pip install --no-cache-dir -r /app/requirements.txt \
	&& playwright install --with-deps chromium

# Copy scraper source code under its package name.
COPY . /app/real_estate_scraper

# Disable PostgreSQL writes by default so local container runs do not fail
# when DB is not provided. Override at runtime with SCRAPER_USE_POSTGRES=1.
ENV SCRAPER_USE_POSTGRES=0

# Default command runs all spiders sequentially.
CMD ["python", "real_estate_scraper/run_spiders.py"]
