import pandas as pd
import numpy as np
import os
import requests
from datetime import datetime

from sklearn.model_selection import GroupKFold
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, LabelEncoder
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import roc_auc_score, log_loss
import xgboost as xgb
from xgboost import XGBRanker

class HorseRacingPredictor:
    def __init__(self, hipodrom_key):
        self.hipodrom_key = hipodrom_key.upper()
        self.data_dir = "data"
        self.output_dir = "output"
        
        # TUTARLILIK İÇİN: Global random seed'leri ayarla (deterministik sonuçlar için)
        RANDOM_SEED = 42
        np.random.seed(RANDOM_SEED)
        import random
        random.seed(RANDOM_SEED)
        # XGBoost modelleri zaten random_state=42 parametresi ile ayarlanıyor (train_ensemble_models içinde)
        
        # Klasörleri oluştur (Render'da yazma izinleri için)
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            os.makedirs(self.output_dir, exist_ok=True)
            # Klasörlerin yazılabilir olduğunu test et
            test_file = os.path.join(self.data_dir, '.test_write')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            print(f"✅ Klasörler hazır: {self.data_dir}, {self.output_dir}")
        except Exception as e:
            print(f"⚠️ Klasör oluşturma/yazma testi hatası: {e}")
            # Yine de devam et, belki çalışır
        
        # Dosya yolları
        self.data_file = os.path.join(self.data_dir, f"{self.hipodrom_key}_races.csv")
        self.output_all = os.path.join(self.output_dir, f"{self.hipodrom_key}_predictions_all.csv")
        self.output_top3 = os.path.join(self.output_dir, f"{self.hipodrom_key}_predictions_top3.csv")
        
        # Model ve encoder'lar
        self.model = None
        self.label_encoders = {}
        self.feature_names = []
        self.numeric_medians = {}  # Training median'larını sakla
        # Kalibrasyon ayarları
        self.use_softmax_calibration = False
        self.softmax_temperature = 0.6
        # Meta-learner bağlam (pist/mesafe/sınıf) kullanımı
        self.use_meta_context = False
        # Koşu tipi bazlı sabit ağırlıklar kullanılsın mı?
        self.use_context_weights = True
        
    def download_data(self):
        """API'den veri indir"""
        print(f"📡 {self.hipodrom_key} verisi indiriliyor...")
        
        url = f"https://www.sanalganyan.com/api/v1/ai-daily-races?hipodrom_key={self.hipodrom_key}"
        
        try:
            response = requests.get(url)
            response.raise_for_status()
            
            # Response encoding'ini kontrol et ve düzelt
            response.encoding = response.apparent_encoding or 'utf-8'
            
            with open(self.data_file, 'w', encoding='utf-8') as f:
                f.write(response.text)
            
            print(f"✅ Veri indirildi: {self.data_file}")
            return True
            
        except Exception as e:
            print(f"❌ Veri indirme hatası: {e}")
            return False
    
    def load_data(self):
        """Veriyi yükle ve hazırla"""
        if not os.path.exists(self.data_file):
            print(f"❌ Veri dosyası bulunamadı: {self.data_file}")
            return None
        
        print(f"📊 {self.hipodrom_key} verisi yükleniyor...")
        
        # Farklı encoding'leri dene - Türkçe karakterler için optimize edilmiş
        encodings_to_try = ['utf-8', 'utf-8-sig', 'windows-1254', 'cp1254', 'latin-1', 'iso-8859-1']
        df = None
        best_encoding = None
        
        for encoding in encodings_to_try:
            try:
                test_df = pd.read_csv(self.data_file, engine="python", encoding=encoding)
                # Eğer başarılı okunduysa ve at_adi kolonu varsa kontrol et
                if 'at_adi' in test_df.columns and len(test_df) > 0:
                    # Türkçe karakter kontrolü - örnek isimleri kontrol et
                    sample_names = test_df['at_adi'].dropna().head(10).astype(str)
                    if len(sample_names) > 0:
                        # Problemli karakterleri kontrol et
                        problematic_chars = ['Ã', 'Ä', 'Å', 'Ã§', 'Ã¼', 'Ã¶', 'Ä±', 'ÅŸ', 'Ä°', 'ÄŸ']
                        problematic = any(any(char in str(name) for char in problematic_chars) for name in sample_names)
                        if not problematic:
                            df = test_df
                            best_encoding = encoding
                            print(f"✅ Encoding bulundu: {encoding}")
                            break
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        if df is None:
            # Son çare olarak errors='ignore' ile oku
            print("⚠️ Uygun encoding bulunamadı, errors='ignore' ile okunuyor...")
            df = pd.read_csv(self.data_file, engine="python", encoding='utf-8', errors='ignore')
        
        target_col = "sonuc"
        group_col = "yaris_kosu_key"
        
        # Sonuc sütununu numeric'e çevir (bugünün koşuları için boş olabilir)
        df[target_col] = pd.to_numeric(df[target_col], errors='coerce')
        
        # TUTARLILIK İÇİN: Data'yı deterministik sırala (aynı veri her zaman aynı sırada)
        # Sıralama: tarih -> yaris_kosu_key -> at_adi (veya mevcut sütunlar)
        sort_cols = []
        if 'tarih' in df.columns:
            sort_cols.append('tarih')
        if group_col in df.columns:
            sort_cols.append(group_col)
        if 'at_adi' in df.columns:
            sort_cols.append('at_adi')
        elif 'at_no' in df.columns:
            sort_cols.append('at_no')
        
        if sort_cols:
            df = df.sort_values(by=sort_cols, kind='mergesort').reset_index(drop=True)
        
        # SADECE geçmiş verileri kontrol et (bugünkü koşuları kaybetme)
        print(f"📊 Toplam veri: {len(df)} satır")
        if df[target_col].notna().sum() > 0:
            print(f"🏆 Kazananlar (geçmiş): {(df[target_col] == 1).sum()} ({(df[target_col] == 1).sum() / df[target_col].notna().sum()*100:.1f}%)")
        
        return df
    
    def split_train_predict(self, df):
        """Training ve prediction verilerini ayır"""
        print(f"📅 Training ve prediction verileri ayrılıyor...")
        
        # Bugünün tarihi
        today = datetime.now().strftime('%d/%m/%Y')
        
        # Tarih sütunu varsa ayır
        if 'tarih' in df.columns:
            # Bugünün koşularını ara
            today_races = df[df['tarih'] == today].copy()
            
            if len(today_races) > 0:
                print(f"✅ Bugünün koşuları bulundu: {len(today_races)} at")
                
                # Geçmiş veriler (training için) - BUGÜNÜN KOŞULARINI TAMAMEN ÇIKAR
                past_races = df[df['tarih'] != today].copy()
                past_races = past_races[past_races['sonuc'].notna()]  # Sadece sonucu olan koşular
                past_races = past_races[past_races['sonuc'] != '<nil>']  # nil değerleri de çıkar
                print(f"📊 Training verisi: {len(past_races)} at (geçmiş koşular - bugün hariç)")
                
                # Tarih sütununu kaldırma - form feature'ları için gerekiyor
                # Tarih prepare_features içinde drop edilecek
                
                return past_races, today_races
            else:
                print(f"⚠️ Bugün ({today}) için koşu bulunamadı!")
                print(f"📅 Tüm veri training için kullanılacak")
                
                # Tüm veriyi training için kullan
                df = df[df['sonuc'].notna()].copy()
                # Tarih prepare_features içinde drop edilecek
                return df, None
        else:
            print(f"⚠️ 'tarih' sütunu bulunamadı.")
            return df, None
    
    def create_advanced_features(self, df, skip_future_features=False, exclude_dates=None):
        """Gelişmiş feature'lar oluştur (iyileştirilmiş - mantıksız feature'lar çıkarıldı, önemli feature'lar eklendi)
        
        Args:
            df: Veri çerçevesi
            skip_future_features: Gelecekteki feature'ları (ganyan, agf1, agf2) atla
            exclude_dates: Feature hesaplamasından çıkarılacak tarihler listesi (bugünün tarihi gibi)
        """
        print(f"🔧 Gelişmiş feature'lar oluşturuluyor...")
        
        df = df.copy()

        # Sınıf ağırlığı yardımcı fonksiyonu (global kullanılacak)
        def _class_weight(c):
            s = str(c).upper()
            if 'G 1' in s or 'G1' in s:
                return 1.4
            if 'G 2' in s or 'G2' in s:
                return 1.2
            if 'G 3' in s or 'G3' in s:
                return 1.0
            if 'KV' in s:
                return 0.8
            if 'ŞARTLI' in s or 'SARTLI' in s:
                return 0.5
            if 'HANDIKAP' in s or 'HANDİKAP' in s:
                return 0.45
            if 'MAIDEN' in s:
                return 0.35
            if 'SATIŞ' in s or 'SATIS' in s:
                return 0.3
            return 0.4

        # Yarış sınıf bilgisini numerik olarak ekle (meta-learner bağlamı için de kullanılacak)
        if 'cins_detay' in df.columns and 'race_class_weight' not in df.columns:
            df['race_class_weight'] = df['cins_detay'].apply(_class_weight)
            df['race_is_high_class'] = (df['race_class_weight'] >= 0.8).astype(int)
        
        # Bugünün tarihini tespit et - exclude edilecek
        if exclude_dates is None:
            exclude_dates = []
            # Bugünün tarihini ekle (string formatında)
            today = datetime.now().strftime('%d/%m/%Y')
            exclude_dates.append(today)
        
        if len(exclude_dates) > 0:
            print(f"   🚫 Exclude edilecek tarihler: {exclude_dates}")
        
        # Tarih sütunu varsa datetime formatına çevir
        exclude_dates_dt = []
        if 'tarih' in df.columns:
            if 'tarih_dt' not in df.columns:
                df['tarih_dt'] = pd.to_datetime(df['tarih'], format='%d/%m/%Y', errors='coerce')
            # exclude_dates'i datetime formatına da çevir
            for date_str in exclude_dates:
                try:
                    dt = pd.to_datetime(date_str, format='%d/%m/%Y', errors='coerce')
                    if pd.notna(dt):
                        exclude_dates_dt.append(dt)
                except:
                    pass
        
        # Helper fonksiyon: df_with_result'ı exclude_dates'e göre filtrele
        def filter_exclude_dates(df_subset):
            """Bugünün tarihlerini (exclude_dates) çıkar"""
            original_len = len(df_subset)
            if len(exclude_dates) == 0:
                return df_subset
            if 'tarih' in df_subset.columns:
                before = len(df_subset)
                df_subset = df_subset[~df_subset['tarih'].isin(exclude_dates)].copy()
                after = len(df_subset)
                if before != after:
                    excluded = set(df_subset['tarih'].unique()) if len(df_subset) > 0 else set()
                    print(f"   🔍 filter_exclude_dates: {before} -> {after} satır (exclude_dates: {exclude_dates})")
            if len(exclude_dates_dt) > 0 and 'tarih_dt' in df_subset.columns:
                before = len(df_subset)
                df_subset = df_subset[~df_subset['tarih_dt'].isin(exclude_dates_dt)].copy()
                after = len(df_subset)
                if before != after:
                    print(f"   🔍 filter_exclude_dates (datetime): {before} -> {after} satır")
            if original_len != len(df_subset):
                print(f"   ✅ Toplam {original_len - len(df_subset)} satır exclude edildi")
            return df_subset
        
        # === TEMEL NUMERIC FEATURE'LAR ===
        # 1. Handikap (ne kadar yüksekse at o kadar güçlü)
        if 'handikap' in df.columns:
            df['handikap_numeric'] = pd.to_numeric(df['handikap'], errors='coerce')
            df['handikap_numeric'] = df['handikap_numeric'].fillna(df['handikap_numeric'].median())
        
        # 2. Kilo (handikap dengelensin diye eklenen ağırlık)
        if 'kilo' in df.columns:
            df['kilo_numeric'] = pd.to_numeric(df['kilo'], errors='coerce')
            df['kilo_numeric'] = df['kilo_numeric'].fillna(df['kilo_numeric'].median())
        
        # 3. Start pozisyonu (kulvar/başlangıç pozisyonu)
        if 'start' in df.columns:
            df['start_numeric'] = pd.to_numeric(df['start'], errors='coerce')
            df['start_numeric'] = df['start_numeric'].fillna(df['start_numeric'].median())
        
        # 4. Mesafe (metre cinsinden)
        if 'mesafe' in df.columns:
            df['mesafe_numeric'] = pd.to_numeric(df['mesafe'], errors='coerce')
            df['mesafe_numeric'] = df['mesafe_numeric'].fillna(df['mesafe_numeric'].median())
        
        # 5. KGS analizi (ideal 15 gün)
        if 'kgs' in df.columns:
            df['kgs_numeric'] = pd.to_numeric(df['kgs'], errors='coerce')
            df['kgs_numeric'] = df['kgs_numeric'].fillna(df['kgs_numeric'].median())
            # İdeal KGS'den uzaklık (ne kadar uzaksa o kadar kötü)
            df['kgs_ideal_fark'] = abs(df['kgs_numeric'] - 15)
        
        # 6. At yaşı
        if 'yas' in df.columns:
            df['yas_numeric'] = pd.to_numeric(df['yas'], errors='coerce')
            df['yas_numeric'] = df['yas_numeric'].fillna(df['yas_numeric'].median())
        
        # 7. Ganyan oranı - KALDIRILDI (model eğitimi ve tahminde kullanılmıyor)
        # if not skip_future_features and 'ganyan' in df.columns:
        #     df['ganyan_numeric'] = pd.to_numeric(df['ganyan'].astype(str).str.replace(',', '.'), errors='coerce')
        #     df['ganyan_numeric'] = df['ganyan_numeric'].fillna(df['ganyan_numeric'].median())
        
        # 8. AGF1 ve AGF2 analizi - KALDIRILDI (model eğitimi ve tahminde kullanılmıyor)
        # if not skip_future_features and 'agf1' in df.columns:
        #     df['agf1_numeric'] = pd.to_numeric(df['agf1'], errors='coerce')
        #     df['agf1_numeric'] = df['agf1_numeric'].fillna(df['agf1_numeric'].median())
        
        # if not skip_future_features and 'agf2' in df.columns:
        #     df['agf2_numeric'] = pd.to_numeric(df['agf2'], errors='coerce')
        #     df['agf2_numeric'] = df['agf2_numeric'].fillna(df['agf2_numeric'].median())
        
        # 9. En iyi derece analizi
        if 'en_iyi_derece' in df.columns:
            df['en_iyi_derece_numeric'] = pd.to_numeric(df['en_iyi_derece'], errors='coerce')
            df['en_iyi_derece_numeric'] = df['en_iyi_derece_numeric'].fillna(df['en_iyi_derece_numeric'].median())
        
        # 10. Son20 performans analizi
        if 'son20' in df.columns:
            df['son20_numeric'] = pd.to_numeric(df['son20'], errors='coerce')
            df['son20_numeric'] = df['son20_numeric'].fillna(df['son20_numeric'].median())
        
        # === SON6 FORM ANALİZİ (YENİ - ÇOK ÖNEMLİ) ===
        if 'son6' in df.columns and 'at_adi' in df.columns and 'sonuc' in df.columns:
            def parse_son6(son6_str):
                """Son6 form'u parse et ve ortalama dereceyi hesapla"""
                if pd.isna(son6_str) or not isinstance(son6_str, str):
                    return 0, 0  # form_puan, kazanma_sayisi
                
                # Son6 formatı: "C1C6K7C6C4C5" gibi (C=çim, K=kum, sayı=derece)
                # 0 en kötü (10. veya daha kötü), 1 en iyi (1.)
                dereceler = []
                i = 0
                while i < len(son6_str):
                    if son6_str[i] in ['C', 'K']:
                        if i + 1 < len(son6_str):
                            try:
                                derece = int(son6_str[i+1])
                                # 0 = 10. veya daha kötü, diğerleri direkt derece
                                if derece == 0:
                                    derece = 10
                                dereceler.append(derece)
                            except:
                                pass
                    i += 1
                
                if len(dereceler) == 0:
                    return 0, 0
                
                # Ortalama form puanı (düşük derece = iyi, yüksek derece = kötü)
                # 1. = 10 puan, 2. = 9 puan, ..., 10. = 1 puan
                form_puan = sum(max(0, 11 - d) for d in dereceler) / len(dereceler)
                kazanma_sayisi = sum(1 for d in dereceler if d == 1)
                
                return form_puan, kazanma_sayisi
            
            son6_features = df['son6'].apply(parse_son6)
            df['at_son6_form_puan'] = son6_features.apply(lambda x: x[0])
            df['at_son6_kazanma_sayisi'] = son6_features.apply(lambda x: x[1])
        
        # === AT BAŞARI FEATURE'LARI ===
        # 11. At-Pist-Mesafe kombinasyonu (en önemli kombinasyon)
        if 'pist' in df.columns and 'at_adi' in df.columns and 'mesafe' in df.columns and 'sonuc' in df.columns:
            # Sadece sonuc bilgisi olan satırları kullan (bugünün koşularını hariç tut)
            df_with_result = df[df['sonuc'].notna()].copy()
            # Bugünün tarihlerini çıkar
            df_with_result = filter_exclude_dates(df_with_result)
            if len(df_with_result) > 0:
                at_pist_mesafe_basari = df_with_result.groupby(['at_adi', 'pist', 'mesafe'])['sonuc'].apply(
                    lambda x: (x == 1).mean() if len(x) > 0 else 0
                ).reset_index()
                at_pist_mesafe_basari.columns = ['at_adi', 'pist', 'mesafe', 'at_pist_mesafe_basari']
                df = df.merge(at_pist_mesafe_basari, on=['at_adi', 'pist', 'mesafe'], how='left')
                df['at_pist_mesafe_basari'] = df['at_pist_mesafe_basari'].fillna(0)
            else:
                df['at_pist_mesafe_basari'] = 0
            
            # 11.5. Bu yarıştaki piste göre atın deneyimi (genel yaklaşım)
            # Bugünkü yarışın pistine göre o atın o pistteki performansına bak
            # Sentetik ve kum pistler benzer olduğu için birbirini tamamlayabilir
            if 'pist' in df.columns and 'sonuc' in df.columns and 'at_adi' in df.columns:
                df['at_bu_pist_deneyim'] = 0.2  # Varsayılan: deneyim yok (düşük skor)
                
                # Her satır için o yarıştaki piste göre deneyimi hesapla
                def calculate_pist_deneyim(row):
                    at_adi = row['at_adi']
                    current_pist = row.get('pist')
                    current_date = row.get('tarih_dt', pd.NaT)
                    
                    if pd.isna(current_pist) or pd.isna(at_adi):
                        return 0.2
                    
                    # Bu atın bu pistteki geçmiş koşuları (bugünün koşusu hariç)
                    if 'tarih_dt' in df.columns and pd.notna(current_date):
                        pist_past = df[
                            (df['at_adi'] == at_adi) & 
                            (df['pist'] == current_pist) & 
                            (df['sonuc'].notna()) &
                            (df['tarih_dt'] < current_date)
                        ].copy()
                    else:
                        # Tarih yoksa sadece sonucu olanları al
                        pist_past = df[
                            (df['at_adi'] == at_adi) & 
                            (df['pist'] == current_pist) & 
                            (df['sonuc'].notna())
                        ].copy()
                    
                    # exclude_dates'teki tarihleri çıkar
                    pist_past = filter_exclude_dates(pist_past)
                    
                    # Eğer bu pistte deneyim yoksa ve sentetik/kum pistlerden biriyse, diğerini de dene
                    if len(pist_past) == 0:
                        # Sentetik ve kum pistler benzer olduğu için birbirini tamamlayabilir
                        if current_pist.lower() == 'sentetik':
                            # Sentetik pistte deneyim yoksa kum pist deneyimine bak
                            alternative_pist = 'kum'
                            if 'tarih_dt' in df.columns and pd.notna(current_date):
                                pist_past = df[
                                    (df['at_adi'] == at_adi) & 
                                    (df['pist'] == alternative_pist) & 
                                    (df['sonuc'].notna()) &
                                    (df['tarih_dt'] < current_date)
                                ].copy()
                            else:
                                pist_past = df[
                                    (df['at_adi'] == at_adi) & 
                                    (df['pist'] == alternative_pist) & 
                                    (df['sonuc'].notna())
                                ].copy()
                            pist_past = filter_exclude_dates(pist_past)
                        elif current_pist.lower() == 'kum':
                            # Kum pistte deneyim yoksa sentetik pist deneyimine bak
                            alternative_pist = 'sentetik'
                            if 'tarih_dt' in df.columns and pd.notna(current_date):
                                pist_past = df[
                                    (df['at_adi'] == at_adi) & 
                                    (df['pist'] == alternative_pist) & 
                                    (df['sonuc'].notna()) &
                                    (df['tarih_dt'] < current_date)
                                ].copy()
                            else:
                                pist_past = df[
                                    (df['at_adi'] == at_adi) & 
                                    (df['pist'] == alternative_pist) & 
                                    (df['sonuc'].notna())
                                ].copy()
                            pist_past = filter_exclude_dates(pist_past)
                    
                    if len(pist_past) == 0:
                        return 0.2  # Bu pistte (ve alternatifinde) hiç koşmamış (düşük skor)
                    
                    # Bu pistteki ortalama derece
                    pist_past['sonuc_num'] = pd.to_numeric(pist_past['sonuc'], errors='coerce')
                    ortalama_derece = pist_past['sonuc_num'].mean()
                    
                    # Ortalama dereceyi skorla: 1. = 1.0, 2. = 0.8, 3. = 0.6, ..., 5+ = 0.2
                    if pd.notna(ortalama_derece) and ortalama_derece >= 1:
                        pist_deneyim = max(0.2, 1.0 - (ortalama_derece - 1) * 0.2)
                    else:
                        pist_deneyim = 0.2
                    
                    return pist_deneyim
                
                # Her satır için hesapla
                if 'tarih_dt' not in df.columns and 'tarih' in df.columns:
                    df['tarih_dt'] = pd.to_datetime(df['tarih'], format='%d/%m/%Y', errors='coerce')
                
                df['at_bu_pist_deneyim'] = df.apply(calculate_pist_deneyim, axis=1)
        
        # 12. At-Mesafe uygunluğu
        if 'at_adi' in df.columns and 'mesafe' in df.columns and 'sonuc' in df.columns:
            # Sadece sonuc bilgisi olan satırları kullan (bugünün koşularını hariç tut)
            df_with_result = df[df['sonuc'].notna()].copy()
            df_with_result = filter_exclude_dates(df_with_result)
            if len(df_with_result) > 0:
                at_mesafe_basari = df_with_result.groupby(['at_adi', 'mesafe'])['sonuc'].apply(
                    lambda x: (x == 1).mean() if len(x) > 0 else 0
                ).reset_index()
                at_mesafe_basari.columns = ['at_adi', 'mesafe', 'at_mesafe_basari']
                df = df.merge(at_mesafe_basari, on=['at_adi', 'mesafe'], how='left')
                df['at_mesafe_basari'] = df['at_mesafe_basari'].fillna(0)
                # 12.1. ±200m mesafe bandı başarısı
                def calc_mesafe_band_basari(row):
                    at = row.get('at_adi')
                    cur_m = pd.to_numeric(row.get('mesafe'), errors='coerce')
                    if pd.isna(at) or pd.isna(cur_m):
                        return 0.0
                    at_past = df_with_result[df_with_result['at_adi'] == at].copy()
                    if len(at_past) == 0:
                        return 0.0
                    at_past['m_num'] = pd.to_numeric(at_past['mesafe'], errors='coerce')
                    band_mask = (at_past['m_num'] >= cur_m - 200) & (at_past['m_num'] <= cur_m + 200)
                    band_races = at_past[band_mask]
                    if len(band_races) == 0:
                        return 0.0
                    return float((band_races['sonuc'] == 1).mean())
                df['at_mesafe_band_basari'] = df.apply(calc_mesafe_band_basari, axis=1)
            else:
                df['at_mesafe_basari'] = 0
                df['at_mesafe_band_basari'] = 0.0

        # 12.2. Uzun mesafe bayrağı ve pist benzerlikleri
        if 'mesafe' in df.columns:
            if 'mesafe_numeric' not in df.columns:
                df['mesafe_numeric'] = pd.to_numeric(df['mesafe'], errors='coerce')
            df['at_long_distance'] = (df['mesafe_numeric'] >= 1800).astype(int)
        if 'pist' in df.columns:
            pist_lower = df['pist'].astype(str).str.lower()
            df['pist_is_sand_or_synth'] = pist_lower.isin(['kum','sentetik']).astype(int)
        
        # 13. At-Pist kombinasyonu
        if 'pist' in df.columns and 'at_adi' in df.columns and 'sonuc' in df.columns:
            # Sadece sonuc bilgisi olan satırları kullan (bugünün koşularını hariç tut)
            df_with_result = df[df['sonuc'].notna()].copy()
            df_with_result = filter_exclude_dates(df_with_result)
            if len(df_with_result) > 0:
                at_pist_basari = df_with_result.groupby(['at_adi', 'pist'])['sonuc'].apply(
                    lambda x: (x == 1).mean() if len(x) > 0 else 0
                ).reset_index()
                at_pist_basari.columns = ['at_adi', 'pist', 'at_pist_basari']
                df = df.merge(at_pist_basari, on=['at_adi', 'pist'], how='left')
                df['at_pist_basari'] = df['at_pist_basari'].fillna(0)
                # 13.1. Pist türü (çim/kum/sentetik) bazlı başarı
                def normalize_pist_tur(p):
                    pl = str(p).lower()
                    if 'çim' in pl or 'cim' in pl:
                        return 'çim'
                    if 'kum' in pl:
                        return 'kum'
                    if 'sentetik' in pl or 'sintetik' in pl:
                        return 'sentetik'
                    return 'unknown'
                
                df_with_result['pist_tur'] = df_with_result['pist'].apply(normalize_pist_tur)
                def calc_pist_tur_basari(row):
                    at = row.get('at_adi')
                    cur_p_tur = normalize_pist_tur(row.get('pist', ''))
                    if pd.isna(at) or cur_p_tur == 'unknown':
                        return 0.0
                    at_past = df_with_result[df_with_result['at_adi'] == at].copy()
                    if len(at_past) == 0:
                        return 0.0
                    tur_mask = at_past['pist_tur'] == cur_p_tur
                    tur_races = at_past[tur_mask]
                    if len(tur_races) == 0:
                        return 0.0
                    return float((tur_races['sonuc'] == 1).mean())
                df['at_pist_tur_basari'] = df.apply(calc_pist_tur_basari, axis=1)
            else:
                df['at_pist_basari'] = 0
                df['at_pist_tur_basari'] = 0.0
        
        # 13.5. Atın genel başarı oranı (ATIN FORMUNDAN BAĞIMSIZ GENEL PERFORMANS)
        if 'at_adi' in df.columns and 'sonuc' in df.columns:
            # Sadece sonuc bilgisi olan satırları kullan (bugünün koşularını hariç tut)
            df_with_result = df[df['sonuc'].notna()].copy()
            df_with_result = filter_exclude_dates(df_with_result)
            if len(df_with_result) > 0:
                at_genel_basari = df_with_result.groupby('at_adi')['sonuc'].apply(
                    lambda x: (x == 1).mean() if len(x) > 0 else 0
                ).reset_index()
                at_genel_basari.columns = ['at_adi', 'at_genel_basari']
                df = df.merge(at_genel_basari, on='at_adi', how='left')
                df['at_genel_basari'] = df['at_genel_basari'].fillna(0)
            else:
                df['at_genel_basari'] = 0
        
        # 13.6. Badge tabanlı sayısal feature'lar (jokey-at, mesafe, hipodrom, G1/G2/G3/KV sayıları)
        if 'at_adi' in df.columns and 'sonuc' in df.columns:
            df_badge = df.copy()
            if 'tarih_dt' not in df_badge.columns and 'tarih' in df_badge.columns:
                df_badge['tarih_dt'] = pd.to_datetime(df_badge['tarih'], format='%d/%m/%Y', errors='coerce')

            past = df_badge[df_badge['sonuc'].notna()].copy()
            past = filter_exclude_dates(past)

            def calc_badges(row):
                at_adi = row.get('at_adi')
                if pd.isna(at_adi):
                    return pd.Series({
                        'at_jokey_kazanma_sayisi': 0,
                        'at_jokey_tabela_sayisi': 0,
                        'at_mesafe_kazanma_sayisi': 0,
                        'at_hipodrom_kazanma_sayisi': 0,
                        'at_g1_tecrube_sayisi': 0,
                        'at_g2_tecrube_sayisi': 0,
                        'at_g3_tecrube_sayisi': 0,
                        'at_kv_tecrube_sayisi': 0,
                    })

                subset = past[past['at_adi'] == at_adi].copy()
                cur_dt = row.get('tarih_dt', pd.NaT)
                if 'tarih_dt' in subset.columns and pd.notna(cur_dt):
                    subset = subset[subset['tarih_dt'] < cur_dt]
                subset['sonuc_numeric'] = pd.to_numeric(subset['sonuc'], errors='coerce')

                # Jokey-At
                jk_win = 0
                jk_tab = 0
                if 'jokey_adi' in df.columns and pd.notna(row.get('jokey_adi')):
                    sj = subset[subset['jokey_adi'] == row['jokey_adi']]
                    jk_win = int((sj['sonuc_numeric'] == 1).sum())
                    jk_tab = int(((sj['sonuc_numeric'] >= 1) & (sj['sonuc_numeric'] <= 4)).sum())

                # Mesafe kazanma
                msf_win = 0
                if 'mesafe' in df.columns and pd.notna(row.get('mesafe')):
                    sm = subset[subset['mesafe'] == row['mesafe']]
                    msf_win = int((sm['sonuc_numeric'] == 1).sum())

                # Hipodrom kazanma
                hip_win = 0
                hip_key = row.get('hipodrom_key', self.hipodrom_key)
                if 'hipodrom_key' in subset.columns and pd.notna(hip_key):
                    sh = subset[subset['hipodrom_key'] == hip_key]
                    hip_win = int((sh['sonuc_numeric'] == 1).sum())

                # Grup tecrübesi sayıları
                def grp_count(df_grp, no_space, spaced):
                    if 'cins_detay' not in df_grp.columns:
                        return 0
                    s = df_grp['cins_detay'].astype(str)
                    return int((s.str.contains(no_space, case=False, na=False, regex=False) |
                                s.str.contains(spaced, case=False, na=False, regex=False)).sum())

                g1 = grp_count(subset, 'G1', 'G 1')
                g2 = grp_count(subset, 'G2', 'G 2')
                g3 = grp_count(subset, 'G3', 'G 3')
                kv = 0
                if 'cins_detay' in subset.columns:
                    kv = int(subset['cins_detay'].astype(str).str.contains('KV', case=False, na=False).sum())

                return pd.Series({
                    'at_jokey_kazanma_sayisi': jk_win,
                    'at_jokey_tabela_sayisi': jk_tab,
                    'at_mesafe_kazanma_sayisi': msf_win,
                    'at_hipodrom_kazanma_sayisi': hip_win,
                    'at_g1_tecrube_sayisi': g1,
                    'at_g2_tecrube_sayisi': g2,
                    'at_g3_tecrube_sayisi': g3,
                    'at_kv_tecrube_sayisi': kv,
                })

            badge_feats = df_badge.apply(calc_badges, axis=1)
            for col in badge_feats.columns:
                df[col] = pd.to_numeric(badge_feats[col], errors='coerce').fillna(0)

            # 13.7. Geçmişte kaç farklı rakibi geçti? (unique competitor beat count)
            def calc_beaten_competitors(row):
                at_adi = row.get('at_adi')
                if pd.isna(at_adi):
                    return 0
                cur_dt = row.get('tarih_dt', pd.NaT)
                # Aynı koşuda koşmuş rakipler geçmişte ortak koşularda geçilmiş mi?
                # Basitleştirme: atın tüm geçmiş yarışlarında (geçmiş subset) daha iyi derece yaptığı farklı rakip sayısı
                subset = past[past['at_adi'] == at_adi].copy()
                if 'tarih_dt' in subset.columns and pd.notna(cur_dt):
                    subset = subset[subset['tarih_dt'] < cur_dt]
                subset['sonuc_numeric'] = pd.to_numeric(subset['sonuc'], errors='coerce')
                if len(subset) == 0:
                    return 0
                # Rakip seti: aynı yaris_kosu_key'te koşan diğer atlar
                beaten_set = set()
                # Yarış bazında tüm sonuçları çıkar
                races = past.copy()
                if 'tarih_dt' in races.columns and pd.notna(cur_dt):
                    races = races[races['tarih_dt'] < cur_dt]
                races['sonuc_numeric'] = pd.to_numeric(races['sonuc'], errors='coerce')
                for race_key in subset['yaris_kosu_key'].dropna().unique():
                    r = races[races['yaris_kosu_key'] == race_key]
                    my_res = r[r['at_adi'] == at_adi]['sonuc_numeric']
                    if len(my_res) == 0 or pd.isna(my_res.iloc[0]):
                        continue
                    my_rank = my_res.iloc[0]
                    if pd.isna(my_rank):
                        continue
                    worse = r[(r['at_adi'] != at_adi) & (pd.to_numeric(r['sonuc_numeric'], errors='coerce') > my_rank)]['at_adi']
                    for comp in worse.dropna().unique():
                        beaten_set.add(comp)
                return int(len(beaten_set))

            df['at_gecilen_rakip_sayisi'] = df_badge.apply(calc_beaten_competitors, axis=1)

            # 13.8. Ağırlıklı rozet skoru (öncelik: G1 >> G2 >> G3 >> KV > rakip > mesafe kazanma > hipodrom kazanma)
            # G1/G2/G3 arasındaki farkı büyüt: 1 G1 > 2 G2 > 3 G3 olmalı
            w_g1 = 25.0  # 1 G1 = 25.0
            w_g2 = 10.0  # 1 G2 = 10.0 (2 G2 = 20.0 < 1 G1 = 25.0 ✓)
            w_g3 = 6.0   # 1 G3 = 6.0 (3 G3 = 18.0 < 1 G1 = 25.0 ✓)
            w_kv = 3.0   # KV G3'ten daha düşük
            w_beaten = 2.5
            w_m = 1.8
            w_h = 1.2
            df['at_badge_agirlikli_skor'] = (
                w_g1 * df['at_g1_tecrube_sayisi'] +
                w_g2 * df['at_g2_tecrube_sayisi'] +
                w_g3 * df['at_g3_tecrube_sayisi'] +
                w_kv * df['at_kv_tecrube_sayisi'] +
                w_beaten * df['at_gecilen_rakip_sayisi'] +
                w_m * df['at_mesafe_kazanma_sayisi'] +
                w_h * df['at_hipodrom_kazanma_sayisi']
            )

            # 13.9. Etkileşimli türevler (alt parçaları etkileşimleri)
            df['at_g_ust_sum'] = (
                df['at_g1_tecrube_sayisi'] + df['at_g2_tecrube_sayisi'] + df['at_g3_tecrube_sayisi']
            )
            # Basit ölçekleme (log1p) ile dağılımı stabilize et
            df['at_g_ust_sum_log1p'] = np.log1p(df['at_g_ust_sum'])
            df['at_kv_log1p'] = np.log1p(df['at_kv_tecrube_sayisi'])
            df['at_beaten_log1p'] = np.log1p(df['at_gecilen_rakip_sayisi'])
            df['at_mesafe_win_log1p'] = np.log1p(df['at_mesafe_kazanma_sayisi'])
            df['at_hip_win_log1p'] = np.log1p(df['at_hipodrom_kazanma_sayisi'])

            # Çarpım (interaction) özellikleri
            df['ix_gxkv'] = df['at_g_ust_sum_log1p'] * df['at_kv_log1p']
            df['ix_gxmesafe'] = df['at_g_ust_sum_log1p'] * df['at_mesafe_win_log1p']
            df['ix_gxhip'] = df['at_g_ust_sum_log1p'] * df['at_hip_win_log1p']
            df['ix_kvxmesafe'] = df['at_kv_log1p'] * df['at_mesafe_win_log1p']
            df['ix_kvxhip'] = df['at_kv_log1p'] * df['at_hip_win_log1p']
            df['ix_beatenxmesafe'] = df['at_beaten_log1p'] * df['at_mesafe_win_log1p']
            df['ix_beatenxhip'] = df['at_beaten_log1p'] * df['at_hip_win_log1p']

            # Toplam etkileşim skoru (referans için, model alt parçaları da görecek)
            df['at_badge_interaction_score'] = (
                df['ix_gxkv'] + df['ix_gxmesafe'] + df['ix_gxhip'] +
                df['ix_kvxmesafe'] + df['ix_kvxhip'] +
                df['ix_beatenxmesafe'] + df['ix_beatenxhip']
            )

            # 13.10. G1/G2/G3 ayrı ağırlıklı skorlar ve basit etkileşimleri
            # Tekil önem için ayrı ağırlıklar: G1 >> G2 >> G3 (1 G1 > 2 G2 > 3 G3)
            df['at_g1_weighted'] = 25.0 * df['at_g1_tecrube_sayisi']  # 1 G1 = 25.0 (2 G2 = 20.0 < 1 G1)
            df['at_g2_weighted'] = 10.0 * df['at_g2_tecrube_sayisi']  # 1 G2 = 10.0
            df['at_g3_weighted'] = 6.0 * df['at_g3_tecrube_sayisi']  # 1 G3 = 6.0 (3 G3 = 18.0 < 1 G1)

            # G1/G2/G3 x (mesafe/hipodrom kazanma) etkileşimleri
            df['ix_g1xmesafe'] = df['at_g1_weighted'] * df['at_mesafe_win_log1p']
            df['ix_g2xmesafe'] = df['at_g2_weighted'] * df['at_mesafe_win_log1p']
            df['ix_g3xmesafe'] = df['at_g3_weighted'] * df['at_mesafe_win_log1p']
            df['ix_g1xhip'] = df['at_g1_weighted'] * df['at_hip_win_log1p']
            df['ix_g2xhip'] = df['at_g2_weighted'] * df['at_hip_win_log1p']
            df['ix_g3xhip'] = df['at_g3_weighted'] * df['at_hip_win_log1p']

        # 13.11. Head-to-Head (H2H) Feature - Kim kimi geçti?
        # Her at için geçmişteki rakiplerine karşı genel üstünlük skoru
        if 'at_adi' in df.columns and 'sonuc' in df.columns and 'yaris_kosu_key' in df.columns:
            df_with_result = df[df['sonuc'].notna()].copy()
            df_with_result = filter_exclude_dates(df_with_result)
            
            if len(df_with_result) > 0:
                def normalize_pist_tur_for_h2h(p):
                    pl = str(p).lower()
                    if 'çim' in pl or 'cim' in pl:
                        return 'çim'
                    if 'kum' in pl:
                        return 'kum'
                    if 'sentetik' in pl or 'sintetik' in pl:
                        return 'sentetik'
                    return 'unknown'
                
                def calc_h2h_general_score(row):
                    at_adi = row.get('at_adi')
                    if pd.isna(at_adi):
                        return 0.0
                    
                    # Bu atın koştuğu geçmiş yarışlar
                    at_races = df_with_result[df_with_result['at_adi'] == at_adi].copy()
                    if len(at_races) == 0:
                        return 0.0
                    
                    total_score = 0.0
                    total_weight = 0.0
                    
                    for _, race in at_races.iterrows():
                        race_key = race.get('yaris_kosu_key')
                        if pd.isna(race_key):
                            continue
                        
                        # Aynı yarıştaki diğer atlar
                        same_race = df_with_result[df_with_result['yaris_kosu_key'] == race_key].copy()
                        if len(same_race) < 2:
                            continue
                        
                        at_rank = pd.to_numeric(race.get('sonuc'), errors='coerce')
                        if pd.isna(at_rank):
                            continue
                        
                        # Sınıf ağırlığı
                        cw = 1.0
                        if 'cins_detay' in race:
                            c_str = str(race['cins_detay']).upper()
                            if 'G 1' in c_str or 'G1' in c_str:
                                cw = 1.4
                            elif 'G 2' in c_str or 'G2' in c_str:
                                cw = 1.2
                            elif 'G 3' in c_str or 'G3' in c_str:
                                cw = 1.0
                            elif 'KV' in c_str:
                                cw = 0.8
                            else:
                                cw = 0.6
                        
                        # Recency (yakın zamanda daha önemli)
                        rec = 1.0
                        if 'tarih_dt' in race.index and pd.notna(race.get('tarih_dt')):
                            try:
                                days = (pd.Timestamp.now() - race['tarih_dt']).days
                                rec = float(np.exp(-max(0, days) / 90.0))
                            except:
                                pass
                        
                        # Bu yarışta kaç rakibi geçti
                        beaten = 0
                        for _, opp in same_race.iterrows():
                            if opp['at_adi'] == at_adi:
                                continue
                            opp_rank = pd.to_numeric(opp.get('sonuc'), errors='coerce')
                            if not pd.isna(opp_rank) and at_rank < opp_rank:
                                beaten += 1
                        
                        # Skor: geçtiği rakip sayısı / toplam rakip sayısı
                        opponents = len(same_race) - 1
                        if opponents > 0:
                            win_ratio = beaten / opponents
                            weight = cw * rec
                            total_score += win_ratio * weight
                            total_weight += weight
                    
                    if total_weight > 0:
                        return float(total_score / total_weight)
                    return 0.0
                
                df['at_h2h_genel_skor'] = df.apply(calc_h2h_general_score, axis=1)
            else:
                df['at_h2h_genel_skor'] = 0.0
        else:
            df['at_h2h_genel_skor'] = 0.0

        # === JOKEY VE ANTRENÖR FEATURE'LARI ===
        # 14. Jokey-At kombinasyonu (EN ÖNEMLİ - bu jokey bu atla ne kadar başarılı?)
        if 'jokey_adi' in df.columns and 'at_adi' in df.columns and 'sonuc' in df.columns:
            # Sadece sonuc bilgisi olan satırları kullan (bugünün koşularını hariç tut)
            df_with_result = df[df['sonuc'].notna()].copy()
            df_with_result = filter_exclude_dates(df_with_result)
            if len(df_with_result) > 0:
                jokey_at_basari = df_with_result.groupby(['jokey_adi', 'at_adi'])['sonuc'].apply(
                    lambda x: (x == 1).mean() if len(x) > 0 else 0
                ).reset_index()
                jokey_at_basari.columns = ['jokey_adi', 'at_adi', 'jokey_at_basari']
                df = df.merge(jokey_at_basari, on=['jokey_adi', 'at_adi'], how='left')
                df['jokey_at_basari'] = df['jokey_at_basari'].fillna(0)
            else:
                df['jokey_at_basari'] = 0
        
        # 15. Jokey genel başarı oranı (ayrı ayrı bakmak için)
        if 'jokey_adi' in df.columns and 'sonuc' in df.columns:
            # Sadece sonuc bilgisi olan satırları kullan (bugünün koşularını hariç tut)
            df_with_result = df[df['sonuc'].notna()].copy()
            df_with_result = filter_exclude_dates(df_with_result)
            if len(df_with_result) > 0:
                jokey_basari = df_with_result.groupby('jokey_adi')['sonuc'].apply(
                    lambda x: (x == 1).mean() if len(x) > 0 else 0
                ).reset_index()
                jokey_basari.columns = ['jokey_adi', 'jokey_genel_basari']
                df = df.merge(jokey_basari, on='jokey_adi', how='left')
                df['jokey_genel_basari'] = df['jokey_genel_basari'].fillna(0)
            else:
                df['jokey_genel_basari'] = 0
        
        # 16. Jokey-Mesafe başarı oranı (bu jokey bu mesafede ne kadar başarılı?)
        if 'jokey_adi' in df.columns and 'mesafe' in df.columns and 'sonuc' in df.columns:
            # Sadece sonuc bilgisi olan satırları kullan (bugünün koşularını hariç tut)
            df_with_result = df[df['sonuc'].notna()].copy()
            df_with_result = filter_exclude_dates(df_with_result)
            if len(df_with_result) > 0:
                jokey_mesafe_basari = df_with_result.groupby(['jokey_adi', 'mesafe'])['sonuc'].apply(
                    lambda x: (x == 1).mean() if len(x) > 0 else 0
                ).reset_index()
                jokey_mesafe_basari.columns = ['jokey_adi', 'mesafe', 'jokey_mesafe_basari']
                df = df.merge(jokey_mesafe_basari, on=['jokey_adi', 'mesafe'], how='left')
                df['jokey_mesafe_basari'] = df['jokey_mesafe_basari'].fillna(0)
            else:
                df['jokey_mesafe_basari'] = 0
        
        # 17. Antrenör genel başarı oranı (ayrı ayrı bakmak için)
        if 'antrenor_adi' in df.columns and 'sonuc' in df.columns:
            # Sadece sonuc bilgisi olan satırları kullan (bugünün koşularını hariç tut)
            df_with_result = df[df['sonuc'].notna()].copy()
            df_with_result = filter_exclude_dates(df_with_result)
            if len(df_with_result) > 0:
                antrenor_basari = df_with_result.groupby('antrenor_adi')['sonuc'].apply(
                    lambda x: (x == 1).mean() if len(x) > 0 else 0
                ).reset_index()
                antrenor_basari.columns = ['antrenor_adi', 'antrenor_genel_basari']
                df = df.merge(antrenor_basari, on='antrenor_adi', how='left')
                df['antrenor_genel_basari'] = df['antrenor_genel_basari'].fillna(0)
            else:
                df['antrenor_genel_basari'] = 0

        # 17.1 Jokey/Antrenör son 60 gün sınıf-ağırlıklı form
        if {'jokey_adi','antrenor_adi','tarih','sonuc','cins_detay'}.issubset(df.columns):
            if 'tarih_dt' not in df.columns:
                df['tarih_dt'] = pd.to_datetime(df['tarih'], format='%d/%m/%Y', errors='coerce')
            def rolling_form(name_col, out_col):
                def calc(row):
                    name = row.get(name_col)
                    cur = row.get('tarih_dt', pd.NaT)
                    if pd.isna(name) or pd.isna(cur):
                        return 0.0
                    start = cur - pd.Timedelta(days=60)
                    hist = df[(df[name_col]==name) & (df['tarih_dt']<cur) & (df['tarih_dt']>=start) & (df['sonuc'].notna())]
                    if len(hist)==0:
                        return 0.0
                    hist = hist.copy()
                    hist['cw'] = hist['cins_detay'].apply(lambda s: _class_weight(s))
                    wins = ((pd.to_numeric(hist['sonuc'], errors='coerce')==1)*hist['cw']).sum()
                    denom = hist['cw'].sum()
                    return float(wins/denom) if denom>0 else 0.0
                return calc
            df['jokey_recent60_cls_winrate'] = df.apply(rolling_form('jokey_adi','jokey_recent60_cls_winrate'), axis=1)
            df['ant_recent60_cls_winrate'] = df.apply(rolling_form('antrenor_adi','ant_recent60_cls_winrate'), axis=1)
        
        # 18. Antrenör-Mesafe başarı oranı (bu antrenör bu mesafede ne kadar başarılı?)
        if 'antrenor_adi' in df.columns and 'mesafe' in df.columns and 'sonuc' in df.columns:
            # Sadece sonuc bilgisi olan satırları kullan (bugünün koşularını hariç tut)
            df_with_result = df[df['sonuc'].notna()].copy()
            df_with_result = filter_exclude_dates(df_with_result)
            if len(df_with_result) > 0:
                antrenor_mesafe_basari = df_with_result.groupby(['antrenor_adi', 'mesafe'])['sonuc'].apply(
                    lambda x: (x == 1).mean() if len(x) > 0 else 0
                ).reset_index()
                antrenor_mesafe_basari.columns = ['antrenor_adi', 'mesafe', 'antrenor_mesafe_basari']
                df = df.merge(antrenor_mesafe_basari, on=['antrenor_adi', 'mesafe'], how='left')
                df['antrenor_mesafe_basari'] = df['antrenor_mesafe_basari'].fillna(0)
            else:
                df['antrenor_mesafe_basari'] = 0
        
        # 16. At-Grup kombinasyonu analizi
        if 'grup' in df.columns and 'at_adi' in df.columns and 'sonuc' in df.columns:
            # Sadece sonuc bilgisi olan satırları kullan (bugünün koşularını hariç tut)
            df_with_result = df[df['sonuc'].notna()].copy()
            df_with_result = filter_exclude_dates(df_with_result)
            if len(df_with_result) > 0:
                at_grup_basari = df_with_result.groupby(['at_adi', 'grup'])['sonuc'].apply(
                    lambda x: (x == 1).mean() if len(x) > 0 else 0
                ).reset_index()
                at_grup_basari.columns = ['at_adi', 'grup', 'at_grup_basari']
                df = df.merge(at_grup_basari, on=['at_adi', 'grup'], how='left')
                df['at_grup_basari'] = df['at_grup_basari'].fillna(0)
            else:
                df['at_grup_basari'] = 0

        # 16.5. Cins detay sınıf ağırlıklı son performans (G1>G2>G3>KV>Şartlı>Handikap>Maiden>Satış)
        if 'at_adi' in df.columns and 'sonuc' in df.columns and 'cins_detay' in df.columns:
            if 'tarih_dt' not in df.columns and 'tarih' in df.columns:
                df['tarih_dt'] = pd.to_datetime(df['tarih'], format='%d/%m/%Y', errors='coerce')

            def class_weight(c):
                return _class_weight(c)

            def compute_class_weighted_recent(row):
                at = row.get('at_adi')
                cur_dt = row.get('tarih_dt', pd.NaT)
                if pd.isna(at):
                    return pd.Series({
                        'at_class_weighted_avg_rank_last6': 10.0,
                        'at_class_weighted_win_rate_last6': 0.0,
                        'at_high_class_start_ratio_last6': 0.0
                    })
                hist = df[(df['at_adi'] == at) & (df['sonuc'].notna())].copy()
                if 'tarih_dt' in hist.columns and pd.notna(cur_dt):
                    hist = hist[hist['tarih_dt'] < cur_dt]
                # exclude_dates çıkar
                hist = filter_exclude_dates(hist)
                if len(hist) == 0:
                    return pd.Series({
                        'at_class_weighted_avg_rank_last6': 10.0,
                        'at_class_weighted_win_rate_last6': 0.0,
                        'at_high_class_start_ratio_last6': 0.0
                    })
                # Son 6 yarışı al (varsa)
                if 'tarih_dt' in hist.columns:
                    hist = hist.sort_values('tarih_dt', ascending=False)
                last6 = hist.head(6).copy()
                last6['rank'] = pd.to_numeric(last6['sonuc'], errors='coerce')
                last6['cw'] = last6['cins_detay'].apply(_class_weight)
                # Sınıf-dengeli ortalama derece (düşük daha iyi)
                # Not: yüksek sınıfta (cw büyük) kötü dereceyi nispeten affetmek için rank/cw kullanıyoruz
                if (last6['cw']>0).any() and last6['rank'].notna().any():
                    adj = last6.apply(lambda r: float(r['rank'])/float(r['cw']) if (pd.notna(r['rank']) and r['cw']>0) else np.nan, axis=1)
                    if adj.notna().any():
                        w_avg_rank = float(adj.mean())
                    else:
                        w_avg_rank = 10.0
                else:
                    w_avg_rank = 10.0
                # Ağırlıklı kazanma oranı (rank==1)
                wins = ((last6['rank'] == 1) * last6['cw']).sum()
                cw_sum = last6['cw'].sum()
                w_win_rate = float(wins/cw_sum) if cw_sum>0 else 0.0
                # Yüksek sınıf oranı (G1/G2/G3/KV)
                high = last6['cw'] >= 0.7
                high_ratio = float(high.mean()) if len(last6)>0 else 0.0
                return pd.Series({
                    'at_class_weighted_avg_rank_last6': w_avg_rank,
                    'at_class_weighted_win_rate_last6': w_win_rate,
                    'at_high_class_start_ratio_last6': high_ratio
                })

            class_feats = df.apply(compute_class_weighted_recent, axis=1)
            df = pd.concat([df, class_feats], axis=1)

        # 16.6. Rakip kalite metriği (son 6): yüksek sınıf oranı + rakiplerin sınıf-ağırlıklı form ortalaması
        if {'at_adi','yaris_kosu_key','sonuc','cins_detay'}.issubset(df.columns):
            if 'tarih_dt' not in df.columns and 'tarih' in df.columns:
                df['tarih_dt'] = pd.to_datetime(df['tarih'], format='%d/%m/%Y', errors='coerce')

            def is_high_class(s):
                cw = _class_weight(s)
                return cw >= 0.8

            def compute_opponent_quality(row):
                at = row.get('at_adi')
                cur_dt = row.get('tarih_dt', pd.NaT)
                if pd.isna(at):
                    return 0.0
                hist = df[(df['at_adi'] == at) & (df['sonuc'].notna())].copy()
                if 'tarih_dt' in hist.columns and pd.notna(cur_dt):
                    hist = hist[hist['tarih_dt'] < cur_dt]
                hist = filter_exclude_dates(hist)
                if len(hist) == 0:
                    return 0.0
                if 'tarih_dt' in hist.columns:
                    hist = hist.sort_values('tarih_dt', ascending=False)
                last6 = hist.head(6).copy()
                qualities_ratio = []
                qualities_form = []
                for rk in last6['yaris_kosu_key'].dropna().unique():
                    race_peers = df[df['yaris_kosu_key'] == rk].copy()
                    if 'tarih_dt' in race_peers.columns and pd.notna(cur_dt):
                        race_peers = race_peers[race_peers['tarih_dt'] < cur_dt]
                    race_peers = filter_exclude_dates(race_peers)
                    if len(race_peers) == 0:
                        continue
                    # aynı yarışın cins_detay'ına göre yüksek sınıf kabul et
                    high_mask = race_peers['cins_detay'].apply(is_high_class)
                    # kendisini hariç tut
                    if 'at_adi' in race_peers.columns:
                        high_mask = high_mask & (race_peers['at_adi'] != at)
                    denom = max(1, (race_peers['at_adi'] != at).sum())
                    # Yüksek sınıf oranı
                    qualities_ratio.append(float(high_mask.sum())/float(denom))
                    # Rakiplerin sınıf-ağırlıklı kazanma oranı ortalaması
                    if 'at_class_weighted_win_rate_last6' in race_peers.columns:
                        peers = race_peers[race_peers['at_adi'] != at]
                        if len(peers) > 0:
                            qualities_form.append(float(pd.to_numeric(peers['at_class_weighted_win_rate_last6'], errors='coerce').mean()))
                ratio_mean = float(np.mean(qualities_ratio)) if qualities_ratio else 0.0
                form_mean = float(np.mean(qualities_form)) if qualities_form else 0.0
                # Bileşik skor: form %70, oran %30
                return 0.7 * form_mean + 0.3 * ratio_mean

            df['at_opponent_quality_last6'] = df.apply(compute_opponent_quality, axis=1)
        
        # 16.5. Grup seviye skorlaması ve ağırlıklı performans
        if 'grup' in df.columns:
            def get_grup_seviye_score(grup):
                """Grup seviyesini skorla"""
                grup_str = str(grup).upper()
                
                # 4 ve Yukarı = en üst seviye (skor: 5)
                if '4 VE YUKARI' in grup_str or '4 VE YUKAR' in grup_str:
                    return 5
                # 3 Yaşlı = orta seviye (skor: 3)
                elif '3 YAŞLI' in grup_str or '3 YAŞL' in grup_str:
                    return 3
                # 2 Yaşlı = alt seviye (skor: 1)
                elif '2 YAŞLI' in grup_str or '2 YAŞL' in grup_str:
                    return 1
                # Diğer (skor: 4)
                else:
                    return 4
            
            df['grup_seviye_score'] = df['grup'].apply(get_grup_seviye_score)
            
            # Atın grup seviye bazlı ağırlıklı performansı
            if 'at_adi' in df.columns and 'sonuc' in df.columns:
                # Sadece sonuc bilgisi olan satırları kullan (bugünün koşularını hariç tut)
                df_with_result = df[df['sonuc'].notna()].copy()
                df_with_result = filter_exclude_dates(df_with_result)
                if len(df_with_result) > 0:
                    # Her atın her grup seviyesindeki ortalama derecesini ağırlıklı hesapla
                    def weighted_grup_performance(group_df):
                        if len(group_df) == 0:
                            return 0
                        # sonuc 1 ise başarı (1), 2+ ise başarısızlık (0)
                        # grup seviyesi skoru ile çarp
                        success = (group_df['sonuc'] == 1).astype(int)
                        scores = success * group_df['grup_seviye_score']
                        return scores.mean() if len(scores) > 0 else 0
                    
                    at_weighted_grup = df_with_result.groupby('at_adi').apply(weighted_grup_performance).reset_index()
                    at_weighted_grup.columns = ['at_adi', 'at_weighted_grup_performance']
                    df = df.merge(at_weighted_grup, on='at_adi', how='left')
                    df['at_weighted_grup_performance'] = df['at_weighted_grup_performance'].fillna(0)
                else:
                    df['at_weighted_grup_performance'] = 0
        
        # 16.6. Yarış türü (cins_detay) bazlı skorlar (G1>G2>G3>KV>Şartlı>Handikap>Maiden)
        if 'cins_detay' in df.columns:
            def normalize_text(s: str) -> str:
                if not isinstance(s, str):
                    s = str(s)
                s = s.upper()
                # Türkçe karakter normalize
                repl = {
                    'İ': 'I', 'I': 'I', 'Ş': 'S', 'Ğ': 'G', 'Ü': 'U', 'Ö': 'O', 'Ç': 'C',
                    'Â': 'A', 'Ê': 'E', 'Ô': 'O'
                }
                for k, v in repl.items():
                    s = s.replace(k, v)
                # Bazı encoding bozulmaları için alternatifler
                s = s.replace('Å', 'S').replace('Ä°', 'I').replace('Ã', 'O').replace('Ã', 'U').replace('Ã', 'C').replace('Ä', 'G')
                return s

            def detect_tur_kategori(x: str) -> str:
                ux = normalize_text(x)
                if 'G1' in ux or ' G 1' in ux:
                    return 'G1'
                if 'G2' in ux or ' G 2' in ux:
                    return 'G2'
                if 'G3' in ux or ' G 3' in ux:
                    return 'G3'
                if 'KV' in ux or 'KISA VADE' in ux:
                    return 'KV'
                if 'MAID' in ux or 'MAIDEN' in ux:
                    return 'MAIDEN'
                if 'HAND' in ux:
                    return 'HANDIKAP'
                if 'SART' in ux or 'SARTLI' in ux or 'ŞART' in ux:
                    return 'SARTLI'
                return 'DIGER'

            def kategori_weight(cat: str) -> int:
                weights = {
                    'G1': 10,
                    'G2': 9,
                    'G3': 8,
                    'KV': 7,
                    'SARTLI': 5,
                    'HANDIKAP': 4,
                    'MAIDEN': 3,
                    'DIGER': 2,
                }
                return weights.get(cat, 2)

            df['tur_kategori'] = df['cins_detay'].apply(detect_tur_kategori)
            df['tur_agirlik'] = df['tur_kategori'].apply(kategori_weight)

            # At-tür bazlı başarı oranı
            if 'at_adi' in df.columns and 'sonuc' in df.columns:
                # Sadece sonuc bilgisi olan satırları kullan (bugünün koşularını hariç tut)
                df_with_result = df[df['sonuc'].notna()].copy()
                df_with_result = filter_exclude_dates(df_with_result)
                if len(df_with_result) > 0:
                    at_tur_basari = df_with_result.groupby(['at_adi', 'tur_kategori'])['sonuc'].apply(
                        lambda x: (x == 1).mean() if len(x) > 0 else 0
                    ).reset_index()
                    at_tur_basari.columns = ['at_adi', 'tur_kategori', 'at_tur_basari']
                    df = df.merge(at_tur_basari, on=['at_adi', 'tur_kategori'], how='left')
                    df['at_tur_basari'] = df['at_tur_basari'].fillna(0)
                else:
                    df['at_tur_basari'] = 0

                # Ağırlıklı tür skoru (başarı * ağırlık)
                # Sadece sonuc bilgisi olan satırları kullan (bugünün koşularını hariç tut)
                df_with_result = df[df['sonuc'].notna()].copy()
                df_with_result = filter_exclude_dates(df_with_result)
                if len(df_with_result) > 0:
                    def weighted_tur_performance(group_df):
                        if len(group_df) == 0:
                            return 0
                        success = (group_df['sonuc'] == 1).astype(int)
                        scores = success * group_df['tur_agirlik']
                        return scores.mean() if len(scores) > 0 else 0

                    at_weighted_tur = df_with_result.groupby('at_adi').apply(weighted_tur_performance).reset_index()
                    at_weighted_tur.columns = ['at_adi', 'at_weighted_tur_performance']
                    df = df.merge(at_weighted_tur, on='at_adi', how='left')
                    df['at_weighted_tur_performance'] = df['at_weighted_tur_performance'].fillna(0)
                else:
                    df['at_weighted_tur_performance'] = 0
                
                # Atın üst düzey koşulara katılım sayısı
                # ÖNEMLİ: Sadece KV, G3, G2, G1 koşuları üst düzey sayılır
                # ÖNEMLİ: Bu koşular yoksa 0, varsa sayı
                # ÖNEMLİ: Bugünün koşuları hariç tutulmalı (sonuc NaN olanlar)
                # ÖNEMLİ: Sadece son 1 yıl içindeki üst düzey koşular sayılır
                ust_duzey_turler = ['KV', 'G3', 'G2', 'G1']
                
                # Geçmiş koşuları al (sonuc sütunu varsa ve NaN değilse)
                if 'sonuc' in df.columns:
                    # Sonuc sütunu varsa, sadece sonucu olan koşuları say (bugünün koşuları hariç)
                    past_df = df[df['sonuc'].notna()].copy()
                else:
                    # Sonuc sütunu yoksa, tüm koşuları say
                    past_df = df.copy()
                
                # exclude_dates'teki tarihleri çıkar
                past_df = filter_exclude_dates(past_df)
                
                # En son tarihi bul (bugünün koşuları için bugünün tarihi, geçmiş için en son tarih)
                if 'tarih' in past_df.columns:
                    # Tarihi datetime'a çevir
                    try:
                        past_df['tarih_dt'] = pd.to_datetime(past_df['tarih'], format='%d/%m/%Y', errors='coerce')
                        # En son tarihi bul
                        if past_df['tarih_dt'].notna().any():
                            latest_date = past_df['tarih_dt'].max()
                            # Son 1 yıl içindeki koşuları filtrele
                            one_year_ago = latest_date - pd.Timedelta(days=365)
                            past_df = past_df[past_df['tarih_dt'] >= one_year_ago].copy()
                    except:
                        pass  # Tarih parse edilemezse tüm geçmişi kullan
                
                # Her at için üst düzey koşu sayısını hesapla
                def calculate_ust_duzey_count(at_adi_value):
                    # Bu atın son 1 yıldaki üst düzey koşuları (bugünün koşuları hariç)
                    at_races = past_df[(past_df['at_adi'] == at_adi_value) & 
                                      (past_df['tur_kategori'].isin(ust_duzey_turler))]
                    
                    return len(at_races)  # Sadece sayı
                
                df['at_ust_duzey_deneyim'] = df['at_adi'].apply(calculate_ust_duzey_count)

        # === GÜÇLENDİRİLMİŞ FORM FEATURE'LARI ===
        # 17. Gelişmiş form durumu ve benzer koşullardaki performans
        if 'at_adi' in df.columns and 'tarih' in df.columns and 'sonuc' in df.columns:
            # Tarihi datetime'a çevir
            if 'tarih_dt' not in df.columns:
                df['tarih_dt'] = pd.to_datetime(df['tarih'], format='%d/%m/%Y', errors='coerce')
            if 'sonuc_numeric' not in df.columns:
                df['sonuc_numeric'] = pd.to_numeric(df['sonuc'], errors='coerce')
            
            # Her at için form durumu hesapla
            def calculate_form_features(row):
                at_adi = row['at_adi']
                current_date = row.get('tarih_dt')
                current_sonuc = row.get('sonuc_numeric')
                
                if pd.isna(current_date):
                    return pd.Series({
                        'at_son3_form': 0,
                        'at_son5_form': 0,
                        'at_son3_form_weighted': 0,
                        'at_son5_form_weighted': 0,
                        'at_son_yarista_kazanma': 0,
                        'at_son_yarista_kazanma_weighted': 0,
                        'at_son2_yarista_kazanma': 0,
                        'at_son2_yarista_kazanma_weighted': 0,
                        'at_form_trend': 0,
                        'at_benzer_kosul_son_performans': 0,
                        'at_benzer_kosul_son_performans_weighted': 0,
                        'at_son_derece': 10,
                        'at_son_derece_score': 0,
                        'at_son_derece_score_weighted': 0,
                        'at_form_score': 0,
                        'at_form_score_weighted': 0
                    })
                
                # Bu atın geçmişteki koşuları (bugünün koşusu hariç - exclude_dates kontrolü)
                at_past = df[
                    (df['at_adi'] == at_adi) & 
                    (df['tarih_dt'] < current_date) &
                    (df['sonuc_numeric'].notna())
                ].copy()
                
                # exclude_dates'teki tarihleri çıkar (bugünün verileri dahil ganyan, agf1, agf2 vs. içeren tüm veriler)
                if len(exclude_dates) > 0 and 'tarih' in at_past.columns:
                    at_past = at_past[~at_past['tarih'].isin(exclude_dates)].copy()
                if len(exclude_dates_dt) > 0 and 'tarih_dt' in at_past.columns:
                    at_past = at_past[~at_past['tarih_dt'].isin(exclude_dates_dt)].copy()
                
                at_past = at_past.sort_values('tarih_dt', ascending=False)
                
                if len(at_past) == 0:
                    return pd.Series({
                        'at_son3_form': 0,
                        'at_son5_form': 0,
                        'at_son3_form_weighted': 0,
                        'at_son5_form_weighted': 0,
                        'at_son_yarista_kazanma': 0,
                        'at_son_yarista_kazanma_weighted': 0,
                        'at_son2_yarista_kazanma': 0,
                        'at_son2_yarista_kazanma_weighted': 0,
                        'at_form_trend': 0,
                        'at_benzer_kosul_son_performans': 0,
                        'at_benzer_kosul_son_performans_weighted': 0,
                        'at_son_derece': 10,
                        'at_son_derece_score': 0,
                        'at_son_derece_score_weighted': 0,
                        'at_form_score': 0,
                        'at_form_score_weighted': 0
                    })
                
                # Son 3 ve 5 yarıştaki form durumu (kazanma oranı)
                son3 = at_past.head(3)
                son5 = at_past.head(5)
                
                # Son3 için üstel (exp) ağırlıklı kazanma oranı (λ=0.7)
                if len(son3) > 0:
                    vals = (son3['sonuc_numeric'] == 1).astype(float).to_numpy()
                    # vals[0] en yeni, sonra eski
                    w = np.array([1.0, np.exp(-0.7), np.exp(-1.4)])[:len(vals)]
                    w = w / w.sum()
                    son3_form = float(np.dot(vals, w))
                else:
                    son3_form = 0
                son5_form = (son5['sonuc_numeric'] == 1).mean() if len(son5) > 0 else 0

                # Son6 için GRUP (cins_detay) ağırlıklı puan
                last6 = at_past.head(6).copy()
                if len(last6) > 0:
                    last6['rank'] = pd.to_numeric(last6['sonuc_numeric'], errors='coerce')
                    if 'cins_detay' in last6.columns:
                        last6['cw'] = last6['cins_detay'].apply(lambda s: _class_weight(s) if pd.notna(s) else 0.4)
                    else:
                        last6['cw'] = 0.4
                    def rank_to_score(r):
                        try:
                            r = float(r)
                        except:
                            return 0.0
                        if r <= 1:
                            return 1.0
                        if r >= 10:
                            return 0.0
                        return max(0.0, 1.0 - (r - 1) * 0.15)
                    last6['rscore'] = last6['rank'].apply(rank_to_score)
                    rec_w = np.exp(-0.5 * np.arange(len(last6)))
                    rec_w = rec_w / rec_w.sum()
                    eff_w = rec_w * last6['cw'].fillna(0.4).to_numpy()
                    denom6 = eff_w.sum()
                    at_last6_group_score = float(np.dot(last6['rscore'].fillna(0.0).to_numpy(), eff_w) / denom6) if denom6 > 0 else 0.0
                else:
                    at_last6_group_score = 0.0
                
                # Son yarışta kazandı mı? (kaldırılacak ağırlık)
                son_yarista_kazanma = 1.0 if len(at_past) > 0 and at_past.iloc[0]['sonuc_numeric'] == 1 else 0.0
                
                # Son 2 yarışta kaç kez kazandı?
                son2_kazanma = (at_past.head(2)['sonuc_numeric'] == 1).sum() if len(at_past) >= 2 else 0
                
                # Son yarıştaki derece (1 = kazandı, 2+ = derece, yüksek = kötü)
                son_derece = float(at_past.iloc[0]['sonuc_numeric']) if len(at_past) > 0 else 10
                
                # Form trendi (son 3 yarış vs önceki 3 yarış)
                if len(at_past) >= 6:
                    son3_yarislar = at_past.head(3)
                    onceki3_yarislar = at_past.iloc[3:6]
                    son3_kazanma = (son3_yarislar['sonuc_numeric'] == 1).mean()
                    onceki3_kazanma = (onceki3_yarislar['sonuc_numeric'] == 1).mean()
                    form_trend = son3_kazanma - onceki3_kazanma  # Pozitif = iyileşiyor
                else:
                    form_trend = 0
                
                # Benzer koşullarda son performans
                # Benzer koşul = aynı mesafe + pist kombinasyonu (grup çok spesifik olabilir)
                current_mesafe = row.get('mesafe')
                current_pist = row.get('pist')
                
                benzer_kosul = at_past[
                    (at_past['mesafe'] == current_mesafe) &
                    (at_past['pist'] == current_pist)
                ]
                
                if len(benzer_kosul) > 0:
                    # En son benzer koşuldaki performans
                    benzer_son_performans = benzer_kosul.iloc[0]['sonuc_numeric']
                    # 1 = kazandı, diğer değerler = derece (düşük = iyi)
                    benzer_performans_score = 1.0 if benzer_son_performans == 1 else (1.0 / benzer_son_performans) if benzer_son_performans > 0 else 0
                else:
                    benzer_performans_score = 0
                
                # Kullanıcı isteği: son galibiyet etkisini devreden çıkar
                at_son_yarista_kazanma_weighted = 0.0
                
                # Son 2 yarışta kazanma sayısı - 5x ağırlıklandır
                at_son2_yarista_kazanma_weighted = son2_kazanma * 5.0
                
                # Son dereceyi tersine çevir (1 = en iyi, 10 = en kötü) ve normalize et
                at_son_derece_score = max(0, 1.0 - (son_derece - 1) * 0.1) if son_derece >= 1 else 0
                at_son_derece_score_weighted = at_son_derece_score * 5.0  # 5x ağırlıklandır
                
                # Form skorlarını da agresif ölçeklendir
                at_son3_form_weighted = son3_form * 3.0
                at_son5_form_weighted = son5_form * 2.0
                at_benzer_kosul_weighted = benzer_performans_score * 2.0
                
                # Kombine form skoru: sınıf-ağırlıklı ortalama derece ana sinyal (G>KV>...)
                cwr = row.get('at_class_weighted_avg_rank_last6', np.nan)
                if pd.notna(cwr):
                    # 1 en iyi; 10 en kötü → 1.0..0.0 aralığına sıkıştır
                    cls_rank_score = max(0.0, min(1.0, 1.0 - (float(cwr) - 1.0) * 0.12))
                else:
                    cls_rank_score = at_last6_group_score  # fallback

                form_score = (
                    cls_rank_score * 0.55 +
                    son3_form * 0.20 +
                    son5_form * 0.08 +
                    at_son_derece_score * 0.12 +
                    benzer_performans_score * 0.05
                )
                # Form score'u 10x çarparak çok daha agresif hale getir
                form_score_weighted = form_score * 10.0
                
                return pd.Series({
                    'at_son3_form': son3_form,
                    'at_son5_form': son5_form,
                    'at_son3_form_weighted': at_son3_form_weighted,  # YENİ: 3x ağırlıklandırılmış
                    'at_son5_form_weighted': at_son5_form_weighted,  # YENİ: 2x ağırlıklandırılmış
                    'at_son_yarista_kazanma': son_yarista_kazanma,
                    'at_son_yarista_kazanma_weighted': at_son_yarista_kazanma_weighted,  # YENİ: 10x ağırlıklandırılmış
                    'at_son2_yarista_kazanma': son2_kazanma,
                    'at_son2_yarista_kazanma_weighted': at_son2_yarista_kazanma_weighted,  # YENİ: 5x ağırlıklandırılmış
                    'at_form_trend': form_trend,
                    'at_benzer_kosul_son_performans': benzer_performans_score,
                    'at_benzer_kosul_son_performans_weighted': at_benzer_kosul_weighted,  # YENİ: 2x ağırlıklandırılmış
                    'at_son_derece': son_derece,
                    'at_son_derece_score': at_son_derece_score,
                    'at_son_derece_score_weighted': at_son_derece_score_weighted,  # YENİ: 5x ağırlıklandırılmış
                    'at_last6_group_score': at_last6_group_score,
                    'at_form_score': form_score,
                    'at_form_score_weighted': form_score_weighted  # YENİ: 10x ağırlıklandırılmış kombinasyon skoru (EN ÖNEMLİ!)
                })
            
            # Her satır için form feature'larını hesapla
            form_features = df.apply(calculate_form_features, axis=1)
            df = pd.concat([df, form_features], axis=1)
        
        # === SÜRPRİZ ve BALON POTANSİYELİ FEATURE'LARI ===
        # 23. Atın sürpriz potansiyeli ve balon potansiyeli (agf1_sira bazlı)
        if 'agf1_sira' in df.columns and 'at_adi' in df.columns and 'sonuc' in df.columns and 'tarih' in df.columns:
            # Tarihi datetime'a çevir
            if 'tarih_dt' not in df.columns:
                df['tarih_dt'] = pd.to_datetime(df['tarih'], format='%d/%m/%Y', errors='coerce')
            if 'sonuc_numeric' not in df.columns:
                df['sonuc_numeric'] = pd.to_numeric(df['sonuc'], errors='coerce')
            
            # agf1_sira'yı numeric'e çevir
            df['agf1_sira_numeric'] = pd.to_numeric(df['agf1_sira'], errors='coerce')
            
            def calculate_surpriz_balon(row):
                at_adi = row['at_adi']
                current_date = row.get('tarih_dt')
                
                if pd.isna(current_date) or pd.isna(at_adi):
                    return pd.Series({
                        'at_surpriz_potansiyeli': 0,
                        'at_balon_potansiyeli': 0
                    })
                
                # Bu atın son 1 yıldaki koşuları (bugünün koşusu hariç)
                one_year_ago = current_date - pd.Timedelta(days=365)
                at_past = df[
                    (df['at_adi'] == at_adi) & 
                    (df['tarih_dt'] < current_date) &
                    (df['tarih_dt'] >= one_year_ago) &
                    (df['sonuc_numeric'].notna())
                ].copy()
                
                # exclude_dates'teki tarihleri çıkar
                if len(exclude_dates) > 0 and 'tarih' in at_past.columns:
                    at_past = at_past[~at_past['tarih'].isin(exclude_dates)].copy()
                if len(exclude_dates_dt) > 0 and 'tarih_dt' in at_past.columns:
                    at_past = at_past[~at_past['tarih_dt'].isin(exclude_dates_dt)].copy()
                
                if len(at_past) == 0:
                    return pd.Series({
                        'at_surpriz_potansiyeli': 0,
                        'at_balon_potansiyeli': 0
                    })
                
                # agf1_sira'yı numeric'e çevir (varsa)
                if 'agf1_sira_numeric' not in at_past.columns:
                    at_past['agf1_sira_numeric'] = pd.to_numeric(at_past['agf1_sira'], errors='coerce')
                else:
                    at_past['agf1_sira_numeric'] = pd.to_numeric(at_past['agf1_sira'], errors='coerce')
                
                # SÜRPRİZ POTANSİYELİ: agf1_sira 1, 2 veya 3 dışındayken (favori değilken) kaç kez kazandı?
                # agf1_sira > 3 veya NaN ise favori değil demektir
                non_favorite_races = at_past[
                    (at_past['agf1_sira_numeric'].isna()) | 
                    (at_past['agf1_sira_numeric'] > 3)
                ]
                surpriz_kazanma_sayisi = (non_favorite_races['sonuc_numeric'] == 1).sum()
                
                # BALON POTANSİYELİ: agf1_sira 1, 2 veya 3 içindeyken (favoriyken) kaç kez ilk 3'e giremedi?
                # agf1_sira <= 3 ise favori demektir
                favorite_races = at_past[
                    (at_past['agf1_sira_numeric'].notna()) &
                    (at_past['agf1_sira_numeric'] <= 3)
                ]
                balon_sayisi = (favorite_races['sonuc_numeric'] > 3).sum()
                
                return pd.Series({
                    'at_surpriz_potansiyeli': surpriz_kazanma_sayisi,
                    'at_balon_potansiyeli': balon_sayisi
                })
            
            # Her satır için sürpriz/balon feature'larını hesapla
            surpriz_balon_features = df.apply(calculate_surpriz_balon, axis=1)
            df = pd.concat([df, surpriz_balon_features], axis=1)
        
        print(f"✅ {len(df.columns)} feature oluşturuldu")
        return df

    def prepare_features(self, df, exclude_dates=None):
        """Özellikleri hazırla
        
        Args:
            df: Veri çerçevesi
            exclude_dates: Feature hesaplamasından çıkarılacak tarihler listesi (bugünün tarihi gibi)
        """
        target_col = "sonuc"
        group_col = "yaris_kosu_key"
        
        # exclude_dates None ise boş liste yap
        if exclude_dates is None:
            exclude_dates = []
        
        # ÖNEMLİ: exclude_dates'teki tarihleri df'den önce çıkar (training için)
        if len(exclude_dates) > 0 and 'tarih' in df.columns:
            original_len = len(df)
            for exclude_date in exclude_dates:
                if exclude_date in df['tarih'].values:
                    print(f"   🚫 prepare_features: {exclude_date} tarihi df'den çıkarılıyor (exclude_dates)...")
                    df = df[df['tarih'] != exclude_date].copy()
            if original_len != len(df):
                print(f"   ✅ prepare_features: {original_len - len(df)} satır çıkarıldı")
        
        # Bugünün koşuları için üst düzey deneyim hesaplarken geçmiş veriyi de kullan
        # ÖNEMLİ: Bugünün koşularını tarih bazlı kontrol et, sonuc bilgisi olsa bile bugünün koşuları prediction olarak işlenmeli
        today = datetime.now().strftime('%d/%m/%Y')
        is_prediction = False
        if 'tarih' in df.columns:
            today_dates = df['tarih'].unique()
            # Eğer bugünün tarihi varsa, prediction modunda olmalıyız
            if today in today_dates:
                is_prediction = True
            else:
                # Bugünün tarihi yoksa, sonuc bilgisi yoksa prediction modunda olmalıyız
                is_prediction = target_col not in df.columns or df[target_col].notna().sum() == 0
        if is_prediction and 'tarih' in df.columns:
            try:
                # Geçmiş veriyi yükle
                all_data = self.load_data()
                if 'tarih' in all_data.columns:
                    # Bugünün tarihini al (datetime formatında)
                    today_dates_str = df['tarih'].unique()
                    
                    # ÖNEMLİ: exclude_dates'teki tarihleri de çıkar (training'den gelen)
                    exclude_dates_extended = list(today_dates_str)
                    if exclude_dates:
                        exclude_dates_extended.extend(exclude_dates)
                    exclude_dates_extended = list(set(exclude_dates_extended))  # Duplikatları temizle
                    
                    # Geçmiş koşuları al (bugünün tarihi ve exclude_dates dışındaki tüm koşular)
                    # KRİTİK: all_data içinde bugünün verilerini (ganyan, agf1, agf2 dahil) tamamen çıkar
                    past_races = all_data[~all_data['tarih'].isin(exclude_dates_extended)].copy()
                    
                    # Ek kontrol: bugünün tarihi farklı formatlarda olabilir, tüm varyantları çıkar
                    all_dates_str = all_data['tarih'].astype(str).unique()
                    today_variants = [d for d in all_dates_str if any(td in str(d) for td in exclude_dates_extended)]
                    if today_variants:
                        past_races = past_races[~past_races['tarih'].astype(str).isin(today_variants)].copy()
                    
                    excluded_count = len(all_data) - len(past_races)
                    if excluded_count > 0:
                        print(f"   🚫 all_data'dan {excluded_count} satır çıkarıldı (exclude_dates: {exclude_dates_extended})")
                    
                    if len(past_races) > 0:
                        # Geçmiş veriyi de ekleyerek feature'ları oluştur
                        # Böylece üst düzey deneyim hesaplaması geçmiş veriyi de görebilir
                        # Bugünün koşularındaki gelecekteki bilgileri (agf1_sira, agf1, agf2, ganyan) kullanmıyoruz
                        # ÖNEMLİ: Bugünün koşularındaki sonuc bilgisini de kullanmamalıyız!
                        
                        # Bugünün koşularını geçici olarak kopyala ve gelecekteki bilgileri temizle
                        df_clean = df.copy()
                        
                        # Bugünün koşularındaki SONUC bilgisini de temizle (data leakage önleme)
                        if 'sonuc' in df_clean.columns:
                            df_clean['sonuc'] = None
                        
                        # Ganyan ve AGF değerlerini temizle (model eğitimi ve tahminde kullanılmıyor)
                        for col in ['agf1_sira', 'agf1', 'agf2', 'ganyan', 'agf2_sira']:
                            if col in df_clean.columns:
                                df_clean[col] = None
                        
                        # Geçmiş veriyi de ekleyerek feature'ları oluştur
                        df_with_past = pd.concat([past_races, df_clean], ignore_index=True)
                        # Bugünün tarihlerini exclude et (data leakage önleme)
                        all_features = self.create_advanced_features(df_with_past, skip_future_features=False, exclude_dates=list(today_dates_str))
                        
                        # Bugünün koşuları için gelecekteki feature'ları (ganyan_numeric, agf1_numeric, agf2_numeric)
                        today_features = all_features[all_features['tarih'].isin(today_dates_str)].copy()
                        past_features = all_features[~all_features['tarih'].isin(today_dates_str)].copy()
                        
                        # Bugünün koşularındaki SONUC bilgisini de temizle (çünkü create_advanced_features içinde kullanılmış olabilir)
                        if 'sonuc' in today_features.columns:
                            today_features['sonuc'] = None
                        
                        # Ganyan ve AGF feature'larını kaldır (model eğitimi ve tahminde kullanılmıyor)
                        for col in ['ganyan_numeric', 'agf1_numeric', 'agf2_numeric']:
                            if col in today_features.columns:
                                today_features = today_features.drop(columns=[col])
                        
                        df = today_features.copy()
                    else:
                        # Geçmiş veri yoksa normal şekilde devam et (ama gelecekteki feature'ları skip et)
                        df = self.create_advanced_features(df, skip_future_features=True)
                else:
                    # Tarih sütunu yoksa normal şekilde devam et (ama gelecekteki feature'ları skip et)
                    df = self.create_advanced_features(df, skip_future_features=True)
            except Exception as e:
                # Hata olursa normal şekilde devam et (ama gelecekteki feature'ları skip et)
                df = self.create_advanced_features(df, skip_future_features=True)
        else:
            # Geçmiş veri için normal şekilde devam et (ganyan, agf1, agf2 dahil)
            # ÖNEMLİ: Training için kullanılan veride bugünün tarihi olmamalı!
            # exclude_dates parametresinden gelen tarihleri kullan
            training_exclude_dates = list(exclude_dates) if exclude_dates else []
            
            # Ekstra güvenlik: bugünün tarihini de ekle (eğer zaten yoksa)
            today = datetime.now().strftime('%d/%m/%Y')
            if today not in training_exclude_dates:
                training_exclude_dates.append(today)
            
            # KRİTİK: exclude_dates'teki tarihleri df'den KESİNLİKLE çıkar
            # Hem string hem datetime formatında kontrol et
            if len(training_exclude_dates) > 0 and 'tarih' in df.columns:
                before_len = len(df)
                
                # String formatında filtrele
                for exclude_date in training_exclude_dates:
                    if exclude_date in df['tarih'].values:
                        print(f"⚠️ UYARI: Training verisinde {exclude_date} tarihi bulundu! Çıkarılıyor...")
                        df = df[df['tarih'] != exclude_date].copy()
                
                # DateTime formatında da filtrele (ekstra güvenlik)
                if 'tarih_dt' not in df.columns:
                    df['tarih_dt'] = pd.to_datetime(df['tarih'], format='%d/%m/%Y', errors='coerce')
                
                exclude_dates_dt = []
                for date_str in training_exclude_dates:
                    try:
                        dt = pd.to_datetime(date_str, format='%d/%m/%Y', errors='coerce')
                        if pd.notna(dt):
                            exclude_dates_dt.append(dt)
                    except:
                        pass
                
                if len(exclude_dates_dt) > 0:
                    df = df[~df['tarih_dt'].isin(exclude_dates_dt)].copy()
                
                df = df.drop(columns=['tarih_dt'], errors='ignore')
                
                if before_len != len(df):
                    print(f"   ✅ Training'den {before_len - len(df)} satır çıkarıldı")
            
            # Final doğrulama: df içinde exclude_dates'teki tarihler olmamalı
            if 'tarih' in df.columns and len(training_exclude_dates) > 0:
                remaining_excluded = df[df['tarih'].isin(training_exclude_dates)]
                if len(remaining_excluded) > 0:
                    print(f"   ❌ KRİTİK HATA: Training verisinde hala {list(remaining_excluded['tarih'].unique())} tarihleri var!")
                    df = df[~df['tarih'].isin(training_exclude_dates)].copy()
                    print(f"   ✅ Temizlendi: {len(df)} satır kaldı")
            
            # SON KONTROL: df içinde bugünün tarihine ait hiçbir veri olmamalı
            if 'tarih' in df.columns:
                final_check = df[df['tarih'].isin(training_exclude_dates)]
                if len(final_check) > 0:
                    print(f"   ❌ FİNAL KONTROL BAŞARISIZ: {len(final_check)} satır daha var!")
                    df = df[~df['tarih'].isin(training_exclude_dates)].copy()
                    print(f"   ✅ Son temizlik: {len(df)} satır")
            
            print(f"   📊 Training için {len(df)} satır kullanılacak (exclude_dates: {training_exclude_dates})")
            
            # create_advanced_features'a geçirilen df içinde KESİNLİKLE bugünün verisi olmamalı
            df = self.create_advanced_features(df, skip_future_features=False, exclude_dates=training_exclude_dates)
        
        # Sonuc sütunu varsa y ve groups oluştur
        if target_col in df.columns and df[target_col].notna().sum() > 0:
            y = (df[target_col] == 1).astype(int)
            groups = df[group_col].astype(str)
        else:
            # Prediction için sonuc sütunu yok
            y = None
            groups = None
        
        # Niş pist/mesafe etkileri (bucket)
        if 'mesafe_numeric' in df.columns:
            def _bucket(m):
                try:
                    m = float(m)
                except Exception:
                    return 'unknown'
                if m < 1400: return 'short'
                if m < 1800: return 'mid'
                return 'long'
            df['distance_bucket'] = df['mesafe_numeric'].apply(_bucket)
        
        drop_cols = {
            target_col, group_col,
            "at_key", "sahip_kodu", "antrenor_kodu", "jokey_kodu",
            "derece", "fark", "son800", "gec_cikis_boy", "no",
            "grup_seviye_score",  # Geçici feature
            "tarih_dt", "sonuc_numeric",  # Geçici feature'lar
            "tarih",  # Tarih sütunu feature olarak kullanılmaz
            "at_surpriz_potansiyeli", "at_balon_potansiyeli",  # Sadece tahmin çıktısında gösterilecek, modele dahil değil
            "agf1_sira_numeric",  # Geçici feature
            "ganyan_numeric", "agf1_numeric", "agf2_numeric",  # Ganyan ve AGF feature'ları kaldırıldı (model eğitimi ve tahminde kullanılmıyor)
            "ganyan", "agf1", "agf2", "agf1_sira", "agf2_sira"  # Orijinal ganyan/AGF sütunları da kaldırıldı (model eğitimi ve tahminde kullanılmıyor)
        }
        
        X = df.drop(columns=[c for c in drop_cols if c in df.columns]).copy()
        
        # Categorical sütunları belirle (object dtype + categorical dtype)
        cat_cols = [c for c in X.columns if X[c].dtype == "object" or str(X[c].dtype).startswith('category')]
        num_cols = [c for c in X.columns if c not in cat_cols]
        
        # Feature pruning/normalization: clip ve log1p
        if len(num_cols) > 0:
            for c in num_cols:
                try:
                    q1 = X[c].quantile(0.01)
                    q99 = X[c].quantile(0.99)
                    if pd.notna(q1) and pd.notna(q99) and q99 > q1:
                        X[c] = X[c].clip(q1, q99)
                    if X[c].min() >= 0:
                        X[c] = np.log1p(X[c])
                except Exception:
                    continue
            # Yüksek korelasyonlu numeric kolonları düşür
            try:
                corr = X[num_cols].corr().abs()
                upper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))
                to_drop = [column for column in upper.columns if any(upper[column] > 0.98)]
                if to_drop:
                    X = X.drop(columns=[c for c in to_drop if c in X.columns])
                    num_cols = [c for c in num_cols if c not in to_drop]
            except Exception:
                pass
        
        print(f"📊 Özellikler: {len(X.columns)} (Numeric: {len(num_cols)}, Categorical: {len(cat_cols)})")
        
        return X, y, groups, cat_cols, num_cols
    
    def train_ensemble_models(self, X, y, groups, cat_cols, num_cols):
        """Ensemble modelleri eğit (5 Decision Tree + XGBoost + XGBRanker)"""
        print(f"🤖 {self.hipodrom_key} ensemble modelleri eğitiliyor...")
        
        # Categorical feature'ları encode et
        X_enc = X.copy()
        les = {}
        for c in cat_cols:
            le = LabelEncoder()
            # Fit et ve transform et
            X_enc[c] = le.fit_transform(X_enc[c].astype(str))
            les[c] = le
            # Unseen kategoriler için max+1 değerini sakla (prediction için)
            if not hasattr(le, 'unknown_value'):
                le.unknown_value = len(le.classes_)
        
        # Numeric feature'ları impute et
        for c in num_cols:
            if X_enc[c].isna().any():
                median_val = X_enc[c].median()
                X_enc[c] = X_enc[c].fillna(median_val)
                # Training median'larını sakla
                self.numeric_medians[c] = median_val
            else:
                # NaN yoksa bile median'ı sakla (prediction için)
                self.numeric_medians[c] = X_enc[c].median()
        
        self.label_encoders = les  # Sonraki kullanım için sakla
        
        # 1. Decision Tree kısa grid araması ve en iyi 5 konfigürasyonu seçme
        print("🌳 Decision Tree kısa grid araması...")
        candidate_dt = [
            {"max_depth": 8,  "min_samples_split": 10, "min_samples_leaf": 5},
            {"max_depth": 10, "min_samples_split": 5,  "min_samples_leaf": 2},
            {"max_depth": 12, "min_samples_split": 7,  "min_samples_leaf": 3},
            {"max_depth": 15, "min_samples_split": 3,  "min_samples_leaf": 1},
            {"max_depth": 20, "min_samples_split": 2,  "min_samples_leaf": 1},
            {"max_depth": 6,  "min_samples_split": 4,  "min_samples_leaf": 2},
        ]
        # 3-fold group CV ile puanla (GroupKFold deterministik böler)
        gkf_dt = GroupKFold(n_splits=min(3, max(2, len(X_enc)//2)))
        scored = []
        for cfg in candidate_dt:
            aucs = []
            for tr, va in gkf_dt.split(X_enc, y, groups):
                m = DecisionTreeClassifier(random_state=42, **cfg)
                m.fit(X_enc.iloc[tr], y.iloc[tr])
                p = m.predict_proba(X_enc.iloc[va])[:,1]
                try:
                    aucs.append(roc_auc_score(y.iloc[va], p))
                except Exception:
                    pass
            scored.append((np.mean(aucs) if aucs else -1.0, cfg))
        scored.sort(key=lambda x: x[0], reverse=True)
        best_dt_configs = [s[1] for s in scored[:5]]
        print(f"   ✅ En iyi DT konfigürasyonları: {best_dt_configs}")
        dt_models = []
        for i, config in enumerate(best_dt_configs):
            dt = DecisionTreeClassifier(random_state=42+i, **config)
            dt.fit(X_enc, y)
            dt_models.append(dt)
            print(f"   ✅ Decision Tree {i+1} eğitildi")
        
        # 2. XGBoost kısa grid araması
        print("🚀 XGBoost kısa grid araması...")
        xgb_candidates = [
            {"max_depth": 6, "learning_rate": 0.08, "subsample": 0.8, "colsample_bytree": 0.8},
            {"max_depth": 8, "learning_rate": 0.10, "subsample": 0.8, "colsample_bytree": 0.8},
            {"max_depth": 8, "learning_rate": 0.08, "subsample": 1.0, "colsample_bytree": 0.8},
            {"max_depth": 10, "learning_rate": 0.08, "subsample": 0.9, "colsample_bytree": 0.9},
        ]
        gkf_xgb = GroupKFold(n_splits=min(3, max(2, len(X_enc)//2)))
        best_auc, best_cfg = -1.0, None
        for cfg in xgb_candidates:
            aucs = []
            for tr, va in gkf_xgb.split(X_enc, y, groups):
                mdl = xgb.XGBClassifier(n_estimators=300, random_state=42, eval_metric='logloss', **cfg)
                mdl.fit(X_enc.iloc[tr], y.iloc[tr])
                p = mdl.predict_proba(X_enc.iloc[va])[:,1]
                try:
                    aucs.append(roc_auc_score(y.iloc[va], p))
                except Exception:
                    pass
            mean_auc = np.mean(aucs) if aucs else -1.0
            if mean_auc > best_auc:
                best_auc, best_cfg = mean_auc, cfg
        print(f"   ✅ En iyi XGB: {best_cfg} (AUC~{best_auc:.4f})")
        xgb_model = xgb.XGBClassifier(n_estimators=300, random_state=42, eval_metric='logloss', **best_cfg)
        xgb_model.fit(X_enc, y)
        print("   ✅ XGBoost eğitildi")
        
        # 3. XGBRanker Modeli (ranking için)
        print("🏆 XGBRanker kısa grid araması...")
        rank_candidates = [
            {"max_depth": 6, "learning_rate": 0.10, "subsample": 0.8, "colsample_bytree": 0.8},
            {"max_depth": 8, "learning_rate": 0.08, "subsample": 0.9, "colsample_bytree": 0.9},
            {"max_depth": 10, "learning_rate": 0.06, "subsample": 1.0, "colsample_bytree": 0.8},
        ]
        gkf_rank = GroupKFold(n_splits=min(3, max(2, len(X_enc)//2)))
        best_r_auc, best_r_cfg = -1.0, None
        for cfg in rank_candidates:
            aucs = []
            for tr, va in gkf_rank.split(X_enc, y, groups):
                mdl = XGBRanker(n_estimators=300, random_state=42, objective='rank:pairwise', **cfg)
                # group sizes for train split
                tr_groups = groups.iloc[tr]
                tr_counts = tr_groups.value_counts()
                tr_sizes = [tr_counts[g] for g in tr_groups.unique()]
                try:
                    mdl.fit(X_enc.iloc[tr], y.iloc[tr], group=tr_sizes)
                    p = mdl.predict(X_enc.iloc[va])
                    aucs.append(roc_auc_score(y.iloc[va], p))
                except Exception:
                    pass
            mean_auc = np.mean(aucs) if aucs else -1.0
            if mean_auc > best_r_auc:
                best_r_auc, best_r_cfg = mean_auc, cfg
        print(f"   ✅ En iyi XGBRanker: {best_r_cfg} (AUC~{best_r_auc:.4f})")
        xgb_ranker = XGBRanker(n_estimators=300, random_state=42, objective='rank:pairwise', **best_r_cfg)
        group_counts = groups.value_counts()
        group_sizes = [group_counts[g] for g in groups.unique()]
        xgb_ranker.fit(X_enc, y, group=group_sizes)
        print("   ✅ XGBRanker eğitildi")
        
        # 4. Stacking meta-learner (Logistic Regression) - OOF eğitim
        print("🧱 Stacking meta-learner hazırlanıyor (OOF)...")
        n_splits_meta = min(5, max(2, len(X_enc)//2))
        gkf_meta = GroupKFold(n_splits=n_splits_meta)
        oof_meta = np.zeros((len(X_enc), 7), dtype=float)
        for tr_idx, va_idx in gkf_meta.split(X_enc, y, groups):
            X_tr, X_va = X_enc.iloc[tr_idx], X_enc.iloc[va_idx]
            y_tr = y.iloc[tr_idx]
            # Decision Trees (yeniden fit)
            fold_dt_preds = []
            for config in [
                {"max_depth": 10, "min_samples_split": 5, "min_samples_leaf": 2, "random_state": 42},
                {"max_depth": 15, "min_samples_split": 3, "min_samples_leaf": 1, "random_state": 43},
                {"max_depth": 8, "min_samples_split": 10, "min_samples_leaf": 5, "random_state": 44},
                {"max_depth": 12, "min_samples_split": 7, "min_samples_leaf": 3, "random_state": 45},
                {"max_depth": 20, "min_samples_split": 2, "min_samples_leaf": 1, "random_state": 46}
            ]:
                dt_f = DecisionTreeClassifier(**config)
                dt_f.fit(X_tr, y_tr)
                fold_dt_preds.append(dt_f.predict_proba(X_va)[:, 1])
            oof_meta[va_idx, 0:5] = np.column_stack(fold_dt_preds)
            # XGB (yeniden fit)
            xgb_f = xgb.XGBClassifier(
                n_estimators=200, max_depth=8, learning_rate=0.1, subsample=0.8, colsample_bytree=0.8,
                random_state=42, eval_metric='logloss'
            )
            xgb_f.fit(X_tr, y_tr)
            oof_meta[va_idx, 5] = xgb_f.predict_proba(X_va)[:, 1]
            # XGBRanker (fallback olarak sınıflandırıcı skoru)
            try:
                xgbr_f = XGBRanker(
                    n_estimators=200, max_depth=6, learning_rate=0.1, subsample=0.8, colsample_bytree=0.8,
                    random_state=42, objective='rank:pairwise'
                )
                xgbr_f.fit(X_tr, y_tr, group=np.ones(len(X_tr)))
                oof_meta[va_idx, 6] = xgbr_f.predict(X_va)
            except Exception:
                oof_meta[va_idx, 6] = xgb_f.predict_proba(X_va)[:, 1]
            # Bağlam ekle
            # Bağlam ekleme kapalı (use_meta_context=False)
        meta = LogisticRegression(max_iter=1000)
        meta.fit(oof_meta, y.values)
        print("   ✅ Meta-learner eğitildi")

        # Tüm modelleri sakla
        self.ensemble_models = {
            'decision_trees': dt_models,
            'xgboost': xgb_model,
            'xgb_ranker': xgb_ranker,
            'meta': meta
        }
        
        # Cross-validation ile performans değerlendirme
        print("📊 Cross-validation ile performans değerlendiriliyor...")
        n_samples = len(X_enc)
        n_splits = min(5, n_samples // 2)
        if n_splits < 2:
            n_splits = 2
        
        gkf = GroupKFold(n_splits=n_splits)
        all_aucs, all_lls, all_hit1 = [], [], []
        oof_ensemble = np.zeros(len(X_enc))
        
        for tr, va in gkf.split(X_enc, y, groups):
            # Her model için prediction yap
            dt_predictions = []
            for dt in dt_models:
                dt.fit(X_enc.iloc[tr], y.iloc[tr])
                dt_pred = dt.predict_proba(X_enc.iloc[va])[:, 1]
                dt_predictions.append(dt_pred)
            
            xgb_model.fit(X_enc.iloc[tr], y.iloc[tr])
            xgb_pred = xgb_model.predict_proba(X_enc.iloc[va])[:, 1]
            
            # XGBRanker için group bilgilerini hazırla
            tr_groups = groups.iloc[tr]
            tr_group_counts = tr_groups.value_counts()
            tr_group_sizes = []
            for group in tr_groups.unique():
                tr_group_sizes.append(tr_group_counts[group])
            
            xgb_ranker.fit(X_enc.iloc[tr], y.iloc[tr], group=tr_group_sizes)
            xgb_ranker_pred = xgb_ranker.predict(X_enc.iloc[va])
            
            # Ensemble prediction (tüm modellerin ortalaması)
            ensemble_pred = np.mean(dt_predictions + [xgb_pred, xgb_ranker_pred], axis=0)
            oof_ensemble[va] = ensemble_pred
            
            # Metrikleri hesapla
            all_aucs.append(roc_auc_score(y.iloc[va], ensemble_pred))
            all_lls.append(log_loss(y.iloc[va], ensemble_pred))
            
            g = groups.iloc[va].reset_index(drop=True)
            yv = y.iloc[va].reset_index(drop=True)
            pv = pd.Series(ensemble_pred).reset_index(drop=True)
            df_va = pd.DataFrame({"g": g, "y": yv, "p": pv})
            
            hits = []
            for gid, chunk in df_va.groupby("g"):
                if chunk["y"].max() == 0: continue
                hits.append(int(chunk.loc[chunk["p"].idxmax(), "y"] == 1))
            all_hit1.append(np.mean(hits) if hits else np.nan)
        
        # Sonuçları yazdır
        results = {
            "AUC_mean": float(np.nanmean(all_aucs)),
            "AUC_std": float(np.nanstd(all_aucs)),
            "LogLoss_mean": float(np.nanmean(all_lls)),
            "Hit@1_mean": float(np.nanmean(all_hit1)),
            "n_folds": len(all_aucs)
        }
        
        print(f"📊 {self.hipodrom_key} Ensemble Model Sonuçları:")
        print(f"   AUC: {results['AUC_mean']:.4f} ± {results['AUC_std']:.4f}")
        print(f"   Hit@1: {results['Hit@1_mean']:.4f}")
        print(f"   LogLoss: {results['LogLoss_mean']:.4f}")
        
        # Feature importance göster
        try:
            print("\n🔍 Top Feature Importances:")
            # XGBoost feature importance
            xgb_importance = xgb_model.feature_importances_
            feature_names_list = list(X_enc.columns)
            xgb_feat_imp = list(zip(feature_names_list, xgb_importance))
            xgb_feat_imp.sort(key=lambda x: x[1], reverse=True)
            
            print("   📈 XGBoost Top 15:")
            for feat, imp in xgb_feat_imp[:15]:
                print(f"      {feat}: {imp:.4f}")
            
            # H2H feature'ının pozisyonunu kontrol et
            h2h_pos = None
            for i, (feat, imp) in enumerate(xgb_feat_imp):
                if 'h2h' in feat.lower():
                    h2h_pos = i + 1
                    print(f"\n   ⚔️ H2H Feature: '{feat}' - Sıra: #{h2h_pos}, Importance: {imp:.4f}")
                    break
            
            if h2h_pos is None:
                print("\n   ⚔️ H2H Feature: Bulunamadı veya importance = 0")
                
        except Exception as e:
            print(f"   ⚠️ Feature importance gösterilemedi: {e}")
        
        # Final ensemble prediction
        print("🔮 Final ensemble prediction hesaplanıyor...")
        final_predictions = []
        
        # Decision Tree'lerden prediction al
        for dt in dt_models:
            dt_pred = dt.predict_proba(X_enc)[:, 1]
            final_predictions.append(dt_pred)
        
        # XGBoost'tan prediction al
        xgb_pred = xgb_model.predict_proba(X_enc)[:, 1]
        final_predictions.append(xgb_pred)
        
        # XGBRanker'dan prediction al
        xgb_ranker_pred = xgb_ranker.predict(X_enc)
        final_predictions.append(xgb_ranker_pred)
        
        # Tüm modellerin ortalaması
        ensemble_proba = np.mean(final_predictions, axis=0)
        
        # Scaling uygula
        proba_min = np.min(ensemble_proba)
        proba_max = np.max(ensemble_proba)
        proba_range = proba_max - proba_min
        
        if proba_range > 0:
            proba_normalized = (ensemble_proba - proba_min) / proba_range
            proba_all = 0.1 + 0.8 * proba_normalized
        else:
            # TUTARLILIK İÇİN: Sabit bir fallback değeri kullan (np.random.uniform yerine)
            # Eğer tüm olasılıklar aynıysa, sabit bir değer kullan (0.5)
            proba_all = np.full(len(ensemble_proba), 0.5)
        
        # Model ve encoder'ları sakla
        self.model = self.ensemble_models  # Ensemble modelleri sakla
        self.feature_names = list(X_enc.columns)
        
        return self.ensemble_models, proba_all, results
    
    def train_model(self, X, y, groups, cat_cols, num_cols):
        """Modeli eğit - ensemble modelleri kullan"""
        return self.train_ensemble_models(X, y, groups, cat_cols, num_cols)
    
    def save_predictions(self, df, proba_all):
        """Tahminleri kaydet"""
        print(f"💾 {self.hipodrom_key} tahminleri kaydediliyor...")
        
        df["win_proba"] = proba_all
        
        # At adı sütununu bul
        name_col = None
        for c in ["at_adi", "at_ismi", "at"]:
            if c in df.columns:
                name_col = c
                break
        
        # Tüm tahminler
        group_col = "yaris_kosu_key"
        target_col = "sonuc"
        all_keep = [c for c in [group_col, name_col, "win_proba", target_col] if c in df.columns]
        df[all_keep].to_csv(self.output_all, index=False)
        
        # İlk 3 tahmin
        ranked = df.sort_values([group_col, "win_proba"], ascending=[True, False])
        top3 = ranked.groupby(group_col).head(3)
        
        top_keep = [c for c in [group_col, name_col, "win_proba", target_col] if c in df.columns]
        top3[top_keep].to_csv(self.output_top3, index=False)
        
        print(f"✅ Tahminler kaydedildi:")
        print(f"   📄 {self.output_all}")
        print(f"   📄 {self.output_top3}")
    
    def generate_smart_labels(self, df, all_past_data):
        """Her at için akıllı labellar oluştur (modelden bağımsız, sadece çıktı için)"""
        print(f"🏷️ Akıllı labellar oluşturuluyor...")
        
        labels_list = []
        
        for idx, row in df.iterrows():
            at_adi = row.get('at_adi', '')
            jokey_adi = row.get('jokey_adi', '')
            mesafe = row.get('mesafe', '')
            hipodrom_key = row.get('hipodrom_key', self.hipodrom_key)
            yaris_kosu_key = row.get('yaris_kosu_key', '')
            gec_cikis_boy = row.get('gec_cikis_boy', '')
            
            labels = []
            
            # Geçmiş verilerden bu atın geçmiş performansını bul
            at_past = all_past_data[all_past_data['at_adi'] == at_adi].copy()
            
            if len(at_past) == 0:
                labels_list.append('')
                continue
            
            # Sonuc sütununu numeric'e çevir
            at_past['sonuc_numeric'] = pd.to_numeric(at_past['sonuc'], errors='coerce')
            
            # 1. Geç çıkış potansiyeli
            if pd.notna(gec_cikis_boy) and gec_cikis_boy != '':
                try:
                    gec_cikis_val = float(str(gec_cikis_boy).replace(' Boy', '').replace(' Boyun', '').replace(' Burun', '').strip())
                    if gec_cikis_val > 0:
                        labels.append(f"🚦 Geç çıkış potansiyeli")
                except:
                    pass
            
            # 2. Bu jokey-at ikilisiyle daha önce kaç kez kazandı
            if jokey_adi:
                jokey_at_past = at_past[at_past['jokey_adi'] == jokey_adi].copy()
                jokey_kazanma = (jokey_at_past['sonuc_numeric'] == 1).sum()
                if jokey_kazanma > 0:
                    labels.append(f"🏆 Jokey-At: {int(jokey_kazanma)}x kazandı")
            
            # 3. Bu jokey-at ikilisiyle daha önce kaç kez tabelaya (ilk 4'e) girdi
            if jokey_adi:
                jokey_at_past = at_past[at_past['jokey_adi'] == jokey_adi].copy()
                jokey_tabela = ((jokey_at_past['sonuc_numeric'] >= 1) & (jokey_at_past['sonuc_numeric'] <= 4)).sum()
                if jokey_tabela > 0:
                    labels.append(f"📊 Jokey-At: {int(jokey_tabela)}x tabela")
            
            # 4. Bu mesafede daha önce kaç kez kazandı
            if mesafe:
                mesafe_past = at_past[at_past['mesafe'] == mesafe].copy()
                mesafe_kazanma = (mesafe_past['sonuc_numeric'] == 1).sum()
                if mesafe_kazanma > 0:
                    labels.append(f"📏 Mesafe: {int(mesafe_kazanma)}x kazandı")
            
            # 5. Bu şehirde (hipodrom) daha önce kaç kez kazandı
            if hipodrom_key:
                hipodrom_past = at_past[at_past['hipodrom_key'] == hipodrom_key].copy()
                hipodrom_kazanma = (hipodrom_past['sonuc_numeric'] == 1).sum()
                if hipodrom_kazanma > 0:
                    labels.append(f"🏟️ {hipodrom_key}: {int(hipodrom_kazanma)}x kazandı")
            
            # 5.5. Üst grup tecrübesi (G1, G2, G3, KV)
            if 'cins_detay' in df.columns and pd.notna(row.get('cins_detay')):
                current_race_type = str(row['cins_detay']).upper()
                
                # Bugünkü yarış tipini belirle
                is_kv = 'KV' in current_race_type or 'KV-' in current_race_type
                is_g3 = 'G 3' in current_race_type or 'G3' in current_race_type or ' G3' in current_race_type
                is_g2 = 'G 2' in current_race_type or 'G2' in current_race_type or ' G2' in current_race_type
                is_g1 = 'G 1' in current_race_type or 'G1' in current_race_type or ' G1' in current_race_type
                
                # Hangi üst grupları kontrol edeceğiz?
                groups_to_check = []
                
                if is_kv:
                    # KV ise sadece G1, G2, G3
                    groups_to_check = ['G1', 'G2', 'G3']
                elif is_g3:
                    # G3 ise sadece G1, G2
                    groups_to_check = ['G1', 'G2']
                elif is_g2:
                    # G2 ise sadece G1
                    groups_to_check = ['G1']
                elif is_g1:
                    # G1 ise sadece G1 deneyimini göster (kendisi de üst seviye)
                    groups_to_check = ['G1']
                else:
                    # Diğerleri (ŞARTLI, Handikap, Maiden vb) için hepsi
                    groups_to_check = ['G1', 'G2', 'G3', 'KV']
                
                # Her grup için tecrübe sayısını hesapla
                group_experiences = []
                for group in groups_to_check:
                    if group == 'KV':
                        # KV için KV-6, KV-7, KV-8, KV-9 gibi formatları kontrol et
                        kv_past = at_past[at_past['cins_detay'].astype(str).str.contains('KV', case=False, na=False)].copy()
                        kv_count = len(kv_past)
                        if kv_count > 0:
                            group_experiences.append(f"{kv_count}x KV")
                    else:
                        # G1, G2, G3 için - hem "G 1" hem "G1" formatlarını kontrol et
                        group_pattern = group.replace(' ', '')  # G1, G2, G3
                        group_space = f"G {group[-1]}"  # G 1, G 2, G 3
                        group_past = at_past[
                            (at_past['cins_detay'].astype(str).str.contains(group_pattern, case=False, na=False, regex=False)) |
                            (at_past['cins_detay'].astype(str).str.contains(group_space, case=False, na=False, regex=False))
                        ].copy()
                        group_count = len(group_past)
                        if group_count > 0:
                            group_experiences.append(f"{group_count}x {group_pattern}")
                
                if group_experiences:
                    labels.append(f"🏅 {' '.join(group_experiences)}")
            
            # 6. Bu koşudaki rakiplerini daha önce geçti
            if yaris_kosu_key:
                # Aynı koşudaki diğer atları bul
                race_competitors = df[df['yaris_kosu_key'] == yaris_kosu_key]['at_adi'].tolist()
                race_competitors = [c for c in race_competitors if c != at_adi]
                
                if len(race_competitors) > 0:
                    # Bu atın bu rakiplerle karşılaştığı geçmiş koşuları bul
                    beaten_competitors = []
                    for competitor in race_competitors:
                        # Her iki atın da yer aldığı geçmiş koşuları bul
                        competitor_past = all_past_data[all_past_data['at_adi'] == competitor].copy()
                        competitor_past['sonuc_numeric'] = pd.to_numeric(competitor_past['sonuc'], errors='coerce')
                        
                        # Ortak koşuları bul (yaris_kosu_key'e göre)
                        at_races = set(at_past['yaris_kosu_key'].unique())
                        competitor_races = set(competitor_past['yaris_kosu_key'].unique())
                        common_races = at_races & competitor_races
                        
                        if len(common_races) > 0:
                            # Bu koşularda hangi at daha iyi performans göstermiş?
                            for race_key in common_races:
                                at_result = at_past[at_past['yaris_kosu_key'] == race_key]['sonuc_numeric'].values
                                comp_result = competitor_past[competitor_past['yaris_kosu_key'] == race_key]['sonuc_numeric'].values
                                
                                if len(at_result) > 0 and len(comp_result) > 0:
                                    at_derece = at_result[0]
                                    comp_derece = comp_result[0]
                                    
                                    if pd.notna(at_derece) and pd.notna(comp_derece):
                                        # Bu at daha iyi derece yaptıysa (daha küçük sayı = daha iyi)
                                        if at_derece < comp_derece:
                                            beaten_competitors.append(competitor)
                                            break
                    
                    if len(beaten_competitors) > 0:
                        # Tüm rakipleri göster (tekrarsız)
                        uniq_comps = []
                        seen = set()
                        for c in beaten_competitors:
                            if c not in seen:
                                uniq_comps.append(c)
                                seen.add(c)
                        labels.append(f"⚔️ Geçti: {', '.join(uniq_comps)}")
            
            labels_list.append(' '.join(labels) if labels else '')
        
        return labels_list
    
    def save_txt_predictions(self, df, proba_all, all_past_data=None):
        """Tahminleri TXT formatında kaydet"""
        print(f"📝 TXT formatında tahminler kaydediliyor...")
        
        # Win probability ekle
        df = df.copy()
        df['win_proba'] = proba_all
        
        # At adı sütununu bul
        name_col = None
        for c in ["at_adi", "at_ismi", "at"]:
            if c in df.columns:
                name_col = c
                break
        
        # Akıllı labellar oluştur
        if all_past_data is not None:
            smart_labels = self.generate_smart_labels(df, all_past_data)
            df['smart_labels'] = smart_labels
        else:
            df['smart_labels'] = ''
        
        # TXT dosyası oluştur
        txt_file = os.path.join(self.output_dir, f"{self.hipodrom_key}_tahminler.txt")
        
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write(f"🏇 {self.hipodrom_key} AT YARIŞI TAHMİNLERİ\n")
            f.write("=" * 60 + "\n")
            f.write(f"📅 Tarih: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
            f.write(f"📊 Toplam Koşu: {df['yaris_kosu_key'].nunique()}\n")
            f.write(f"📊 Toplam At: {len(df)}\n")
            f.write("=" * 60 + "\n\n")
            
            # Saate göre grupla (koşu no'ya değil)
            if 'saat' in df.columns:
                races = df.groupby('saat')
                print(f"📊 Saate göre gruplandı: {df['saat'].nunique()} farklı saat")
            else:
                # Saat sütunu yoksa yaris_kosu_key'e göre grupla
                races = df.groupby('yaris_kosu_key')
                print(f"⚠️ Saat sütunu yok, yaris_kosu_key'e göre gruplandı")
            
            race_count = 0
            for time_key, race_horses in races:
                race_count += 1
                
                # Win probability'ye göre sırala
                race_horses = race_horses.sort_values('win_proba', ascending=False)
                
                # Cins detay bilgisini al (ilk attan)
                cins_detay = ''
                if 'cins_detay' in race_horses.columns and len(race_horses) > 0:
                    first_horse = race_horses.iloc[0]
                    if pd.notna(first_horse.get('cins_detay')):
                        cins_detay = str(first_horse['cins_detay'])
                
                # Saat bilgisini göster
                if 'saat' in df.columns:
                    if cins_detay:
                        f.write(f"🏁 KOŞU {race_count} - Saat {time_key} - {cins_detay}\n")
                    else:
                        f.write(f"🏁 KOŞU {race_count} - Saat {time_key}\n")
                else:
                    if cins_detay:
                        f.write(f"🏁 KOŞU {race_count} - {cins_detay}\n")
                    else:
                        f.write(f"🏁 KOŞU {race_count}\n")
                f.write("-" * 40 + "\n")
                
                for i, (_, horse) in enumerate(race_horses.iterrows(), 1):
                    prob = horse['win_proba']
                    at_adi = horse[name_col]
                    
                    # Probability'ye göre emoji
                    if prob > 0.7:
                        emoji = "🔥"
                    elif prob > 0.5:
                        emoji = "⭐"
                    elif prob > 0.3:
                        emoji = "📈"
                    else:
                        emoji = "📉"
                    
                    # Sürpriz ve balon potansiyeli etiketleri
                    surpriz = horse.get('at_surpriz_potansiyeli', 0)
                    balon = horse.get('at_balon_potansiyeli', 0)
                    
                    labels = []
                    if not pd.isna(surpriz) and surpriz >= 2:
                        labels.append(f"🎯 Sürpriz:{int(surpriz)}")
                    if not pd.isna(balon) and balon >= 2:
                        labels.append(f"⚠️ Balon:{int(balon)}")
                    
                    # Akıllı labelları ekle
                    smart_label = horse.get('smart_labels', '')
                    if smart_label:
                        labels.append(smart_label)
                    
                    label_str = " " + " ".join(labels) if labels else ""
                    
                    f.write(f"{i:2d}. {emoji} {at_adi:25} - {prob*100:5.1f}%{label_str}\n")
                
                # En yüksek 3'ü vurgula
                f.write(f"\n🎯 En Yüksek 3 Tahmin:\n")
                for i, (_, horse) in enumerate(race_horses.head(3).iterrows(), 1):
                    prob = horse['win_proba']
                    at_adi = horse[name_col]
                    f.write(f"   {i}. {at_adi:25} - {prob*100:5.1f}%\n")
                
                f.write("\n" + "=" * 60 + "\n\n")
            
            # Özet istatistikler
            f.write("📊 ÖZET İSTATİSTİKLER\n")
            f.write("-" * 30 + "\n")
            
            # En yüksek probability'li atlar
            top_horses = df.nlargest(5, 'win_proba')
            f.write(f"🔥 En Yüksek 5 Kazanma Olasılığı:\n")
            for i, (_, horse) in enumerate(top_horses.iterrows(), 1):
                f.write(f"   {i}. {horse[name_col]:25} - {horse['win_proba']*100:5.1f}%\n")
            
            # Probability dağılımı
            f.write(f"\n📈 Probability Dağılımı:\n")
            f.write(f"   En yüksek: {df['win_proba'].max()*100:.1f}%\n")
            f.write(f"   En düşük:  {df['win_proba'].min()*100:.1f}%\n")
            f.write(f"   Ortalama:  {df['win_proba'].mean()*100:.1f}%\n")
        
        print(f"✅ TXT tahminler kaydedildi: {txt_file}")
        return txt_file
    
    def run_full_pipeline(self):
        """Tam pipeline çalıştır"""
        print(f"🏇 {self.hipodrom_key} At Yarışı Tahmin Sistemi")
        print("=" * 50)
        
        # 1. Veri indir
        if not self.download_data():
            return False
        
        # 2. Veri yükle
        df = self.load_data()
        if df is None:
            return False
        
        # 3. Training ve prediction verilerini ayır
        train_df, predict_df = self.split_train_predict(df)
        
        if predict_df is None:
            print("❌ Bugünün koşuları bulunamadı!")
            return False
        
        # 4. Training verisi ile modeli eğit
        X_train, y_train, groups_train, cat_cols, num_cols = self.prepare_features(train_df)
        clf, _, results = self.train_model(X_train, y_train, groups_train, cat_cols, num_cols)
        
        # 5. Bugünün koşuları için tahmin yap
        print(f"\n🔮 Bugünün koşuları için tahmin yapılıyor...")
        X_predict, _, _, _, _ = self.prepare_features(predict_df)
        
        # Sadece training'de olan kolonları kullan
        # Eksik kolonları ekle (bugünün koşuları için drop edilen sütunlar)
        missing_cols = set(X_train.columns) - set(X_predict.columns)
        if missing_cols:
            # Eksik kolonları ekle ve geçmiş verilerden median ile doldur
            for col in missing_cols:
                if col in num_cols:
                    # Numeric sütunlar için median kullan
                    if col in self.numeric_medians:
                        X_predict[col] = self.numeric_medians[col]
                    else:
                        # Eğer median yoksa, training'den median al
                        if col in X_train.columns:
                            median_val = X_train[col].median()
                            X_predict[col] = median_val
                        else:
                            X_predict[col] = 0
                elif col in cat_cols:
                    # Categorical sütunlar için en sık kullanılan değeri kullan
                    if col in X_train.columns:
                        most_common = X_train[col].mode()
                        if len(most_common) > 0:
                            X_predict[col] = most_common.iloc[0]
                        else:
                            X_predict[col] = 0
                    else:
                        X_predict[col] = 0
                else:
                    # Bilinmeyen tip için 0 kullan
                    X_predict[col] = 0
        
        X_predict = X_predict[X_train.columns]
        
        # Random Forest için categorical feature'ları encode et
        X_predict_enc = X_predict.copy()
        for c in cat_cols:
            if c in X_predict_enc.columns:
                le = self.label_encoders.get(c)
                if le is not None:
                    # Bilinmeyen kategoriler için max+1 değerini kullan (eğitilmemiş kategori)
                    unknown_val = getattr(le, 'unknown_value', len(le.classes_))
                    X_predict_enc[c] = X_predict_enc[c].apply(
                        lambda v: le.transform([v])[0] if v in le.classes_ else unknown_val
                    )
        
        # Numeric feature'ları impute et (training median'larını kullan)
        for c in num_cols:
            if c in X_predict_enc.columns:
                # Training median'ını kullan (prediction verisinin median'ı değil!)
                median_val = self.numeric_medians.get(c, X_predict_enc[c].median())
                if X_predict_enc[c].isna().any():
                    X_predict_enc[c] = X_predict_enc[c].fillna(median_val)
        
        # Ensemble tahmin yap
        print("🔮 Ensemble prediction yapılıyor...")
        ensemble_predictions = []
        
        # Decision Tree'lerden prediction al
        for i, dt in enumerate(self.ensemble_models['decision_trees']):
            dt_pred = dt.predict_proba(X_predict_enc)[:, 1]
            ensemble_predictions.append(dt_pred)
            print(f"   ✅ Decision Tree {i+1} prediction tamamlandı")
        
        # XGBoost'tan prediction al
        xgb_pred = self.ensemble_models['xgboost'].predict_proba(X_predict_enc)[:, 1]
        ensemble_predictions.append(xgb_pred)
        print("   ✅ XGBoost prediction tamamlandı")
        
        # XGBRanker'dan prediction al
        xgb_ranker_pred = self.ensemble_models['xgb_ranker'].predict(X_predict_enc)
        ensemble_predictions.append(xgb_ranker_pred)
        print("   ✅ XGBRanker prediction tamamlandı")
        
        # Stacking/meta veya bağlama göre sabit ağırlıklarla birleştir
        try:
            meta_input = np.column_stack(ensemble_predictions)  # (n_samples, 7)
            # Model skorlarını re-rank ve konsensus için df'e ekle
            try:
                for mj in range(meta_input.shape[1]):
                    predict_df[f'model_score_{mj+1}'] = meta_input[:, mj]
            except Exception:
                pass
            if 'meta' in self.ensemble_models:
                # Bağlam ağırlıkları aktifse sabit ağırlıklı ortalama uygula
                if self.use_context_weights and 'cins_detay' in predict_df.columns:
                    proba_raw = np.zeros(meta_input.shape[0])
                    # Model sırası: DT1..DT5, XGB, XGBR
                    for i in range(meta_input.shape[0]):
                        cins = str(predict_df.iloc[i].get('cins_detay','')).upper()
                        cls_w = predict_df.iloc[i].get('race_class_weight', None)
                        high = False
                        if cls_w is not None:
                            high = cls_w >= 0.8
                        else:
                            high = ('G1' in cins) or ('G 1' in cins) or ('G2' in cins) or ('G 2' in cins) or ('G3' in cins) or ('G 3' in cins) or ('KV' in cins)
                        # Maiden/Şartlı 1 tespiti
                        maiden_s1 = ('MAID' in cins) or ('ŞARTLI 1' in cins) or ('SARTLI 1' in cins)
                        # Ağırlık vektörü
                        if maiden_s1:
                            # Maiden/Şartlı1: form/pist-uyumu (XGB yüksek), Ranker düşük
                            w = np.array([0.06,0.06,0.06,0.06,0.06,0.60,0.10])
                        elif high:
                            # Yüksek sınıf: Ranker en yüksek, XGB ikinci; DT'ler minimal
                            w = np.array([0.03,0.03,0.03,0.03,0.03,0.27,0.60])
                        else:
                            # Düşük sınıf: DT'ler kısık, XGB daha yüksek, Ranker orta
                            w = np.array([0.06,0.06,0.06,0.06,0.06,0.48,0.22])
                        proba_raw[i] = float(np.dot(meta_input[i], w))
                    print("   🎯 Koşu tipi bazlı sabit ağırlıklarla birleştirildi")
                else:
                    proba_raw = self.ensemble_models['meta'].predict_proba(meta_input)[:, 1]
                    print("   🧱 Meta-learner ile birleştirildi")
            else:
                proba_raw = np.mean(ensemble_predictions, axis=0)
                print(f"   🎯 {len(ensemble_predictions)} modelin ortalaması alındı")
        except Exception:
            proba_raw = np.mean(ensemble_predictions, axis=0)
            print(f"   🎯 {len(ensemble_predictions)} modelin ortalaması alındı")
        
        # Head-to-Head (kim kimi geçti) boost'u uygula — GEÇİCİ OLARAK DEVRE DIŞI (izolasyon)
        try:
            pass  # H2H aktif
            def _class_weight_local(c):
                s = str(c).upper()
                if 'G 1' in s or 'G1' in s:
                    return 1.4
                if 'G 2' in s or 'G2' in s:
                    return 1.2
                if 'G 3' in s or 'G3' in s:
                    return 1.0
                if 'KV' in s:
                    return 0.8
                if 'ŞARTLI' in s or 'SARTLI' in s:
                    return 0.5
                if 'HANDIKAP' in s or 'HANDİKAP' in s:
                    return 0.45
                if 'MAIDEN' in s:
                    return 0.35
                if 'SATIŞ' in s or 'SATIS' in s:
                    return 0.3
                return 0.4

            def _bucket(m):
                try:
                    m = float(m)
                except:
                    return 'mid'
                if m < 1400:
                    return 'short'
                if m <= 2000:
                    return 'mid'
                return 'long'
            
            def mesafe_similarity(m1, m2):
                """Mesafe benzerliği - ±200m içinde tam benzer, sonra azalan"""
                try:
                    m1 = float(m1)
                    m2 = float(m2)
                    diff = abs(m1 - m2)
                    if diff <= 200:
                        return 1.0
                    if diff <= 400:
                        return 0.85
                    if diff <= 600:
                        return 0.7
                    if diff <= 1000:
                        return 0.5
                    return 0.3
                except:
                    return 0.5

            # Geçmiş veri (rakip karşılaştırmaları için)
            hist = self.load_data()
            if 'tarih' in hist.columns and 'sonuc' in hist.columns:
                if 'tarih_dt' not in hist.columns:
                    hist['tarih_dt'] = pd.to_datetime(hist['tarih'], format='%d/%m/%Y', errors='coerce')
                hist = hist[hist['sonuc'].notna()].copy()
                hist['rank_num'] = pd.to_numeric(hist['sonuc'], errors='coerce')
                # Bugünün verilerini ve bugünkü yarış anahtarlarını açıkça hariç tut
                try:
                    pred_dates = set(predict_df['tarih'].dropna().unique()) if 'tarih' in predict_df.columns else set()
                    if pred_dates:
                        hist = hist[~hist['tarih'].isin(pred_dates)].copy()
                except Exception:
                    pass
                try:
                    if 'yaris_kosu_key' in hist.columns and 'yaris_kosu_key' in predict_df.columns:
                        cur_keys = set(predict_df['yaris_kosu_key'].dropna().unique())
                        if cur_keys:
                            hist = hist[~hist['yaris_kosu_key'].isin(cur_keys)].copy()
                except Exception:
                    pass
            else:
                hist = None

            boosts = np.zeros(len(predict_df))
            # Index -> position haritası
            idx_to_pos = {idx: pos for pos, idx in enumerate(predict_df.index.tolist())}
            if hist is not None and {'at_adi'}.issubset(predict_df.columns):
                # Grup sütunu: tercihen 'saat' varsa onunla, yoksa 'yaris_kosu_key'
                group_col = 'saat' if 'saat' in predict_df.columns else ('yaris_kosu_key' if 'yaris_kosu_key' in predict_df.columns else None)
                groups = [('', predict_df)] if group_col is None else predict_df.groupby(group_col)
                for g_key, g_df in groups:
                    idxs = g_df.index.tolist()
                    horses = g_df['at_adi'].astype(str).tolist() if 'at_adi' in g_df.columns else []
                    if len(horses) < 2:
                        continue
                    # Mevcut yarışın bağlamı
                    cur_m = g_df.get('mesafe', pd.Series(index=g_df.index)).iloc[0] if 'mesafe' in g_df.columns and len(g_df)>0 else np.nan
                    cur_p = str(g_df.get('pist', pd.Series(index=g_df.index)).iloc[0]).lower() if 'pist' in g_df.columns and len(g_df)>0 else ''
                    cur_b = _bucket(cur_m)
                    def pist_sim(p):
                        pl = str(p).lower()
                        if pl == cur_p:
                            return 1.0
                        sands = {'kum','sentetik'}
                        return 0.7 if (pl in sands and cur_p in sands) else 0.5

                    # Çiftler için üstünlük matrisi
                    h2h_score = {h: 0.0 for h in horses}
                    for i, hi in enumerate(horses):
                        for j, hj in enumerate(horses):
                            if i == j:
                                continue
                            # İki atın birlikte koştuğu geçmiş yarışlar
                            mask = hist['at_adi'].isin([hi, hj])
                            common_keys = hist[mask]['yaris_kosu_key'].dropna().unique() if 'yaris_kosu_key' in hist.columns else []
                            pair_score = 0.0
                            for rk in common_keys:
                                r = hist[hist['yaris_kosu_key'] == rk]
                                if hi not in set(r['at_adi']) or hj not in set(r['at_adi']):
                                    continue
                                ri = r[r['at_adi'] == hi]
                                rj = r[r['at_adi'] == hj]
                                if len(ri)==0 or len(rj)==0:
                                    continue
                                ri_rank = float(ri['rank_num'].iloc[0]) if pd.notna(ri['rank_num'].iloc[0]) else np.nan
                                rj_rank = float(rj['rank_num'].iloc[0]) if pd.notna(rj['rank_num'].iloc[0]) else np.nan
                                if np.isnan(ri_rank) or np.isnan(rj_rank):
                                    continue
                                better = 1.0 if ri_rank < rj_rank else (-1.0 if ri_rank > rj_rank else 0.0)
                                cw = _class_weight_local(r['cins_detay'].iloc[0]) if 'cins_detay' in r.columns and len(r)>0 else 0.4
                                # Recency ağırlığı
                                rec = 1.0
                                if 'tarih_dt' in r.columns and pd.notna(r['tarih_dt'].iloc[0]):
                                    days = (pd.Timestamp.now() - r['tarih_dt'].iloc[0]).days
                                    rec = float(np.exp(-max(0, days)/90.0))
                                # Mesafe/pist benzerliği - benzer koşulda geçme daha önemli
                                r_mesafe = r['mesafe'].iloc[0] if 'mesafe' in r.columns and len(r)>0 else np.nan
                                r_pist = r['pist'].iloc[0] if 'pist' in r.columns and len(r)>0 else ''
                                
                                # Mesafe benzerliği (±200m içinde tam benzer)
                                db = mesafe_similarity(cur_m, r_mesafe) if not pd.isna(cur_m) and not pd.isna(r_mesafe) else 0.5
                                
                                # Pist türü benzerliği
                                ps = pist_sim(r_pist) if r_pist else 0.5
                                
                                # Benzer koşulda geçme durumu çok daha önemli
                                # Aynı mesafe/pist türünde geçme durumu 2x ağırlıklandırılır
                                similarity_boost = 1.0
                                if db >= 0.85 and ps >= 0.85:  # Çok benzer koşullar
                                    similarity_boost = 2.5  # Çok daha önemli
                                elif db >= 0.7 and ps >= 0.7:  # Benzer koşullar
                                    similarity_boost = 1.8
                                elif db >= 0.5 or ps >= 0.7:  # Orta benzerlik
                                    similarity_boost = 1.3
                                
                                w = cw * rec * db * ps * similarity_boost
                                pair_score += better * w
                            h2h_score[hi] += pair_score
                    # Normalize ve z-score
                    vals = np.array([h2h_score[h] for h in horses], dtype=float)
                    if np.allclose(vals.max(), vals.min()):
                        z = np.zeros_like(vals)
                    else:
                        z = (vals - vals.mean()) / (vals.std() + 1e-6)
                    # Boost katsayısı - benzer koşullarda geçme durumu daha önemli olduğu için artırıldı
                    alpha = 1.5  # Daha önce 1.2 idi
                    for k, row_idx in enumerate(idxs):
                        pos = idx_to_pos.get(row_idx, None)
                        if pos is not None and 0 <= pos < len(boosts):
                            boosts[pos] = alpha * z[k]

            # Probaları logit düzeyinde ayarla
            eps = 1e-5
            clipped = np.clip(proba_raw, eps, 1 - eps)
            logits = np.log(clipped / (1.0 - clipped))
            logits = logits + boosts
            proba_raw = 1.0 / (1.0 + np.exp(-logits))
            print("   ⚔️ H2H boost uygulandı")
        except Exception as e:
            print(f"   ⚠️ H2H boost atlandı: {e}")

        # Her koşu için ayrı scaling uygula
        proba_all = np.zeros(len(proba_raw))
        
        # Koşu bazında grupla ve her grup için ayrı scaling yap (öncelik: saat → yaris_kosu_key → (tarih,kosu_no,hipodrom))
        group_field = None
        if 'yaris_kosu_key' in predict_df.columns:
            group_field = 'yaris_kosu_key'
        elif 'saat' in predict_df.columns:
            group_field = 'saat'
        elif all(col in predict_df.columns for col in ['tarih','kosu_no','hipodrom']):
            group_field = ['tarih','kosu_no','hipodrom']

        if group_field is not None:
            # Orijinal index → pozisyon haritası
            idx_to_pos_scale = {idx: pos for pos, idx in enumerate(predict_df.index.tolist())}
            grouped = predict_df.groupby(group_field)
            for g_key, group_index_labels in grouped.groups.items():
                positions = [idx_to_pos_scale[idx] for idx in list(group_index_labels)]
                group_proba = proba_raw[positions]
                if self.use_softmax_calibration:
                    # Softmax (temperature) + eşit skor fallback'ı (rank-based)
                    n = len(group_proba)
                    if n == 0:
                        group_scaled = np.array([])
                    else:
                        arr = np.asarray(group_proba, dtype=float)
                        if np.allclose(arr.max(), arr.min()) or (np.std(arr) < 1e-9):
                            # Tümü eşit ise rank tabanlı
                            # Stabil tiebreak: index sırasına göre çok küçük pertürbasyon ekle
                            tiny = 1e-6 * np.arange(n)[::-1]
                            order = np.argsort(-(arr + tiny))
                            ranks = np.empty(n, dtype=int)
                            ranks[order] = np.arange(n)
                            weights = (n - ranks).astype(float)
                            denom = weights.sum()
                            group_scaled = weights / denom if denom > 0 else np.ones(n) / n
                        else:
                            t = max(1e-3, float(getattr(self, 'softmax_temperature', 1.0)))
                            logits = arr / t
                            logits = logits - np.max(logits)
                            exps = np.exp(logits)
                            denom = exps.sum()
                            probs = exps / denom if denom > 0 else np.ones(n) / n
                            group_scaled = probs
                else:
                    proba_min = np.min(group_proba)
                    proba_max = np.max(group_proba)
                    proba_range = proba_max - proba_min
                    if proba_range > 0:
                        proba_normalized = (group_proba - proba_min) / proba_range
                        group_scaled = 0.1 + 0.8 * proba_normalized
                    else:
                        # Uniform yerine rank tabanlı dağıtım
                        n = len(group_proba)
                        arr = np.asarray(group_proba, dtype=float)
                        tiny = 1e-6 * np.arange(n)[::-1]
                        order = np.argsort(-(arr + tiny))
                        ranks = np.empty(n, dtype=int)
                        ranks[order] = np.arange(n)
                        weights = (n - ranks).astype(float)
                        denom = weights.sum()
                        group_scaled = weights / denom if denom > 0 else np.ones(n) / n

                # Son kontrol: hâlâ tüm değerler eşitse rank-based'e zorla
                if len(group_proba) > 1:
                    uniq = np.unique(np.round(group_scaled, 6))
                    if uniq.size == 1:
                        n = len(group_proba)
                        arr = np.asarray(group_proba, dtype=float)
                        tiny = 1e-6 * np.arange(n)[::-1]
                        order = np.argsort(-(arr + tiny))
                        ranks = np.empty(n, dtype=int)
                        ranks[order] = np.arange(n)
                        weights = (n - ranks).astype(float)
                        denom = weights.sum()
                        group_scaled = weights / denom if denom > 0 else np.ones(n) / n
                
                # Top-1 re-rank: H2H + sınıf-ağırlıklı rank + form ile küçük bonus ve yeniden normalize
                try:
                    def _nz_norm(x):
                        x = np.asarray(x, dtype=float)
                        if x.size == 0:
                            return x
                        mn, mx = np.nanmin(x), np.nanmax(x)
                        if not np.isfinite(mn) or not np.isfinite(mx) or mx - mn < 1e-9:
                            return np.zeros_like(x)
                        return (x - mn) / (mx - mn)

                    # H2H z skorlarını tekrar üretmeyelim; bonusu mevcut sinyallerden türet
                    # Kullan: düşük 'at_class_weighted_avg_rank_last6' daha iyi → 1/rank normalize
                    cls_rank = predict_df.loc[list(group_index_labels)].get('at_class_weighted_avg_rank_last6')
                    cls_inv = None
                    if cls_rank is not None and hasattr(cls_rank, 'to_numpy'):
                        arr = pd.to_numeric(cls_rank, errors='coerce').to_numpy()
                        with np.errstate(divide='ignore', invalid='ignore'):
                            inv = 1.0 / np.clip(arr, 1e-6, None)
                        cls_inv = _nz_norm(inv)
                    else:
                        cls_inv = np.zeros(len(positions))

                    form_w = predict_df.loc[list(group_index_labels)].get('at_form_score_weighted')
                    if form_w is not None and hasattr(form_w, 'to_numpy'):
                        form_n = _nz_norm(pd.to_numeric(form_w, errors='coerce').to_numpy())
                    else:
                        form_n = np.zeros(len(positions))

                    oppq = predict_df.loc[list(group_index_labels)].get('at_opponent_quality_last6')
                    if oppq is not None and hasattr(oppq, 'to_numpy'):
                        opp_n = _nz_norm(pd.to_numeric(oppq, errors='coerce').to_numpy())
                    else:
                        opp_n = np.zeros(len(positions))

                    # Per-race prior: sınıf ağırlığı + pist/mesafe uyumu
                    # Sınıf
                    rcw = predict_df.loc[list(group_index_labels)].get('race_class_weight')
                    class_prior = _nz_norm(pd.to_numeric(rcw, errors='coerce').to_numpy()) if rcw is not None else np.zeros(len(positions))
                    # Pist deneyim ve mesafe başarısı
                    pist_den = predict_df.loc[list(group_index_labels)].get('at_bu_pist_deneyim')
                    pist_prior = _nz_norm(pd.to_numeric(pist_den, errors='coerce').to_numpy()) if pist_den is not None else np.zeros(len(positions))
                    mesafe_bas = predict_df.loc[list(group_index_labels)].get('at_mesafe_basari')
                    mesafe_prior = _nz_norm(pd.to_numeric(mesafe_bas, errors='coerce').to_numpy()) if mesafe_bas is not None else np.zeros(len(positions))
                    
                    # ±200m mesafe band başarısı
                    mesafe_band = predict_df.loc[list(group_index_labels)].get('at_mesafe_band_basari')
                    mesafe_band_prior = _nz_norm(pd.to_numeric(mesafe_band, errors='coerce').to_numpy()) if mesafe_band is not None else np.zeros(len(positions))
                    
                    # Pist türü başarısı
                    pist_tur = predict_df.loc[list(group_index_labels)].get('at_pist_tur_basari')
                    pist_tur_prior = _nz_norm(pd.to_numeric(pist_tur, errors='coerce').to_numpy()) if pist_tur is not None else np.zeros(len(positions))
                    
                    # H2H genel skoru - kim kimi geçti
                    h2h_genel = predict_df.loc[list(group_index_labels)].get('at_h2h_genel_skor')
                    h2h_prior = _nz_norm(pd.to_numeric(h2h_genel, errors='coerce').to_numpy()) if h2h_genel is not None else np.zeros(len(positions))

                    # Model konsensüsü: 7 skorun std'si düşükse yüksek anlaşma
                    try:
                        mcols = [f'model_score_{k+1}' for k in range(7)]
                        mstack = np.vstack([pd.to_numeric(predict_df.loc[list(group_index_labels)][c], errors='coerce').to_numpy() for c in mcols])
                        stds = np.nanstd(mstack, axis=0)
                        cons = 1.0 - _nz_norm(stds)
                    except Exception:
                        cons = np.zeros(len(positions))

                    # Bonus ağırlıkları (mesafe band + pist türü + H2H eklendi)
                    bonus = (
                        0.13 * cls_inv +
                        0.10 * form_n +
                        0.06 * opp_n +
                        0.08 * class_prior +
                        0.06 * pist_prior +
                        0.05 * mesafe_prior +
                        0.04 * mesafe_band_prior +
                        0.04 * pist_tur_prior +
                        0.04 * h2h_prior +  # H2H genel skor eklendi
                        0.05 * cons
                    )
                    boosted = group_scaled + bonus
                    boosted = np.clip(boosted, 1e-9, None)
                    boosted = boosted / boosted.sum()
                    group_scaled = boosted
                except Exception:
                    pass

                proba_all[positions] = group_scaled
        else:
            # Saat sütunu yoksa genel scaling
            proba_min = np.min(proba_raw)
            proba_max = np.max(proba_raw)
            proba_range = proba_max - proba_min
            
            if proba_range > 0:
                proba_normalized = (proba_raw - proba_min) / proba_range
                proba_all = 0.1 + 0.8 * proba_normalized
            else:
                # TUTARLILIK İÇİN: Sabit bir fallback değeri kullan (np.random.uniform yerine)
                # Eğer tüm olasılıklar aynıysa, sabit bir değer kullan (0.5)
                proba_all = np.full(len(proba_raw), 0.5)
        
        # 6. Tahminleri TXT formatında kaydet
        predict_df['win_proba'] = proba_all
        
        # Sürpriz ve balon potansiyeli feature'larını ekle (sadece gösterim için, modele dahil değil)
        predict_features = self.create_advanced_features(predict_df)
        if 'at_surpriz_potansiyeli' in predict_features.columns and 'at_balon_potansiyeli' in predict_features.columns:
            predict_df = predict_df.merge(
                predict_features[['at_adi', 'at_surpriz_potansiyeli', 'at_balon_potansiyeli']],
                on='at_adi',
                how='left',
                suffixes=('', '_features')
            )
        
        # Geçmiş veriyi al (labellar için)
        all_past_data = train_df.copy()
        
        # CSV dosyalarını kaydet
        self.save_predictions(predict_df, proba_all)
        
        # TXT dosyasını kaydet
        txt_file = self.save_txt_predictions(predict_df, proba_all, all_past_data=all_past_data)
        
        print(f"🎉 {self.hipodrom_key} tahmin sistemi tamamlandı!")
        print(f"📄 TXT dosyası: {txt_file}")
        return True

def main():
    """Ana fonksiyon"""
    import sys
    
    if len(sys.argv) > 1:
        hipodrom_key = sys.argv[1]
    else:
        hipodrom_key = input("Hipodrom anahtarı girin (örn: KOCAELI, ISTANBUL): ").strip()
    
    if not hipodrom_key:
        print("❌ Hipodrom anahtarı gerekli!")
        return
    
    predictor = HorseRacingPredictor(hipodrom_key)
    success = predictor.run_full_pipeline()
    
    if success:
        print(f"\n🚀 {hipodrom_key} için tahmin sistemi başarıyla çalıştırıldı!")
    else:
        print(f"\n❌ {hipodrom_key} için tahmin sistemi başarısız!")

if __name__ == "__main__":
    main()
