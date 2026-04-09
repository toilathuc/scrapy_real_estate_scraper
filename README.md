# Scrapy Real Estate Scraper

## 1. Mo ta du an
Du an thu thap du lieu bat dong san tu nhieu thanh pho, lam sach du lieu, xuat CSV, va co the luu vao PostgreSQL neu bat che do DB.

Spider hien co:
- `london`
- `paris`
- `madrid`
- `rome`
- `lisbon`

## 2. Cau truc chinh
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

## 3. Luong xu ly du lieu
1. Spider crawl listing page.
2. Spider vao tung detail page lay: `price`, `city`, `address`, `property_size`, `property_type`, `amenities`, `listing_url`.
3. `items.py` lam sach du lieu (gia, dien tich, dia chi).
4. Pipeline:
- `SCRAPER_USE_POSTGRES=0`: bo qua DB, chi xuat CSV.
- `SCRAPER_USE_POSTGRES=1`: ghi vao PostgreSQL.
5. CSV xuat ra thu muc `real_estate_scraper/output/`.

## 4. Setup local (khong Docker)

### 4.1 Tao va kich hoat virtual environment (PowerShell)
```powershell
cd "E:\Viscode\real state"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 4.2 Cai dependencies
```powershell
cd "E:\Viscode\real state\scrapy_real_estate_scraper\real_estate_scraper"
pip install -r requirements.txt
```

### 4.3 Chay 1 spider
```powershell
python -m scrapy crawl london
```

### 4.4 Chay tat ca spider
```powershell
python run_spiders.py
```

### 4.5 Thoat virtual environment
```powershell
deactivate
```

## 5. Setup Docker

### 5.1 Build image
```powershell
cd "E:\Viscode\real state\scrapy_real_estate_scraper\real_estate_scraper"
docker build -t real-estate-scraper .
```

Ghi chu:
- Build dau tien co the lau (do cai them Playwright + Chromium + Airflow dependencies).

### 5.2 Chay 1 spider va luu file ve host
```powershell
docker run --rm -e SCRAPER_USE_POSTGRES=0 -v "${PWD}\output:/app/output" real-estate-scraper python -m scrapy crawl london
```

### 5.3 Chay tat ca spider
```powershell
docker run --rm -e SCRAPER_USE_POSTGRES=0 -v "${PWD}\output:/app/output" real-estate-scraper
```

## 6. Bat che do PostgreSQL (tuy chon)
Can set cac bien moi truong:
- `SCRAPER_USE_POSTGRES=1`
- `DB_HOST`
- `DB_USER`
- `DB_PASSWORD`
- `DB_NAME`

Vi du:
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

## 7. Madrid anti-bot va proxy
Nguon `madrid` de bi 403 (bot block).

Da tich hop:
- `madrid` dung Playwright.
- Middleware xoay proxy qua bien `MADRID_PROXY_POOL`.

Format proxy pool:
```text
http://user:pass@proxy1:8000,http://user:pass@proxy2:8000
```

Lenh chay Madrid voi proxy:
```powershell
$env:MADRID_PROXY_POOL="http://user:pass@proxy1:8000,http://user:pass@proxy2:8000"
docker run --rm -e SCRAPER_USE_POSTGRES=0 -e MADRID_PROXY_POOL="$env:MADRID_PROXY_POOL" -v "${PWD}\output:/app/output" real-estate-scraper python -m scrapy crawl madrid
```

Neu van 403:
- Kiem tra proxy pool co gia tri that (`$env:MADRID_PROXY_POOL`).
- Dung residential proxy chat luong cao hon.
- Uu tien crawl `london`/`rome` de dam bao co du lieu on dinh.

## 8. Testing
```powershell
cd "E:\Viscode\real state\scrapy_real_estate_scraper\real_estate_scraper"
python -m unittest discover tests
```

## 9. Git workflow cho team

### 9.1 Kiem tra thay doi
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

## 10. Loi thuong gap

### 10.1 `docker: command not recognized`
- Chua co Docker trong PATH hoac chua mo terminal moi.

### 10.2 `failed to connect to docker API`
- Docker daemon chua running. Mo Docker Desktop, doi Engine Running roi thu lai.

### 10.3 `Scrapy ... no active project`
- Chay sai thu muc hoac thieu `scrapy.cfg`.
- Du an nay can chay trong repo `scrapy_real_estate_scraper`.

### 10.4 `403 Forbidden` o Madrid
- Day la block tu website, khong phai loi parser.
- Thu proxy chat luong cao hon hoac chuyen nguon de crawl truoc.

## 11. Luu y quan trong
- Ton trong Terms of Service va robots rules cua tung website.
- Selector co the can cap nhat dinh ky khi website doi giao dien.

## 12. License
MIT. Xem file `LICENSE`.


