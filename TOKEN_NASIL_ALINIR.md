# GitHub Token Nasıl Alınır - ADIM ADIM

## YOL 1: GitHub Ayarlarından (EN KOLAY)

### Adım 1: GitHub'a Giriş Yap
1. https://github.com adresine git
2. Sağ üstte profil resmin var mı? Varsa giriş yapmışsın ✅

### Adım 2: Ayarlara Git
1. Sağ üstte **profil resmin**e tıkla
2. Açılan menüden **"Settings"** seç

### Adım 3: Developer Settings
1. Sol menüde en alta kaydır
2. **"Developer settings"** seç (en altta)

### Adım 4: Personal Access Tokens
1. Sol menüden **"Personal access tokens"** seç
2. **"Tokens (classic)"** seç (veya direkt "Tokens" varsa onu)

### Adım 5: Yeni Token Oluştur
1. **"Generate new token"** butonuna tıkla
2. **"Generate new token (classic)"** seç
3. Formu doldur:
   - **Note:** `galopcu-predictor` yaz
   - **Expiration:** 90 days (veya istediğin süre)
   - **Select scopes:** Aşağıdakileri işaretle:
     - ✅ `repo` (tüm repo seçenekleri)
     - ✅ `workflow` (varsa)
4. En alta kaydır, **"Generate token"** butonuna tıkla

### Adım 6: Token'ı Kopyala
- Yeşil kutuda token görünecek
- **HEMEN KOPYALA!** (bir daha gösterilmeyecek)
- `ghp_xxxxxxxxxxxxxxxxxxxx` şeklinde bir şey olacak

---

## YOL 2: Direkt Link (Eğer Yukarıdaki Çalışmazsa)

Bu linki dene:
```
https://github.com/settings/tokens/new
```

Veya:
```
https://github.com/settings/personal-access-tokens/new
```

---

## YOL 3: GitHub CLI Kullan (Alternatif)

Eğer token bulamazsan, GitHub CLI ile de yapabiliriz ama daha karmaşık.

---

## SORUN MU VAR?

Eğer hala bulamıyorsan:
1. GitHub'a giriş yaptın mı? (sağ üstte profil resmin görünüyor mu?)
2. Hangi sayfadasın? Ekran görüntüsü alıp paylaşabilir misin?
3. "Settings" sayfasında "Developer settings" görünüyor mu?

