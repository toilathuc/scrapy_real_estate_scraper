# Huong Dan Crawl Du Lieu Batdongsan (Commit Hien Tai)

Tai lieu nay dung cho **commit hien tai** (ban CauGiay.py cu), noi README chua ghi day du luong chay script `real_estate_scraper/spiders/CauGiay.py`.

## 1) Dieu kien

- Windows + PowerShell.
- Khuyen nghi Python **3.12** (de on dinh voi crawl4ai).
- Dang o dung repo:

```powershell
cd "E:\Viscode\real state\scrapy_real_estate_scraper"
```

## 2) Tao moi truong ao

Neu chua co `.venv312`:

```powershell
py -3.12 -m venv .venv312
.\.venv312\Scripts\Activate.ps1
```

Neu da co roi:

```powershell
.\.venv312\Scripts\Activate.ps1
```

## 3) Cai thu vien can thiet

```powershell
python -m pip install -U pip setuptools wheel
python -m pip install crawl4ai playwright
python -m playwright install chromium
```

Neu script bao thieu package khac:

```powershell
python -m pip install -r real_estate_scraper/requirements.txt
```

## 4) Kiem tra file cau hinh URL crawl mac dinh

File: `real_estate_scraper/spiders/crawler_config.json`

Vi du:

```json
{
  "start_url": "https://batdongsan.com.vn/nha-dat-ban-cau-giay"
}
```

Luu y: o commit nay script co the nhan `--start-url`, nen khong bat buoc sua file config moi lan.

## 5) Crawl theo tung quan (muc tieu 500 dong/quan)

Khuyen nghi moi quan dung **1 file output rieng** de de resume va de kiem soat trung lap.

Mau lenh:

```powershell
python real_estate_scraper/spiders/CauGiay.py --resume --start-url "<URL_QUAN>" --max-pages 60 --max-items 500 --output "real_estate_scraper/output/<ten_quan>_500.csv"
```

### 5.1 Cau Giay

```powershell
python real_estate_scraper/spiders/CauGiay.py --resume --start-url "https://batdongsan.com.vn/nha-dat-ban-cau-giay" --max-pages 60 --max-items 500 --output "real_estate_scraper/output/caugiay_500.csv"
```

### 5.2 Dong Da

```powershell
python real_estate_scraper/spiders/CauGiay.py --resume --start-url "https://batdongsan.com.vn/nha-dat-ban-dong-da" --max-pages 60 --max-items 500 --output "real_estate_scraper/output/dongda_500.csv"
```

### 5.3 Ba Dinh

```powershell
python real_estate_scraper/spiders/CauGiay.py --resume --start-url "https://batdongsan.com.vn/nha-dat-ban-ba-dinh" --max-pages 60 --max-items 500 --output "real_estate_scraper/output/badinh_500.csv"
```

### 5.4 Thanh Xuan

```powershell
python real_estate_scraper/spiders/CauGiay.py --resume --start-url "https://batdongsan.com.vn/nha-dat-ban-thanh-xuan" --max-pages 60 --max-items 500 --output "real_estate_scraper/output/thanhxuan_500.csv"
```

### 5.5 Hoang Mai

```powershell
python real_estate_scraper/spiders/CauGiay.py --resume --start-url "https://batdongsan.com.vn/nha-dat-ban-hoang-mai" --max-pages 60 --max-items 500 --output "real_estate_scraper/output/hoangmai_500.csv"
```

## 6) Kiem tra da dat 500 dong chua

Dem so dong trong file CSV (tru 1 dong header):

```powershell
$path = "real_estate_scraper/output/caugiay_500.csv"
((Get-Content $path).Count - 1)
```

Kiem tra nhanh 5 dong dau:

```powershell
Get-Content "real_estate_scraper/output/caugiay_500.csv" -TotalCount 6
```

## 7) Cach chay lai de lay them du lieu moi

Script o commit nay co `--resume` de bo qua `listing_url` da co trong file output.

Chay lai cung 1 file output:

```powershell
python real_estate_scraper/spiders/CauGiay.py --resume --start-url "https://batdongsan.com.vn/nha-dat-ban-cau-giay" --max-pages 60 --max-items 500 --output "real_estate_scraper/output/caugiay_500.csv"
```

Neu log bao `No new links to crawl.` thi co the:

- Tang `--max-pages` (vi du 80 hoac 100).
- Doi khung gio chay.
- Chay lai sau mot thoi gian de co tin moi.

## 8) Luu y de giam bi chan

- Chay theo lo nho (moi quan 300-500, khong nen qua lon 1 lan).
- Khong chay qua nhieu command song song.
- Uu tien giu 1 IP/moi truong on dinh trong mot phien.
- Neu thay title la "Just a moment..." hoac N/A qua nhieu, nen dung va chay lai sau.

## 9) Thu muc output khuyen nghi

Tat ca file ket qua dat tai:

- `real_estate_scraper/output/`

Dat ten file theo mau:

- `<quan>_500.csv`
- `<quan>_run2.csv` (neu muon tach dot crawl)

