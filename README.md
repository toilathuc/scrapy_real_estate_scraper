# Scrapy Real Estate Scraper

## 1. Project Description

This project collects real estate data from multiple cities, cleans and normalizes it, exports CSV files, and can optionally write to PostgreSQL.

Available spiders:

- `london`
- `paris`
- `madrid`
- `rome`
- `lisbon`

## 2. Main Structure

```
scrapy_real_estate_scraper/
	scrapy.cfg
	README.md
	.gitignore
	real_estate_scraper/
		Dockerfile
		docker-compose.yaml
		requirements.txt
		settings.py
		items.py
		pipelines.py
		middlewares.py
		run_spiders.py
		spiders/
		tests/
		dags/
		output/
```

## 3. Data Processing Flow

1. A spider crawls listing pages.
2. It visits each detail page and extracts: `price`, `city`, `address`, `property_size`, `property_type`, `amenities`, `listing_url`.
3. `items.py` cleans the extracted values (price, size, address).
4. Pipeline behavior:

- `SCRAPER_USE_POSTGRES=0`: skip database writes, export CSV only.
- `SCRAPER_USE_POSTGRES=1`: write data to PostgreSQL.

5. CSV files are written to `real_estate_scraper/output/`.

## 4. Local Setup (without Docker)

### 4.1 Create and activate virtual environment (PowerShell)

```powershell
cd "E:\Viscode\real state"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 4.2 Install dependencies

```powershell
cd "E:\Viscode\real state\scrapy_real_estate_scraper\real_estate_scraper"
pip install -r requirements.txt
```

### 4.3 Run one spider

```powershell
python -m scrapy crawl london
```

### 4.4 Run all spiders

```powershell
python run_spiders.py
```

### 4.5 Exit virtual environment

```powershell
deactivate
```

## 5. Docker Setup

### 5.1 Build image

```powershell
cd "E:\Viscode\real state\scrapy_real_estate_scraper\real_estate_scraper"
docker build -t real-estate-scraper .
```

Note:

- The first build can take a while because it installs Playwright, Chromium, and Airflow dependencies.

### 5.2 Run one spider and save output on host

```powershell
docker run --rm -e SCRAPER_USE_POSTGRES=0 -v "${PWD}\output:/app/output" real-estate-scraper python -m scrapy crawl london
```

### 5.3 Run all spiders

```powershell
docker run --rm -e SCRAPER_USE_POSTGRES=0 -v "${PWD}\output:/app/output" real-estate-scraper
```

## 6. Enable PostgreSQL Mode (optional)

Set these environment variables:

- `SCRAPER_USE_POSTGRES=1`
- `DB_HOST`
- `DB_USER`
- `DB_PASSWORD`
- `DB_NAME`

Example:

```powershell
docker run --rm `
	-e SCRAPER_USE_POSTGRES=1 `
	-e DB_HOST=host.docker.internal `
	-e DB_USER=postgres `
	-e DB_PASSWORD=your_password `
	-e DB_NAME=realestate `
	-v "${PWD}\output:/app/output" `
	real-estate-scraper python -m scrapy crawl london
```

## 7. Madrid Anti-Bot and Proxy

The `madrid` source is more likely to return `403` (bot blocking).

Current mitigation:

- `madrid` uses Playwright.
- Proxy rotation middleware is available via `MADRID_PROXY_POOL`.

Proxy pool format:

```text
http://user:pass@proxy1:8000,http://user:pass@proxy2:8000
```

Run Madrid with proxy:

```powershell
$env:MADRID_PROXY_POOL="http://user:pass@proxy1:8000,http://user:pass@proxy2:8000"
docker run --rm -e SCRAPER_USE_POSTGRES=0 -e MADRID_PROXY_POOL="$env:MADRID_PROXY_POOL" -v "${PWD}\output:/app/output" real-estate-scraper python -m scrapy crawl madrid
```

If `403` still happens:

- Verify the proxy pool has a real value (`$env:MADRID_PROXY_POOL`).
- Use higher-quality residential proxies.
- Prioritize `london`/`rome` for more stable collection.

## 8. Testing

```powershell
cd "E:\Viscode\real state\scrapy_real_estate_scraper\real_estate_scraper"
python -m unittest discover tests
```

## 9. Git Workflow for Team Collaboration

### 9.1 Check changes

```powershell
cd "E:\Viscode\real state\scrapy_real_estate_scraper"
git status
```

### 9.2 Commit

```powershell
git add .
git commit -m "Update scraper setup, Docker, Madrid Playwright, proxy rotation"
```

### 9.3 Push

```powershell
git push origin main
```

## 10. Common Issues

### 10.1 `docker: command not recognized`

- Docker is not in PATH, or the terminal was not restarted.

### 10.2 `failed to connect to docker API`

- Docker daemon is not running. Open Docker Desktop and wait for Engine Running.

### 10.3 `Scrapy ... no active project`

- You are running from the wrong directory or `scrapy.cfg` is missing.
- Run inside the `scrapy_real_estate_scraper` repository.

### 10.4 `403 Forbidden` on Madrid

- This is a target-site block, not a parser error.
- Use better proxies or switch to other sources first.

## 11. Important Notes

- Respect Terms of Service and robots rules for each target site.
- Selectors may need periodic updates when websites change their HTML.

## 12. License

MIT. See `LICENSE`.
