#!/usr/bin/env python3
"""
At Yarışı Tahmin Sistemi - Anlaşılır Format
"""

import pandas as pd
import sys
from datetime import datetime

def format_predictions(hipodrom_key):
    """Tahminleri anlaşılır formatta yazdır"""
    
    # Dosya yolları
    all_file = f"output/{hipodrom_key}_predictions_all.csv"
    top3_file = f"output/{hipodrom_key}_predictions_top3.csv"
    
    try:
        # Veriyi yükle
        df_all = pd.read_csv(all_file)
        df_top3 = pd.read_csv(top3_file)
        
        print(f"🏇 {hipodrom_key} BUGÜNÜN AT YARIŞI TAHMİNLERİ")
        print("=" * 60)
        print(f"📅 Tarih: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        print(f"📊 Bugünün Koşu Sayısı: {df_all['yaris_kosu_key'].nunique()}")
        print(f"📊 Bugünün At Sayısı: {len(df_all)}")
        print("=" * 60)
        
        # Saat sırasına göre grupla
        races_by_time = {}
        
        for _, row in df_all.iterrows():
            time_key = row['saat'] if 'saat' in row else 'Bilinmiyor'
            if time_key not in races_by_time:
                races_by_time[time_key] = []
            races_by_time[time_key].append(row)
        
        # Saatlere göre sırala ve yazdır
        race_count = 0
        for time in sorted(races_by_time.keys()):
            race_count += 1
            horses = races_by_time[time]
            
            # Win probability'ye göre sırala
            horses.sort(key=lambda x: x['win_proba'], reverse=True)
            
            print(f"\n🏁 KOŞU {race_count} - Saat {time}")
            print("-" * 50)
            
            for i, horse in enumerate(horses, 1):
                prob = horse['win_proba']
                at_adi = horse['at_adi']
                sonuc = horse.get('sonuc', 'N/A')
                
                # Sonuc durumu
                if sonuc == 1:
                    status = "🏆 KAZANDI"
                elif sonuc != 'N/A':
                    status = f"📊 {int(sonuc)}. sıra"
                else:
                    status = "⏳ Tahmin"
                
                # Probability'ye göre renk/emoji
                if prob > 0.7:
                    prob_emoji = "🔥"
                elif prob > 0.5:
                    prob_emoji = "⭐"
                elif prob > 0.3:
                    prob_emoji = "📈"
                else:
                    prob_emoji = "📉"
                
                print(f"{i:2d}. {prob_emoji} {at_adi:25} - {prob*100:5.1f}% - {status}")
            
            # En yüksek 3'ü vurgula
            print(f"\n🎯 En Yüksek 3 Tahmin:")
            for i, horse in enumerate(horses[:3], 1):
                prob = horse['win_proba']
                at_adi = horse['at_adi']
                print(f"   {i}. {at_adi:25} - {prob*100:5.1f}%")
        
        # Özet istatistikler
        print(f"\n📊 ÖZET İSTATİSTİKLER")
        print("-" * 30)
        
        # En yüksek probability'li atlar
        top_horses = df_all.nlargest(5, 'win_proba')
        print(f"🔥 En Yüksek 5 Kazanma Olasılığı:")
        for i, (_, horse) in enumerate(top_horses.iterrows(), 1):
            print(f"   {i}. {horse['at_adi']:25} - {horse['win_proba']*100:5.1f}%")
        
        # Probability dağılımı
        print(f"\n📈 Probability Dağılımı:")
        print(f"   En yüksek: {df_all['win_proba'].max()*100:.1f}%")
        print(f"   En düşük:  {df_all['win_proba'].min()*100:.1f}%")
        print(f"   Ortalama:  {df_all['win_proba'].mean()*100:.1f}%")
        
        # Kazananlar (eğer sonuc varsa)
        if 'sonuc' in df_all.columns:
            winners = df_all[df_all['sonuc'] == 1]
            if len(winners) > 0:
                print(f"\n🏆 Gerçek Kazananlar:")
                for _, winner in winners.iterrows():
                    prob = winner['win_proba']
                    print(f"   {winner['at_adi']:25} - {prob*100:5.1f}%")
        
        print(f"\n" + "=" * 60)
        print(f"✅ {hipodrom_key} tahminleri hazır!")
        
    except FileNotFoundError:
        print(f"❌ {hipodrom_key} tahmin dosyaları bulunamadı!")
        print(f"Önce tahmin yapın: python3 predict.py {hipodrom_key}")
    except Exception as e:
        print(f"❌ Hata: {e}")

def main():
    if len(sys.argv) != 2:
        print("Kullanım: python3 format_predictions.py [HİPODROM_ADI]")
        print("Örnek: python3 format_predictions.py ISTANBUL")
        return
    
    hipodrom = sys.argv[1].upper()
    format_predictions(hipodrom)

if __name__ == "__main__":
    main()
