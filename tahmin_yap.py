#!/usr/bin/env python3
"""
At yarışı tahmin sistemi - Ana kullanım dosyası
"""

import sys
import os
from horse_racing_predictor import HorseRacingPredictor

def main():
    """Ana fonksiyon"""
    if len(sys.argv) != 2:
        print("❌ Kullanım: python3 tahmin_yap.py <HIPODROM>")
        print("📋 Mevcut hipodromlar: ANKARA, IZMIR")
        print("📝 Örnek: python3 tahmin_yap.py ANKARA")
        sys.exit(1)
    
    hipodrom_key = sys.argv[1].upper()
    
    print(f"🏇 {hipodrom_key} At Yarışı Tahmin Sistemi")
    print("=" * 50)
    
    try:
        predictor = HorseRacingPredictor(hipodrom_key)
        success = predictor.run_full_pipeline()
        
        if success:
            print(f"\n🎉 {hipodrom_key} tahminleri başarıyla tamamlandı!")
            print(f"📄 Çıktı dosyası: output/{hipodrom_key}_tahminler.txt")
        else:
            print(f"\n❌ {hipodrom_key} tahminleri başarısız!")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ Hata: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()