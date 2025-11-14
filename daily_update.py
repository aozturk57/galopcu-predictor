#!/usr/bin/env python3
"""
Günlük Otomatik Güncelleme Scripti
- CSV dosyalarını kontrol eder
- Bugün koşu olan şehirleri tespit eder
- O şehirler için tahmin çalıştırır
"""

import os
import sys
import pandas as pd
from datetime import datetime
from pathlib import Path
import subprocess

# Proje dizini
BASE_DIR = Path(__file__).parent

def get_cities_with_races_today():
    """Bugün koşu olan şehirleri tespit et"""
    data_dir = BASE_DIR / 'data'
    today = datetime.now().strftime('%d/%m/%Y')
    
    cities_with_races = []
    
    # Tüm CSV dosyalarını kontrol et
    for csv_file in data_dir.glob('*_races.csv'):
        try:
            # Şehir adını dosya adından çıkar (örn: ISTANBUL_races.csv -> ISTANBUL)
            city_name = csv_file.stem.replace('_races', '').upper()
            
            # CSV'yi oku
            df = pd.read_csv(csv_file, encoding='utf-8')
            
            # Bugün koşu var mı kontrol et
            if 'tarih' in df.columns:
                today_races = df[df['tarih'] == today]
                if len(today_races) > 0:
                    cities_with_races.append(city_name)
                    print(f"✅ {city_name}: Bugün {len(today_races)} at var")
        except Exception as e:
            print(f"⚠️ {csv_file.name} okunurken hata: {e}")
            continue
    
    return sorted(cities_with_races)

def run_predictions_for_cities(cities):
    """Belirtilen şehirler için tahmin çalıştır"""
    print(f"\n🎯 {len(cities)} şehir için tahmin çalıştırılıyor...")
    
    for city in cities:
        print(f"\n{'='*50}")
        print(f"🏇 {city} tahminleri oluşturuluyor...")
        print(f"{'='*50}")
        
        try:
            result = subprocess.run(
                ['python3', 'predict.py', city],
                cwd=BASE_DIR,
                capture_output=True,
                text=True,
                timeout=600  # 10 dakika timeout
            )
            
            if result.returncode == 0:
                print(f"✅ {city} tahminleri başarıyla oluşturuldu")
            else:
                print(f"❌ {city} tahminleri oluşturulurken hata:")
                print(result.stderr)
        except subprocess.TimeoutExpired:
            print(f"⏱️ {city} tahminleri zaman aşımına uğradı (10 dakika)")
        except Exception as e:
            print(f"❌ {city} tahminleri çalıştırılırken hata: {e}")

def main():
    """Ana fonksiyon"""
    print("="*60)
    print("🔄 Günlük Otomatik Güncelleme Başlatılıyor...")
    print(f"📅 Tarih: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("="*60)
    
    # Bugün koşu olan şehirleri bul
    cities_with_races = get_cities_with_races_today()
    
    if not cities_with_races:
        print("\n⚠️ Bugün hiçbir şehirde koşu bulunamadı!")
        return
    
    print(f"\n📊 Bugün koşu olan şehirler: {', '.join(cities_with_races)}")
    
    # Tahminleri çalıştır
    run_predictions_for_cities(cities_with_races)
    
    print("\n" + "="*60)
    print("✅ Günlük otomatik güncelleme tamamlandı!")
    print("="*60)

if __name__ == '__main__':
    main()


