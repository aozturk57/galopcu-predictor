#!/usr/bin/env python3
"""
At Yarışı Tahmin Sistemi - Hızlı Kullanım
"""

import sys
from horse_racing_predictor import HorseRacingPredictor

def main():
    print("🏇 At Yarışı Tahmin Sistemi")
    print("=" * 40)
    
    if len(sys.argv) != 2:
        print("Kullanım: python3 predict.py [HİPODROM_ADI]")
        print("Örnek: python3 predict.py ISTANBUL")
        print("\nMevcut hipodromlar:")
        print("- ISTANBUL (API'den çekilir)")
        print("- KOCAELI (yerel veri)")
        return
    
    hipodrom = sys.argv[1].upper()
    
    print(f"🎯 Hedef: {hipodrom}")
    print("-" * 40)
    
    predictor = HorseRacingPredictor(hipodrom)
    success = predictor.run_full_pipeline()
    
    if success:
        print(f"\n🎉 {hipodrom} tahminleri hazır!")
        print(f"📄 output/{hipodrom}_predictions_top3.csv")
        print(f"📄 output/{hipodrom}_predictions_all.csv")
    else:
        print(f"\n❌ {hipodrom} için tahmin yapılamadı!")

if __name__ == "__main__":
    main()