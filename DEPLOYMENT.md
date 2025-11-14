# Canlıya Alma (Deployment) Rehberi

## 🚀 HIZLI BAŞLANGIÇ - Render.com (ÜCRETSİZ)

### ADIM ADIM REHBER:

#### 1. GitHub'a Yükle (5 dakika)

Terminal'de proje klasöründe şu komutları çalıştır:

```bash
# Git'i başlat (eğer yoksa)
git init

# Tüm dosyaları ekle
git add .

# İlk commit
git commit -m "İlk versiyon - canlıya alınacak"

# GitHub'da yeni repo oluştur:
# 1. https://github.com adresine git
# 2. Sağ üstte "+" > "New repository"
# 3. Repo adı: "galopcu-predictor" (veya istediğin isim)
# 4. "Create repository" butonuna tıkla
# 5. GitHub sana komutlar gösterecek, şu komutu çalıştır:
#    git remote add origin https://github.com/KULLANICI_ADIN/galopcu-predictor.git
#    (KULLANICI_ADIN yerine GitHub kullanıcı adını yaz)

# Dosyaları GitHub'a yükle
git branch -M main
git push -u origin main
```

#### 2. Render.com'a Kayıt Ol (2 dakika)

1. https://render.com adresine git
2. "Get Started for Free" butonuna tıkla
3. GitHub hesabınla giriş yap (en kolay yol)

#### 3. Render'da Web Service Oluştur (5 dakika)

1. Render dashboard'da "New +" butonuna tıkla
2. "Web Service" seç
3. GitHub repo'nu seç (az önce yüklediğin repo)
4. Ayarları doldur:
   - **Name:** `galopcu-predictor` (veya istediğin isim)
   - **Region:** `Frankfurt` (Türkiye'ye en yakın)
   - **Branch:** `main`
   - **Root Directory:** (boş bırak)
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn web_app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
   - **Plan:** `Free` seç

5. "Create Web Service" butonuna tıkla

#### 4. Bekle ve Test Et (5-10 dakika)

- Render otomatik olarak build başlatır
- İlk build 5-10 dakika sürebilir
- Build tamamlandığında URL verilecek: `https://galopcu-predictor.onrender.com`
- URL'yi tarayıcıda aç ve test et!

#### ✅ BAŞARILI! Artık herkes kullanabilir!

---

## Seçenek 1: Render.com (ÖNERİLEN - Ücretsiz)

### Adımlar:
1. **GitHub'a Yükle:**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/KULLANICI_ADI/REPO_ADI.git
   git push -u origin main
   ```

2. **Render.com'a Git:**
   - https://render.com adresine git
   - "New" > "Web Service" seç
   - GitHub repo'yu bağla
   - Ayarlar:
     - **Build Command:** `pip install -r requirements.txt`
     - **Start Command:** `gunicorn web_app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
     - **Environment:** Python 3
     - **Plan:** Free (ücretsiz)

3. **Deploy Et:**
   - "Create Web Service" butonuna tıkla
   - İlk build 5-10 dakika sürebilir
   - URL: `https://PROJE_ADI.onrender.com`

### Notlar:
- Ücretsiz plan: 15 dakika kullanılmazsa uyku moduna geçer
- İlk istekte 30-60 saniye uyanma süresi olabilir
- 750 saat/ay ücretsiz

---

## Seçenek 2: Railway.app

### Adımlar:
1. **GitHub'a Yükle** (yukarıdaki gibi)

2. **Railway'a Git:**
   - https://railway.app adresine git
   - "New Project" > "Deploy from GitHub repo"
   - Repo'yu seç

3. **Ayarlar:**
   - Railway otomatik algılar
   - $5/ay ücretli plan gerekebilir (daha stabil)

---

## Seçenek 3: VPS (DigitalOcean, AWS, vb.)

### DigitalOcean Droplet:
1. **Droplet Oluştur:**
   - Ubuntu 22.04
   - En az 2GB RAM

2. **Sunucuya Bağlan:**
   ```bash
   ssh root@SUNUCU_IP
   ```

3. **Gerekli Paketleri Kur:**
   ```bash
   apt update
   apt install python3-pip python3-venv nginx git -y
   ```

4. **Projeyi Kopyala:**
   ```bash
   cd /var/www
   git clone https://github.com/KULLANICI_ADI/REPO_ADI.git
   cd REPO_ADI
   ```

5. **Python Environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

6. **Systemd Service Oluştur:**
   ```bash
   sudo nano /etc/systemd/system/galopcu.service
   ```
   
   İçerik:
   ```ini
   [Unit]
   Description=Galopcu Predictor Web App
   After=network.target

   [Service]
   User=www-data
   WorkingDirectory=/var/www/REPO_ADI
   Environment="PATH=/var/www/REPO_ADI/venv/bin"
   ExecStart=/var/www/REPO_ADI/venv/bin/gunicorn web_app:app --bind 127.0.0.1:5001 --workers 2

   [Install]
   WantedBy=multi-user.target
   ```

7. **Servisi Başlat:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl start galopcu
   sudo systemctl enable galopcu
   ```

8. **Nginx Konfigürasyonu:**
   ```bash
   sudo nano /etc/nginx/sites-available/galopcu
   ```
   
   İçerik:
   ```nginx
   server {
       listen 80;
       server_name DOMAIN_ADI.com;

       location / {
           proxy_pass http://127.0.0.1:5001;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

   ```bash
   sudo ln -s /etc/nginx/sites-available/galopcu /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl restart nginx
   ```

---

## Önemli Notlar:

1. **Environment Variables:**
   - Production'da `FLASK_ENV=production` ayarla
   - Gerekirse API key'leri environment variable olarak ekle

2. **Dosya Yolları:**
   - `data/` klasörü ve `output/` klasörü için yazma izinleri gerekli
   - Render/Railway'de geçici depolama kullanılır

3. **Scheduler:**
   - APScheduler production'da çalışır
   - Heroku/Render'da uyku modunda durur (çözüm: external cron job)

4. **Statik Dosyalar:**
   - `static/` klasörü otomatik servis edilir
   - Production'da CDN kullanmak daha iyi

---

## Hızlı Test:

Lokalde production modunda test:
```bash
export FLASK_ENV=production
gunicorn web_app:app --bind 0.0.0.0:5001 --workers 2
```

---

## Sorun Giderme:

- **Port Hatası:** `$PORT` environment variable'ını kontrol et
- **Dosya Yazma Hatası:** `data/` ve `output/` klasörlerine yazma izni ver
- **Memory Hatası:** Worker sayısını azalt veya daha fazla RAM al

