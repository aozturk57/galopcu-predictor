# Render.com'a Yükleme - ADIM ADIM (5 DAKİKA)

## ✅ ADIM 1: Render.com'a Kayıt Ol (2 dakika)

1. **Render.com'a git:**
   - https://render.com adresine git

2. **Kayıt ol:**
   - "Get Started for Free" butonuna tıkla
   - **"Sign in with GitHub"** seç (en kolay yol)
   - GitHub hesabınla giriş yap (`aozturk57`)

3. **Yetkilendir:**
   - GitHub, Render'a erişim izni isteyecek
   - "Authorize render" butonuna tıkla

---

## ✅ ADIM 2: Web Service Oluştur (3 dakika)

1. **Render Dashboard'da:**
   - Sağ üstte **"New +"** butonuna tıkla
   - **"Web Service"** seç

2. **GitHub Repo'yu Bağla:**
   - GitHub hesabını seç
   - **"galopcu-predictor"** repo'sunu seç
   - "Connect" butonuna tıkla

3. **Ayarları Doldur:**
   - **Name:** `galopcu-predictor` (otomatik dolu olabilir)
   - **Region:** `Frankfurt` seç (Türkiye'ye en yakın)
   - **Branch:** `main` (otomatik)
   - **Root Directory:** (boş bırak)
   - **Environment:** `Python 3` seç
   - **Build Command:** `pip install -r requirements.txt` (otomatik dolu olabilir)
   - **Start Command:** `gunicorn web_app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120` (otomatik dolu olabilir - Procfile sayesinde)
   - **Plan:** `Free` seç (ücretsiz)

4. **Deploy Et:**
   - En alta kaydır
   - **"Create Web Service"** butonuna tıkla

---

## ✅ ADIM 3: Bekle ve Test Et (5-10 dakika)

1. **Build Başlar:**
   - Render otomatik olarak build başlatır
   - İlk build 5-10 dakika sürebilir (ML kütüphaneleri büyük)
   - Log'ları izleyebilirsin

2. **Build Tamamlandığında:**
   - Yeşil "Live" yazısı görünecek
   - URL verilecek: `https://galopcu-predictor.onrender.com`
   - URL'yi tarayıcıda aç ve test et!

---

## ✅ BAŞARILI! 🎉

Artık siten canlıda! Herkes kullanabilir:
- **URL:** `https://galopcu-predictor.onrender.com`
- **Otomatik Güncelleme:** Her sabah 07:00'da çalışacak

---

## ⚠️ ÖNEMLİ NOTLAR:

### Ücretsiz Plan:
- 15 dakika kullanılmazsa uyku moduna geçer
- İlk istekte 30-60 saniye uyanma süresi olabilir
- 750 saat/ay ücretsiz (yeterli)

### Ücretli Plan ($7/ay):
- Sürekli çalışır (uyku modu yok)
- Daha hızlı
- Sınırsız saat

---

## 🆘 SORUN MU VAR?

### Build Hatası:
- Log'ları kontrol et
- `requirements.txt` dosyası doğru mu?
- Memory limiti yeterli mi?

### Site Açılmıyor:
- Build tamamlandı mı? (yeşil "Live" yazısı var mı?)
- URL doğru mu?
- Birkaç dakika bekle, ilk başlatma uzun sürebilir

### Başka Sorun:
- Render dashboard'da "Logs" sekmesine bak
- Hata mesajını kopyala, bana gönder

