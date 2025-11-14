# Normal Hosting'e Yükleme Rehberi

## ⚠️ ÖNEMLİ: Bu Uygulama İçin Gereksinimler

Bu uygulama **Machine Learning** kütüphaneleri kullanıyor, bu yüzden bazı özel gereksinimler var:

### ✅ Çalışması İçin Gerekenler:

1. **Python 3.9+ Desteği**
   - Hosting'de Python 3.9 veya üzeri olmalı
   - cPanel'de genellikle "Python App" veya "Setup Python App" özelliği var

2. **pip ile Paket Kurulumu**
   - `pip install` komutunu çalıştırabilmen gerekiyor
   - Virtual environment (venv) desteği olmalı

3. **Yeterli Memory (RAM)**
   - **En az 512MB RAM** önerilir (ML modelleri için)
   - 256MB ile çalışabilir ama yavaş olabilir
   - 128MB ile muhtemelen çalışmaz

4. **Disk Alanı**
   - En az 500MB boş alan (ML kütüphaneleri büyük)
   - xgboost, scikit-learn, pandas, numpy gibi paketler 200-300MB yer kaplar

5. **WSGI Desteği**
   - Gunicorn veya mod_wsgi ile çalıştırılabilmeli
   - cPanel'de genellikle "Passenger" veya "mod_wsgi" var

6. **Sürekli Çalışan Process**
   - APScheduler için uygulama sürekli çalışmalı
   - Cron job desteği de olabilir (alternatif)

---

## 🎯 Hangi Hosting'lerde Çalışır?

### ✅ ÇALIŞIR:
- **cPanel + Python App** (çoğu modern cPanel hosting)
- **Plesk + Python** (Python desteği olan Plesk)
- **VPS/Cloud Server** (DigitalOcean, AWS, vb.)
- **Python-specific hosting** (PythonAnywhere, Heroku, Render)

### ❌ ÇALIŞMAYABİLİR:
- **Sadece PHP hosting** (Python desteği yok)
- **Çok eski shared hosting** (Python 2.7 veya hiç Python yok)
- **Çok düşük memory limitli hosting** (128MB altı)

---

## 📋 cPanel Hosting'e Yükleme Adımları

### 1. Python App Oluştur

1. cPanel'e gir
2. "Software" > "Setup Python App" veya "Python App" bul
3. "Create Application" butonuna tıkla
4. Ayarlar:
   - **Python Version:** 3.9 veya üzeri seç
   - **App Directory:** `public_html/galopcu` (veya istediğin klasör)
   - **App URL:** `/galopcu` (veya `/`)
   - **Startup File:** `web_app.py`
   - **Application Root:** `public_html/galopcu`

### 2. Dosyaları Yükle

1. FTP veya cPanel File Manager ile dosyaları yükle
2. Tüm proje dosyalarını `public_html/galopcu/` klasörüne kopyala

### 3. Virtual Environment Oluştur ve Paketleri Kur

cPanel Terminal'den veya SSH ile:

```bash
cd ~/public_html/galopcu

# Virtual environment oluştur
python3.9 -m venv venv

# Activate et
source venv/bin/activate

# Paketleri kur (bu 5-10 dakika sürebilir)
pip install --upgrade pip
pip install -r requirements.txt
```

**NOT:** ML kütüphaneleri büyük olduğu için kurulum uzun sürebilir. Eğer timeout olursa, hosting desteğine başvur.

### 4. WSGI Dosyası Oluştur

`public_html/galopcu/passenger_wsgi.py` dosyası oluştur:

```python
import sys
import os

# Virtual environment path
INTERP = os.path.expanduser("~/public_html/galopcu/venv/bin/python3.9")
if sys.executable != INTERP:
    os.execl(INTERP, INTERP, *sys.argv)

sys.path.append(os.getcwd())

from web_app import app as application

if __name__ == "__main__":
    application.run()
```

### 5. Dosya İzinlerini Ayarla

```bash
chmod 755 passenger_wsgi.py
chmod -R 755 public_html/galopcu
chmod -R 777 public_html/galopcu/data
chmod -R 777 public_html/galopcu/output
```

### 6. Python App'i Restart Et

cPanel'de "Setup Python App" bölümüne geri dön ve "Restart" butonuna tıkla.

---

## 🔧 Alternatif: Gunicorn ile Çalıştırma

Eğer Passenger çalışmazsa, Gunicorn kullan:

### `.htaccess` Dosyası Oluştur:

```apache
PassengerEnabled On
PassengerAppRoot /home/KULLANICI/public_html/galopcu
PassengerBaseURI /
PassengerPython /home/KULLANICI/public_html/galopcu/venv/bin/python3.9
```

### Veya `start.sh` Script:

```bash
#!/bin/bash
cd ~/public_html/galopcu
source venv/bin/activate
gunicorn web_app:app --bind 127.0.0.1:5001 --workers 1 --timeout 120
```

---

## ⚠️ Olası Sorunlar ve Çözümler

### 1. "Memory limit exceeded" Hatası

**Çözüm:**
- Hosting'de memory limitini artır (512MB+)
- Worker sayısını azalt: `--workers 1`
- Daha hafif ML modelleri kullan (ama performans düşer)

### 2. Paket Kurulumu Timeout Oluyor

**Çözüm:**
- SSH erişimi varsa terminal'den kur
- Paketleri tek tek kur: `pip install flask`, `pip install pandas`, vb.
- Hosting desteğine başvur, memory limitini artırsınlar

### 3. APScheduler Çalışmıyor

**Çözüm:**
- cPanel Cron Job kullan:
  ```
  0 7 * * * cd ~/public_html/galopcu && source venv/bin/activate && python3 daily_update.py
  ```
- Her sabah 07:00'da `daily_update.py` çalıştır

### 4. Dosya Yazma İzni Hatası

**Çözüm:**
```bash
chmod -R 777 data/
chmod -R 777 output/
```

---

## 🎯 Önerilen Hosting'ler

### 1. **PythonAnywhere** (ÖNERİLEN - Python için özel)
- ✅ Python desteği mükemmel
- ✅ Ücretsiz plan var
- ✅ Kolay kurulum
- ❌ Ücretsiz planda sınırlı

### 2. **DigitalOcean Droplet** ($6/ay)
- ✅ Tam kontrol
- ✅ Yeterli kaynak
- ✅ Kolay kurulum
- ❌ Biraz teknik bilgi gerekir

### 3. **Render.com** (ÜCRETSİZ)
- ✅ Python desteği mükemmel
- ✅ Otomatik deploy
- ✅ Ücretsiz plan
- ❌ 15 dakika kullanılmazsa uyku modu

### 4. **cPanel Hosting** (Python desteği olan)
- ✅ Tanıdık arayüz
- ✅ Domain yönetimi kolay
- ❌ ML kütüphaneleri için yeterli kaynak olmayabilir
- ❌ Kurulum biraz zor olabilir

---

## ✅ Test Etme

Kurulumdan sonra test et:

```bash
# Terminal'den
cd ~/public_html/galopcu
source venv/bin/activate
python3 web_app.py
```

Tarayıcıdan: `https://SENIN_DOMAIN.com/galopcu`

---

## 📞 Destek

Eğer sorun yaşarsan:
1. Hosting log dosyalarını kontrol et
2. Python version'ı kontrol et: `python3 --version`
3. Paketlerin kurulu olduğunu kontrol et: `pip list`
4. Hosting desteğine başvur (Python ve memory limiti için)

