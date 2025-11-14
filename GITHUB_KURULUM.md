# GitHub Hesabı Oluşturma ve Proje Yükleme - ÇOK KOLAY REHBER

## 🎯 ADIM ADIM (5 DAKİKA)

### ADIM 1: GitHub Hesabı Oluştur (2 dakika)

1. **Tarayıcıda şu adrese git:**
   ```
   https://github.com/signup
   ```

2. **Bilgilerini doldur:**
   - **Username:** Bir kullanıcı adı seç (örn: `ardagalopcu` veya `galopcu-predictor`)
   - **Email:** Email adresini yaz
   - **Password:** Güçlü bir şifre oluştur
   - "Create account" butonuna tıkla

3. **Email doğrulama:**
   - Email'ine gelen doğrulama linkine tıkla
   - GitHub hesabın hazır! ✅

---

### ADIM 2: Yeni Repo Oluştur (1 dakika)

1. **GitHub'a giriş yap:**
   - https://github.com adresine git
   - Sağ üstte profil resmin görünecek

2. **Yeni repo oluştur:**
   - Sağ üstte **"+"** işaretine tıkla
   - **"New repository"** seç

3. **Repo bilgilerini doldur:**
   - **Repository name:** `galopcu-predictor` (veya istediğin isim)
   - **Description:** (boş bırakabilirsin)
   - **Public** seç (ücretsiz için)
   - **"Create repository"** butonuna tıkla

4. **ÖNEMLİ:** Bir sonraki sayfada GitHub sana komutlar gösterecek, **ŞİMDİLİK KAPAT**, terminal'den yapacağız.

---

### ADIM 3: Terminal'den Projeyi Yükle (2 dakika)

Terminal'de şu komutları sırayla çalıştır (her satırı Enter'a bas):

```bash
# 1. Proje klasörüne git
cd "/Users/ardaozturk/galopcu_predictor web calisan 7 model kopyası 2"

# 2. Git'i başlat
git init

# 3. Tüm dosyaları ekle
git add .

# 4. İlk kayıt
git commit -m "İlk versiyon"

# 5. Ana branch'i ayarla
git branch -M main

# 6. GitHub repo'yu bağla (KULLANICI_ADIN yerine GitHub kullanıcı adını yaz!)
git remote add origin https://github.com/KULLANICI_ADIN/galopcu-predictor.git

# 7. Dosyaları yükle
git push -u origin main
```

**NOT:** 6. adımda GitHub kullanıcı adını yazman gerekiyor. Örneğin kullanıcı adın `ardagalopcu` ise:
```bash
git remote add origin https://github.com/ardagalopcu/galopcu-predictor.git
```

**7. adımda şifre isteyebilir:**
- GitHub şifreni yaz (görünmeyecek, normal)
- Veya Personal Access Token isteyebilir (aşağıda anlatıyorum)

---

### ADIM 4: Personal Access Token (Eğer Şifre Çalışmazsa)

GitHub artık şifre kabul etmiyor, token gerekiyor:

1. **GitHub'da token oluştur:**
   - GitHub'a git → Sağ üstte profil resmin → **Settings**
   - Sol menüden **Developer settings**
   - **Personal access tokens** → **Tokens (classic)**
   - **Generate new token** → **Generate new token (classic)**
   - **Note:** `galopcu-predictor` yaz
   - **Expiration:** 90 days (veya istediğin süre)
   - **Scopes:** `repo` işaretle (tüm repo seçenekleri)
   - **Generate token** butonuna tıkla
   - **ÖNEMLİ:** Token'ı kopyala (bir daha gösterilmeyecek!)

2. **Terminal'de token kullan:**
   ```bash
   git push -u origin main
   ```
   - Username: GitHub kullanıcı adın
   - Password: Token'ı yapıştır (şifre değil, token!)

---

## ✅ BAŞARILI!

Eğer her şey tamamlandıysa:
- GitHub'da repo'nu aç: `https://github.com/KULLANICI_ADIN/galopcu-predictor`
- Dosyaların orada görünecek
- Artık Render.com'a bağlayabilirsin!

---

## 🆘 SORUN MU VAR?

### "fatal: remote origin already exists" hatası:
```bash
git remote remove origin
git remote add origin https://github.com/KULLANICI_ADIN/galopcu-predictor.git
```

### "Permission denied" hatası:
- Token oluştur ve kullan (yukarıdaki ADIM 4)

### Başka sorun:
- Terminal'deki hata mesajını kopyala, bana gönder

