#!/usr/bin/env python3
"""
At Yarışı Tahmin Web Uygulaması
Modern, mobil uyumlu web arayüzü
"""

import os
import re
import json
import threading
import subprocess
import pandas as pd
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from pathlib import Path
from datetime import datetime
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
CORS(app)  # Tüm origin'lerden isteklere izin ver

# Scheduler
scheduler = BackgroundScheduler()
scheduler.start()

# Son güncelleme zamanı (site yenileme için)
last_update_time = None

# Cache mekanizması (API yanıtlarını hızlı tutmak için)
_tahmin_cache = {}  # {hipodrom: {'data': {...}, 'timestamp': datetime, 'file_mtime': float}}
_ganyan_cache = {}  # {hipodrom: {'data': {...}, 'timestamp': datetime}}
CACHE_TTL = 60  # Cache süresi (saniye) - 1 dakika

# Hipodrom listesi
HIPODROMLAR = [
    'ANKARA', 'ISTANBUL', 'IZMIR', 'BURSA', 'KOCAELI', 
    'ADANA', 'SANLIURFA', 'DBAKIR', 'BELMONTBIG', 'SELANGOR', 'ELAZIG'
]

def parse_tahmin_dosyasi(file_path):
    """
    TXT formatındaki tahmin dosyasını parse eder
    """
    if not os.path.exists(file_path):
        return None
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    result = {
        'hipodrom': '',
        'tarih': '',
        'toplam_kosu': 0,
        'toplam_at': 0,
        'kosular': []
    }
    
    # Hipodrom adını bul
    hipodrom_match = re.search(r'🏇\s+(\w+)\s+AT YARIŞI TAHMİNLERİ', content)
    if hipodrom_match:
        result['hipodrom'] = hipodrom_match.group(1)
    
    # Tarih bilgisini bul
    tarih_match = re.search(r'📅\s+Tarih:\s+([^\n]+)', content)
    if tarih_match:
        result['tarih'] = tarih_match.group(1).strip()
    
    # Toplam koşu ve at sayısını bul
    kosu_match = re.search(r'📊\s+Toplam Koşu:\s+(\d+)', content)
    if kosu_match:
        result['toplam_kosu'] = int(kosu_match.group(1))
    
    at_match = re.search(r'📊\s+Toplam At:\s+(\d+)', content)
    if at_match:
        result['toplam_at'] = int(at_match.group(1))
    
    # Koşuları parse et
    kosu_pattern = r'🏁\s+KOŞU\s+(\d+)\s+-\s+Saat\s+(\d{2}:\d{2})\s+-\s+([^\n]+)'
    kosu_matches = re.finditer(kosu_pattern, content)
    
    for kosu_match in kosu_matches:
        kosu_no = int(kosu_match.group(1))
        saat = kosu_match.group(2)
        sinif = kosu_match.group(3).strip()
        
        # Bu koşunun başlangıç ve bitiş pozisyonunu bul
        start_pos = kosu_match.end()
        next_kosu = re.search(r'🏁\s+KOŞU\s+\d+', content[start_pos:])
        end_pos = start_pos + next_kosu.start() if next_kosu else len(content)
        
        kosu_content = content[start_pos:end_pos]
        
        # Atları parse et
        atlar = []
        at_pattern = r'(\d+)\.\s+([📈📉🔥])\s+([A-Za-zÇĞİÖŞÜçğıöşü\s]+?)\s+-\s+(\d+\.\d+)%'
        at_matches = re.finditer(at_pattern, kosu_content)
        
        for at_match in at_matches:
            sira = int(at_match.group(1))
            icon = at_match.group(2)
            at_adi = at_match.group(3).strip()
            olasilik = float(at_match.group(4))
            
            # Bu atın detaylarını bul (aynı satırda - pattern'den sonraki kısım)
            at_match_end = at_match.end()
            at_line_end = kosu_content.find('\n', at_match_end)
            if at_line_end == -1:
                at_line_end = len(kosu_content)
            at_line = kosu_content[at_match_end:at_line_end].strip()
            
            # Detayları parse et
            detaylar = {}
            
            # Jokey-At kazanma
            jokey_at_kazanma = re.search(r'🏆\s+Jokey-At:\s+(\d+)x\s+kazandı', at_line)
            if jokey_at_kazanma:
                detaylar['jokey_at_kazanma'] = int(jokey_at_kazanma.group(1))
            
            # Jokey-At tabela
            jokey_at_tabela = re.search(r'📊\s+Jokey-At:\s+(\d+)x\s+tabela', at_line)
            if jokey_at_tabela:
                detaylar['jokey_at_tabela'] = int(jokey_at_tabela.group(1))
            
            # Mesafe kazanma
            mesafe_kazanma = re.search(r'📏\s+Mesafe:\s+(\d+)x\s+kazandı', at_line)
            if mesafe_kazanma:
                detaylar['mesafe_kazanma'] = int(mesafe_kazanma.group(1))
            
            # Hipodrom kazanma
            hipodrom_kazanma = re.search(r'🏟️\s+(\w+):\s+(\d+)x\s+kazandı', at_line)
            if hipodrom_kazanma:
                detaylar['hipodrom'] = hipodrom_kazanma.group(1)
                detaylar['hipodrom_kazanma'] = int(hipodrom_kazanma.group(2))
            
            # Badge bilgileri (G1, G2, G3, KV)
            badge_pattern = r'🏅\s+([^\n]+?)(?:\s+⚔️|$)'
            badge_match = re.search(badge_pattern, at_line)
            if badge_match:
                badge_text = badge_match.group(1).strip()
                detaylar['badge'] = badge_text
            
            # Geçti bilgileri
            gecti_match = re.search(r'⚔️\s+Geçti:\s+([^\n]+)', at_line)
            if gecti_match:
                gecti_text = gecti_match.group(1).strip()
                detaylar['gecti'] = [x.strip() for x in gecti_text.split(',')]
            
            atlar.append({
                'sira': sira,
                'icon': icon,
                'at_adi': at_adi,
                'olasilik': olasilik,
                'detaylar': detaylar
            })
        
        # En yüksek 3 tahmin
        top3_pattern = r'🎯\s+En Yüksek 3 Tahmin:(.*?)(?=🏁|🎯|$)'
        top3_match = re.search(top3_pattern, kosu_content, re.DOTALL)
        top3 = []
        if top3_match:
            top3_content = top3_match.group(1)
            top3_pattern_inner = r'(\d+)\.\s+([A-Za-zÇĞİÖŞÜçğıöşü\s]+?)\s+-\s+(\d+\.\d+)%'
            top3_matches = re.finditer(top3_pattern_inner, top3_content)
            for tm in top3_matches:
                top3.append({
                    'sira': int(tm.group(1)),
                    'at_adi': tm.group(2).strip(),
                    'olasilik': float(tm.group(3))
                })
        
        result['kosular'].append({
            'kosu_no': kosu_no,
            'saat': saat,
            'sinif': sinif,
            'atlar': atlar,
            'top3': top3
        })
    
    return result

@app.route('/')
def index():
    """Ana sayfa"""
    return render_template('index.html', hipodromlar=HIPODROMLAR)

def get_race_winner_helper(hipodrom, kosu_no, kosu_saat=None):
    """CSV'den koşunun kazananını bul (helper fonksiyon)"""
    csv_path = f'data/{hipodrom}_races.csv'
    if not os.path.exists(csv_path):
        return None
    
    try:
        df = pd.read_csv(csv_path, encoding='utf-8')
        # Türkiye timezone'una göre tarih al
        turkey_tz = pytz.timezone('Europe/Istanbul')
        today = datetime.now(turkey_tz).strftime('%d/%m/%Y')
        today_df = df[df['tarih'] == today]
        
        if len(today_df) == 0:
            return None
        
        # Koşu numarasına göre filtrele
        kosu_df = None
        
        # Önce saat ile eşleştir (en güvenilir yöntem)
        if kosu_saat and 'saat' in today_df.columns:
            try:
                kosu_saat_normalized = kosu_saat.strip()
                kosu_df = today_df[today_df['saat'].astype(str).str.strip() == kosu_saat_normalized]
            except:
                pass
        
        # Bulamazsa no sütunu ile dene
        if (kosu_df is None or len(kosu_df) == 0) and 'no' in today_df.columns:
            try:
                kosu_df = today_df[today_df['no'].astype(str).str.strip() == str(kosu_no)]
            except:
                pass
        
        if kosu_df is None or len(kosu_df) == 0:
            return None
        
        # Sonuç sütununu kontrol et (derece_sonuc veya sonuc)
        for col in ['derece_sonuc', 'sonuc', 'kazanan']:
            if col in kosu_df.columns:
                winner_row = kosu_df[kosu_df[col].notna() & (kosu_df[col].astype(str).str.strip() != '')]
                if len(winner_row) > 0:
                    winner = winner_row.iloc[0][col]
                    if pd.notna(winner) and str(winner).strip():
                        return str(winner).strip()
        
        return None
    except Exception as e:
        print(f"⚠️ Kazanan bulunurken hata ({hipodrom} Koşu {kosu_no}): {e}")
        return None

@app.route('/api/update-time')
def api_update_time():
    """Son güncelleme zamanını döndür (site yenileme kontrolü için)"""
    global last_update_time
    return jsonify({
        'last_update_time': last_update_time,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/hipodromlar')
def api_hipodromlar():
    """Mevcut hipodromları döndür - Yakında yarış olanları başa getir"""
    hipodrom_list = []
    # Türkiye timezone'una göre tarih ve saat al
    turkey_tz = pytz.timezone('Europe/Istanbul')
    today = datetime.now(turkey_tz).strftime('%d/%m/%Y')
    current_time = datetime.now(turkey_tz)
    current_hour = current_time.hour
    current_minute = current_time.minute
    
    def is_race_soon(saat_str):
        """Koşu yakında mı? (1 saat içinde)"""
        try:
            race_hour, race_minute = map(int, saat_str.split(':'))
            race_total_minutes = race_hour * 60 + race_minute
            current_total_minutes = current_hour * 60 + current_minute
            time_diff = race_total_minutes - current_total_minutes
            return 0 <= time_diff <= 60
        except:
            return False
    
    for hipodrom in HIPODROMLAR:
        file_path = f'output/{hipodrom}_tahminler.txt'
        csv_path = f'data/{hipodrom}_races.csv'
        
        has_race_today = False
        has_race_soon = False
        earliest_race_time = None  # En erken koşu saati (dakika cinsinden)
        
        # Bugün yarış var mı ve yakında yarış var mı kontrol et
        if os.path.exists(csv_path):
            try:
                df = pd.read_csv(csv_path, encoding='utf-8')
                if len(df) > 0 and 'tarih' in df.columns:
                    today_races = df[df['tarih'] == today]
                    if len(today_races) > 0:
                        has_race_today = True
                        # Yakında yarış var mı? (1 saat içinde) ve en erken koşu saatini bul
                        if 'saat' in today_races.columns:
                            earliest_minutes = None
                            for _, race in today_races.iterrows():
                                if pd.notna(race.get('saat')):
                                    try:
                                        race_hour, race_minute = map(int, str(race['saat']).split(':'))
                                        race_total_minutes = race_hour * 60 + race_minute
                                        if earliest_minutes is None or race_total_minutes < earliest_minutes:
                                            earliest_minutes = race_total_minutes
                                        if is_race_soon(str(race['saat'])):
                                            has_race_soon = True
                                    except:
                                        pass
                            if earliest_minutes is not None:
                                earliest_race_time = earliest_minutes
            except:
                pass
        
        if os.path.exists(file_path):
            # Dosya tarihini al
            file_time = os.path.getmtime(file_path)
            file_date = datetime.fromtimestamp(file_time).strftime('%d/%m/%Y %H:%M')
            
            hipodrom_list.append({
                'adi': hipodrom,
                'var': True,
                'tarih': file_date,
                'has_race_today': has_race_today,
                'has_race_soon': has_race_soon,
                'earliest_race_time': earliest_race_time
            })
        else:
            hipodrom_list.append({
                'adi': hipodrom,
                'var': False,
                'tarih': None,
                'has_race_today': has_race_today,
                'has_race_soon': has_race_soon,
                'earliest_race_time': earliest_race_time
            })
    
    # Sırala: Önce yakında yarış olanlar, sonra en erken koşu saatine göre, sonra bugün yarış olanlar, sonra diğerleri
    hipodrom_list.sort(key=lambda x: (
        not x.get('has_race_soon', False), 
        x.get('earliest_race_time') if x.get('earliest_race_time') is not None else 9999,
        not x.get('has_race_today', False), 
        x['adi']
    ))
    
    # Bugün koşu olan tüm şehirleri dinamik olarak bul
    # CSV dosyalarından bugün koşu olan şehirleri tespit et
    today_allowed = []
    data_dir = Path('data')
    if data_dir.exists():
        for csv_file in data_dir.glob('*_races.csv'):
            try:
                city_name = csv_file.stem.replace('_races', '').upper()
                df = pd.read_csv(csv_file, encoding='utf-8')
                if 'tarih' in df.columns:
                    today_races = df[df['tarih'] == today]
                    if len(today_races) > 0:
                        today_allowed.append(city_name)
            except:
                continue
    
    # Eğer hiç şehir bulunamazsa, varsayılan listeyi kullan
    if not today_allowed:
        today_allowed = ['ANKARA', 'IZMIR', 'DBAKIR', 'ISTANBUL', 'ADANA', 'KOCAELI']
    
    # Sadece bugün koşu olan ve tahmin dosyası olan şehirleri göster
    hipodrom_list = [h for h in hipodrom_list if h['adi'] in today_allowed and h.get('var', False) and h.get('has_race_today', False)]
    
    return jsonify(hipodrom_list)

def get_ganyan_agf_data(hipodrom):
    """CSV'den bugünün ganyan ve AGF verilerini çek"""
    csv_path = f'data/{hipodrom}_races.csv'
    if not os.path.exists(csv_path):
        return {}
    
    try:
        df = pd.read_csv(csv_path, encoding='utf-8')
        # Bugünün tarihini bul (en son tarih)
        if 'tarih' not in df.columns:
            return {}
        
        # Bugünün verilerini filtrele
        # Türkiye timezone'una göre tarih al
        turkey_tz = pytz.timezone('Europe/Istanbul')
        today = datetime.now(turkey_tz).strftime('%d/%m/%Y')
        today_df = df[df['tarih'] == today].copy()
        
        if today_df.empty:
            return {}
        
        # Ganyan ve AGF verilerini organize et
        result = {}
        
        for _, row in today_df.iterrows():
            # Koşu key'ini bul - önce kosu_kodu, sonra yaris_kosu_key, son olarak kosu_no kullan
            kosu_key = row.get('kosu_kodu', '')
            if not kosu_key:
                kosu_key = row.get('yaris_kosu_key', '')
            if not kosu_key:
                # kosu_no varsa onu kullan
                kosu_no = row.get('kosu_no', '')
                if kosu_no and pd.notna(kosu_no):
                    kosu_key = f'kosu_{kosu_no}'
            
            at_adi = str(row.get('at_adi', '')).strip()
            
            if not kosu_key or not at_adi:
                continue
            
            if kosu_key not in result:
                result[kosu_key] = {}
            
            ganyan = row.get('ganyan', '')
            agf1 = row.get('agf1', '')
            agf2 = row.get('agf2', '')
            
            # Ganyan'ı float'a çevir (virgülü noktaya çevir)
            ganyan_val = None
            if pd.notna(ganyan) and str(ganyan).strip():
                try:
                    ganyan_str = str(ganyan).replace(',', '.')
                    ganyan_val = float(ganyan_str)
                except:
                    pass
    
            result[kosu_key][at_adi] = {
                'ganyan': ganyan_val,
                'agf1': float(agf1) if pd.notna(agf1) and str(agf1).strip() and str(agf1) != '<nil>' else None,
                'agf2': float(agf2) if pd.notna(agf2) and str(agf2).strip() and str(agf2) != '<nil>' else None
            }
        
        return result
    except Exception as e:
        print(f"Ganyan/AGF verisi okuma hatası ({hipodrom}): {e}")
        return {}

def calculate_value_score(olasilik, ganyan):
    """Value betting skorunu hesapla: (olasılık * oran) - 1"""
    if not ganyan or ganyan <= 0:
        return None
    
    try:
        # Ganyan string ise float'a çevir
        if isinstance(ganyan, str):
            ganyan = float(ganyan.replace(',', '.'))
        
        # Olasılığı 0-1 arasına çevir (% -> decimal)
        prob = float(olasilik) / 100.0
        
        # Value = (olasılık * oran) - 1
        # Pozitif değer = iyi fırsat
        value = (prob * float(ganyan)) - 1
        
        # Yüzde olarak döndür (ama çok büyük değerleri sınırla)
        value_percent = round(value * 100, 2)
        
        # Çok büyük değerleri sınırla (muhtemelen hatalı veri)
        if value_percent > 1000:
            return None
        
        return value_percent
    except (ValueError, TypeError) as e:
        print(f"Value hesaplama hatası: {e}, olasılık={olasilik}, ganyan={ganyan}")
        return None

def calculate_profit_score(olasilik, ganyan):
    """Kazanç skorunu hesapla: Beklenen getiri ve risk faktörü"""
    if not ganyan or ganyan <= 0:
        return None
    
    try:
        # Ganyan string ise float'a çevir
        if isinstance(ganyan, str):
            ganyan = float(ganyan.replace(',', '.'))
        
        # Olasılığı 0-1 arasına çevir (% -> decimal)
        prob = float(olasilik) / 100.0
        
        # Beklenen getiri: olasılık * ganyan
        expected_return = prob * float(ganyan)
        
        # Risk düzeltmesi: Olasılık düşükse risk yüksek
        # Yüksek olasılık + yüksek ganyan = ideal
        # Risk faktörü: olasılık ne kadar yüksekse o kadar güvenli
        risk_factor = prob  # 0-1 arası, yüksek olasılık = düşük risk
        
        # Kazanç skoru: Beklenen getiri * risk faktörü
        # Bu skor hem getiriyi hem güvenliği gösterir
        profit_score = expected_return * (0.5 + 0.5 * risk_factor)  # 0.5-1.0 arası risk faktörü
        
        # Yüzde olarak normalize et
        profit_score_percent = round((profit_score - 1) * 100, 2)
        
        return profit_score_percent
    except (ValueError, TypeError) as e:
        print(f"Kazanç skoru hesaplama hatası: {e}, olasılık={olasilik}, ganyan={ganyan}")
        return None
    
def calculate_profit_from_score_and_ganyan(combined_score, ganyan):
    """Skor ve Ganyan'ı kullanarak kazanç skorunu hesapla - Dümdüz çarpım"""
    if not ganyan or ganyan <= 0 or combined_score is None:
        return None
    
    try:
        # Ganyan string ise float'a çevir
        if isinstance(ganyan, str):
            ganyan = float(ganyan.replace(',', '.'))
        
        # Kazanç skoru: Skor * Ganyan (dümdüz çarpım, yüzde değil)
        # Skor zaten 0-1 arası, direkt çarp
        profit_score = combined_score * float(ganyan)
        
        return round(profit_score, 2)
    except (ValueError, TypeError) as e:
        print(f"Skor ve Ganyan'dan kazanç skoru hesaplama hatası: {e}, skor={combined_score}, ganyan={ganyan}")
        return None
    
    
@app.route('/api/tahminler/<hipodrom>')
def api_tahminler(hipodrom):
    """Belirli bir hipodrom için tahminleri döndür (cache'li ve asenkron)"""
    global last_update_time, _tahmin_cache
    try:
        hipodrom = hipodrom.upper()
        file_path = f'output/{hipodrom}_tahminler.txt'
        
        # Cache kontrolü - eğer cache'de varsa ve dosya değişmemişse direkt döndür
        if hipodrom in _tahmin_cache:
            cache_entry = _tahmin_cache[hipodrom]
            cache_time = cache_entry['timestamp']
            cache_file_mtime = cache_entry['file_mtime']
            
            # Dosya hala var mı ve değişmiş mi kontrol et
            if os.path.exists(file_path):
                current_file_mtime = os.path.getmtime(file_path)
                # Cache süresi dolmamış ve dosya değişmemişse cache'den döndür
                time_diff = (datetime.now() - cache_time).total_seconds()
                if time_diff < CACHE_TTL and current_file_mtime == cache_file_mtime:
                    print(f"⚡ {hipodrom} için cache'den döndürülüyor (hızlı yanıt)")
                    return jsonify(cache_entry['data'])
        
        if not os.path.exists(file_path):
            print(f"❌ {hipodrom} için tahmin dosyası bulunamadı: {file_path}")
            # Output klasörünü kontrol et
            output_dir = 'output'
            if os.path.exists(output_dir):
                files = os.listdir(output_dir)
                print(f"📁 Output klasöründeki dosyalar: {files}")
            else:
                print(f"❌ Output klasörü mevcut değil: {output_dir}")
                # Output klasörünü oluştur
                os.makedirs(output_dir, exist_ok=True)
                print(f"📁 Output klasörü oluşturuldu: {output_dir}")
            
            # Tahmin dosyası yoksa, sadece bilgilendirme mesajı döndür
            # Tahminler sadece günde bir kere (07:00) otomatik olarak oluşturulur
            return jsonify({
                'error': f'{hipodrom} için tahmin dosyası bulunamadı',
                'message': f'{hipodrom} için tahminler henüz hazır değil. Tahminler her gün sabah 07:00\'de otomatik olarak oluşturulur. Lütfen daha sonra tekrar deneyin.',
                'hipodrom': hipodrom,
                'file_path': file_path,
                'updating': False,
                'next_update': '07:00 (her gün)'
            }), 404
        
        # Tahmin dosyasının son güncelleme zamanını kontrol et ve last_update_time'ı güncelle
        file_mtime = os.path.getmtime(file_path)
        file_time = datetime.fromtimestamp(file_mtime).isoformat()
        
        # Eğer dosya zamanı last_update_time'dan daha yeni ise güncelle
        if last_update_time is None or file_time > last_update_time:
            last_update_time = file_time
            print(f"🔄 Tahmin dosyası güncellendi: {hipodrom} - {file_time}")
        
        # Parse işlemini background thread'de yap (asenkron)
        # Ama önce cache'de varsa onu kullan
        data = None
        if hipodrom in _tahmin_cache:
            cache_entry = _tahmin_cache[hipodrom]
            if os.path.exists(file_path) and os.path.getmtime(file_path) == cache_entry['file_mtime']:
                # Cache'den parse edilmiş data'yı al
                data = cache_entry.get('parsed_data')
        
        # Cache'de yoksa parse et (bu hızlı olmalı)
        if data is None:
            data = parse_tahmin_dosyasi(file_path)
        if not data:
            print(f"❌ {hipodrom} için tahmin dosyası parse edilemedi")
            return jsonify({'error': 'Tahmin dosyası parse edilemedi'}), 500
        
        # Ganyan ve AGF verilerini ekle (cache'li)
        global _ganyan_cache
        if hipodrom in _ganyan_cache:
            cache_entry = _ganyan_cache[hipodrom]
            time_diff = (datetime.now() - cache_entry['timestamp']).total_seconds()
            if time_diff < CACHE_TTL:
                ganyan_agf_data = cache_entry['data']
            else:
                ganyan_agf_data = get_ganyan_agf_data(hipodrom)
                _ganyan_cache[hipodrom] = {
                    'data': ganyan_agf_data,
                    'timestamp': datetime.now()
                }
        else:
            ganyan_agf_data = get_ganyan_agf_data(hipodrom)
            _ganyan_cache[hipodrom] = {
                'data': ganyan_agf_data,
                'timestamp': datetime.now()
            }
        
        # En mantıklı oyunlar listesi - AGF1 ve Yapay Zeka skoruna göre
        all_candidates = []
        
        # Şu anki saat (saat:dakika formatında)
        # Türkiye timezone'una göre saat al (GMT+3)
        turkey_tz = pytz.timezone('Europe/Istanbul')
        current_time = datetime.now(turkey_tz)
        current_hour = current_time.hour
        current_minute = current_time.minute
        
        def is_race_soon(kosu_saat):
            """Koşu yakında mı? (1 saat içinde)"""
            try:
                # Saat formatını parse et (örn: "17:30")
                race_hour, race_minute = map(int, kosu_saat.split(':'))
                race_total_minutes = race_hour * 60 + race_minute
                current_total_minutes = current_hour * 60 + current_minute
                
                # 1 saat içindeyse True
                time_diff = race_total_minutes - current_total_minutes
                return 0 <= time_diff <= 60
            except:
                return False
        
        def is_race_finished(kosu_saat):
            """Koşu bitmiş mi? (saati geçmiş mi?)"""
            try:
                # Saat formatını parse et (örn: "17:30")
                race_hour, race_minute = map(int, kosu_saat.split(':'))
                race_total_minutes = race_hour * 60 + race_minute
                current_total_minutes = current_hour * 60 + current_minute
                
                # Saati geçmişse True (en az 10 dakika geçmiş olmalı)
                time_diff = current_total_minutes - race_total_minutes
                return time_diff >= 10
            except:
                return False
        
        def get_race_winner(hipodrom, kosu_no, kosu_saat=None):
            """CSV'den koşunun kazananını bul (sonuc sütununu kullan)"""
            csv_path = f'data/{hipodrom}_races.csv'
            if not os.path.exists(csv_path):
                return None
            
            try:
                df = pd.read_csv(csv_path, encoding='utf-8')
                # Türkiye timezone'una göre tarih al
                turkey_tz = pytz.timezone('Europe/Istanbul')
                today = datetime.now(turkey_tz).strftime('%d/%m/%Y')
                today_df = df[df['tarih'] == today]
                
                if len(today_df) == 0:
                    return None
                
                # Koşu numarasına göre filtrele
                kosu_df = None
                
                # Önce saat ile eşleştir (en güvenilir yöntem)
                if kosu_saat and 'saat' in today_df.columns:
                    try:
                        # Saat formatını normalize et
                        kosu_saat_normalized = kosu_saat.strip()
                        kosu_df = today_df[today_df['saat'].astype(str).str.strip() == kosu_saat_normalized]
                        print(f"🔍 Saat ile arama ({kosu_saat_normalized}): {len(kosu_df)} kayıt bulundu")
                    except Exception as e:
                        print(f"⚠️ Saat ile arama hatası: {e}")
                        pass
                
                # Bulamazsa no sütunu ile dene (at numarası değil, koşu numarası olabilir)
                if (kosu_df is None or len(kosu_df) == 0) and 'no' in today_df.columns:
                    try:
                        kosu_df = today_df[today_df['no'] == int(kosu_no)]
                        print(f"🔍 no ile arama (koşu {kosu_no}): {len(kosu_df)} kayıt bulundu")
                    except:
                        pass
                
                # Bulamazsa kosu_kodu ile dene
                if (kosu_df is None or len(kosu_df) == 0) and 'kosu_kodu' in today_df.columns:
                    try:
                        kosu_df = today_df[today_df['kosu_kodu'] == int(kosu_no)]
                        print(f"🔍 kosu_kodu ile arama (koşu {kosu_no}): {len(kosu_df)} kayıt bulundu")
                    except:
                        pass
                
                # Bulamazsa yaris_kosu_key ile dene (hash değeri olabilir)
                if (kosu_df is None or len(kosu_df) == 0) and 'yaris_kosu_key' in today_df.columns:
                    kosu_df = today_df[today_df['yaris_kosu_key'] == f'kosu_{kosu_no}']
                
                # Bulamazsa kosu_no sütunu ile dene
                if (kosu_df is None or len(kosu_df) == 0) and 'kosu_no' in today_df.columns:
                    try:
                        kosu_df = today_df[today_df['kosu_no'] == int(kosu_no)]
                    except:
                        pass
                
                # Bulamazsa kosu sütunu ile dene
                if (kosu_df is None or len(kosu_df) == 0) and 'kosu' in today_df.columns:
                    try:
                        kosu_df = today_df[today_df['kosu'] == int(kosu_no)]
                    except:
                        pass
                
                if kosu_df is None or len(kosu_df) == 0:
                    return None
                
                # Önce sonuc=1 olanı bul (kazanan)
                if 'sonuc' in kosu_df.columns:
                    try:
                        # Sonuc sütununda 1 olan atı bul (string veya int)
                        winner_row = kosu_df[(kosu_df['sonuc'] == 1) | (kosu_df['sonuc'] == '1') | (kosu_df['sonuc'] == '1.0') | (kosu_df['sonuc'].astype(str).str.strip() == '1')]
                        if len(winner_row) > 0:
                            winner_name = winner_row.iloc[0].get('at_adi', '')
                            if pd.notna(winner_name) and str(winner_name).strip() and str(winner_name).strip() != '<nil>':
                                winner = str(winner_name).strip()
                                print(f"✅ Kazanan bulundu ({hipodrom} Koşu {kosu_no}): {winner}")
                                return winner
                    except Exception as e:
                        print(f"Sonuc=1 kontrol hatası ({hipodrom} Koşu {kosu_no}): {e}")
                        pass
                
                # Sonuc=1 yoksa derece=1 olanı bul
                if 'derece' in kosu_df.columns:
                    try:
                        winner_row = kosu_df[(kosu_df['derece'] == 1) | (kosu_df['derece'] == '1') | (kosu_df['derece'] == '1.0') | (kosu_df['derece'].astype(str).str.strip() == '1')]
                        if len(winner_row) > 0:
                            winner_name = winner_row.iloc[0].get('at_adi', '')
                            if pd.notna(winner_name) and str(winner_name).strip():
                                winner = str(winner_name).strip()
                                print(f"✅ Kazanan bulundu (derece=1) ({hipodrom} Koşu {kosu_no}): {winner}")
                                return winner
                    except Exception as e:
                        print(f"Derece=1 kontrol hatası ({hipodrom} Koşu {kosu_no}): {e}")
                        pass
                
                print(f"⚠️ Kazanan bulunamadı ({hipodrom} Koşu {kosu_no})")
                return None
            except Exception as e:
                print(f"❌ Kazanan bulma hatası ({hipodrom} Koşu {kosu_no}): {e}")
                import traceback
                print(traceback.format_exc())
                return None
        
        # Her koşu için AGF1 ve yapay zeka skorunu birleştir
        for kosu in data['kosular']:
            kosu_soon = is_race_soon(kosu['saat'])
            kosu_finished = is_race_finished(kosu['saat'])
            race_winner = get_race_winner(hipodrom, kosu['kosu_no'], kosu['saat']) if kosu_finished else None
            
            # CSV'den koşu mesafesini al
            kosu_mesafe = None
            csv_path = f'data/{hipodrom}_races.csv'
            if os.path.exists(csv_path):
                try:
                    df = pd.read_csv(csv_path, encoding='utf-8')
                    # Türkiye timezone'una göre tarih al
                    turkey_tz = pytz.timezone('Europe/Istanbul')
                    today = datetime.now(turkey_tz).strftime('%d/%m/%Y')
                    today_df = df[df['tarih'] == today]
                    
                    if len(today_df) > 0:
                        # Koşu numarasına göre filtrele - saat ile eşleştirme
                        kosu_df = None
                        if kosu.get('saat') and 'saat' in today_df.columns:
                            kosu_df = today_df[today_df['saat'].astype(str).str.strip() == kosu['saat'].strip()]
                        
                        if kosu_df is None or len(kosu_df) == 0:
                            # Yaris_kosu_key ile dene
                            kosu_df = today_df[today_df['yaris_kosu_key'] == f'kosu_{kosu["kosu_no"]}']
                        
                        if kosu_df is not None and len(kosu_df) > 0:
                            # İlk satırdan mesafe bilgisini al
                            row = kosu_df.iloc[0]
                            mesafe_val = row.get('mesafe', None)
                            if pd.notna(mesafe_val) and str(mesafe_val).strip() and str(mesafe_val) != '<nil>':
                                try:
                                    # Mesafe değerini sayıya çevir (string olabilir, "1600" gibi)
                                    mesafe_str = str(mesafe_val).strip()
                                    # Sadece sayıları al
                                    mesafe_num = ''.join(filter(str.isdigit, mesafe_str))
                                    if mesafe_num:
                                        kosu_mesafe = int(mesafe_num)
                                except:
                                    pass
                except Exception as e:
                    pass
            
            # Önce koşudaki tüm atların AGF1 ve olasılık bilgilerini topla
            kosu_atlar_info = []
            kosu_pist_tur = None  # Koşu seviyesinde pist türü
            kosu_cins_detay = None  # Koşu seviyesinde cins detay
            
            for at in kosu['atlar']:
                at_adi = at['at_adi']
                olasilik = at['olasilik']
                
                # Ganyan ve AGF verilerini bul
                ganyan = None
                agf1 = None
                agf2 = None
                agf1_sira = None
                
                # En iyi derece bilgilerini varsayılan değerlerle başlat
                en_iyi_derece = None
                en_iyi_derece_farkli_hipodrom = False
                
                # Ganyan verisini bul - tüm koşularda ara
                for kosu_key, atlar in ganyan_agf_data.items():
                    for at_name_in_data, at_data in atlar.items():
                        if at_name_in_data.upper().strip() == at_adi.upper().strip():
                            ganyan = at_data['ganyan']
                            agf1 = at_data['agf1']
                            agf2 = at_data['agf2']
                            break
                    if ganyan is not None:
                        break
                
                # CSV'den AGF1_sira, AGF2_sira, pist türü, jokey, at no ve derece/sonuç bilgisini al
                pist_tur = None
                jokey_adi = None
                at_no = None
                agf2_sira = None
                derece_sonuc = None  # Bitmiş koşularda atın kaçıncı olduğu
                csv_path = f'data/{hipodrom}_races.csv'
                if os.path.exists(csv_path):
                    try:
                        df = pd.read_csv(csv_path, encoding='utf-8')
                        # Türkiye timezone'una göre tarih al
                        turkey_tz = pytz.timezone('Europe/Istanbul')
                        today = datetime.now(turkey_tz).strftime('%d/%m/%Y')
                        today_df = df[df['tarih'] == today]
                        
                        if len(today_df) > 0:
                            # Koşu numarasına göre filtrele - saat ile eşleştirme
                            kosu_df = None
                            if kosu.get('saat') and 'saat' in today_df.columns:
                                kosu_df = today_df[today_df['saat'].astype(str).str.strip() == kosu['saat'].strip()]
                            
                            if kosu_df is None or len(kosu_df) == 0:
                                # Yaris_kosu_key ile dene
                                kosu_df = today_df[today_df['yaris_kosu_key'] == f'kosu_{kosu["kosu_no"]}']
                            
                            if kosu_df is None or len(kosu_df) == 0:
                                # Yaris_kosu_key yoksa, sadece at adına göre ara
                                kosu_df = today_df
                            
                            at_row = kosu_df[kosu_df['at_adi'].str.upper().str.strip() == at_adi.upper().strip()]
                            if len(at_row) > 0:
                                row = at_row.iloc[0]
                                
                                # AGF1_sira
                                agf1_sira_val = row.get('agf1_sira', None)
                                if pd.notna(agf1_sira_val) and str(agf1_sira_val).strip() and str(agf1_sira_val) != '<nil>':
                                    try:
                                        agf1_sira = int(float(agf1_sira_val))
                                    except:
                                        pass
                                
                                # AGF2_sira
                                agf2_sira_val = row.get('agf2_sira', None)
                                if pd.notna(agf2_sira_val) and str(agf2_sira_val).strip() and str(agf2_sira_val) != '<nil>':
                                    try:
                                        agf2_sira = int(float(agf2_sira_val))
                                    except:
                                        pass
                                
                                # Pist türü
                                pist_val = row.get('pist', None)
                                if pd.notna(pist_val) and str(pist_val).strip() and str(pist_val) != '<nil>':
                                    pist_tur = str(pist_val).strip()
                                    # Koşu seviyesinde pist türü bilgisini de kaydet (ilk atın pist türü)
                                    if kosu_pist_tur is None:
                                        kosu_pist_tur = pist_tur
                                
                                # Cins detay
                                cins_detay_val = row.get('cins_detay', None)
                                if pd.notna(cins_detay_val) and str(cins_detay_val).strip() and str(cins_detay_val) != '<nil>':
                                    cins_detay = str(cins_detay_val).strip()
                                    # Koşu seviyesinde cins detay bilgisini de kaydet (ilk atın cins detay)
                                    if kosu_cins_detay is None:
                                        kosu_cins_detay = cins_detay
                                
                                # Jokey adı
                                jokey_val = row.get('jokey_adi', None)
                                if pd.notna(jokey_val) and str(jokey_val).strip() and str(jokey_val) != '<nil>':
                                    jokey_adi = str(jokey_val).strip()
                                
                                # At numarası (no sütunu)
                                no_val = row.get('no', None)
                                if pd.notna(no_val) and str(no_val).strip() and str(no_val) != '<nil>':
                                    try:
                                        at_no = int(float(str(no_val).strip()))
                                        print(f"✅ At numarası bulundu: {at_adi} -> {at_no}")
                                    except Exception as e:
                                        print(f"⚠️ At numarası parse hatası ({at_adi}): {e}")
                                        pass
                                
                                # Ganyan (CSV'den direkt oku)
                                ganyan_val = row.get('ganyan', None)
                                if pd.notna(ganyan_val) and str(ganyan_val).strip() and str(ganyan_val) != '<nil>':
                                    try:
                                        ganyan_str = str(ganyan_val).replace(',', '.')
                                        ganyan = float(ganyan_str)
                                    except:
                                        pass
                                
                                # En iyi derece
                                en_iyi_derece_val = row.get('en_iyi_derece', None)
                                en_iyi_derece = None
                                if pd.notna(en_iyi_derece_val) and str(en_iyi_derece_val).strip() and str(en_iyi_derece_val) != '<nil>':
                                    try:
                                        en_iyi_derece = str(en_iyi_derece_val).strip()
                                    except:
                                        pass
                                
                                # En iyi derece farklı hipodrom
                                en_iyi_derece_farkli_hipodrom_val = row.get('en_iyi_derece_farkli_hipodrom', None)
                                en_iyi_derece_farkli_hipodrom = False
                                if pd.notna(en_iyi_derece_farkli_hipodrom_val):
                                    try:
                                        # Boolean kontrolü: True, 1, "True", "1" gibi değerler
                                        val_str = str(en_iyi_derece_farkli_hipodrom_val).strip().lower()
                                        en_iyi_derece_farkli_hipodrom = val_str in ['true', '1', 'yes', 'evet']
                                    except:
                                        pass
                                
                                # Derece/Sonuç (bitmiş koşularda)
                                if kosu_finished:
                                    # Önce sonuc sütununu kontrol et
                                    sonuc_val = row.get('sonuc', None)
                                    if pd.notna(sonuc_val) and str(sonuc_val).strip() and str(sonuc_val) != '<nil>':
                                        try:
                                            sonuc_int = int(float(str(sonuc_val).strip()))
                                            if sonuc_int > 0:
                                                derece_sonuc = sonuc_int
                                        except:
                                            pass
                                    
                                    # Sonuc yoksa derece sütununu kontrol et
                                    if derece_sonuc is None:
                                        derece_val = row.get('derece', None)
                                        if pd.notna(derece_val) and str(derece_val).strip() and str(derece_val) != '<nil>':
                                            try:
                                                # Derece sütunu zaman formatı olabilir (2.33.84 gibi), sadece sonuc=1 kontrolü yaptık
                                                # Ama eğer sonuc yoksa, derece sütunundan ilk sayıyı al
                                                derece_str = str(derece_val).strip()
                                                # Sadece sayısal değer varsa (1, 2, 3 gibi)
                                                if derece_str.isdigit():
                                                    derece_sonuc = int(derece_str)
                                            except:
                                                pass
                    except Exception as e:
                        print(f"CSV okuma hatası: {e}")
                        pass
                
                kosu_atlar_info.append({
                    'at': at,
                    'at_adi': at_adi,
                    'olasilik': olasilik,
                    'ganyan': ganyan,
                    'agf1': agf1,
                    'agf2': agf2,
                    'agf1_sira': agf1_sira,
                    'agf2_sira': agf2_sira,
                    'pist_tur': pist_tur,
                    'jokey_adi': jokey_adi,
                    'at_no': at_no,
                    'derece_sonuc': derece_sonuc,
                    'en_iyi_derece': en_iyi_derece,
                    'en_iyi_derece_farkli_hipodrom': en_iyi_derece_farkli_hipodrom
                })
            
            # Olasılık sırasını hesapla (aynı koşudaki atlar arasında)
            kosu_atlar_info.sort(key=lambda x: x['olasilik'], reverse=True)
            for idx, at_info in enumerate(kosu_atlar_info):
                at_info['olasilik_sira'] = idx + 1
            
            # AGF1 sırasını hesapla (aynı koşudaki atlar arasında, AGF1 yüksek = iyi)
            kosu_atlar_with_agf1 = [a for a in kosu_atlar_info if a['agf1'] is not None and a['agf1'] > 0]
            kosu_atlar_with_agf1.sort(key=lambda x: x['agf1'], reverse=True)
            for idx, at_info in enumerate(kosu_atlar_with_agf1):
                if at_info['agf1_sira'] is None:
                    at_info['agf1_sira'] = idx + 1
            
            # Koşu objesine bitmiş bilgisi, kazananı, mesafeyi, pist türünü ve cins detay ekle
            kosu['is_finished'] = kosu_finished
            kosu['race_winner'] = race_winner
            kosu['mesafe'] = kosu_mesafe
            kosu['pist_tur'] = kosu_pist_tur
            kosu['cins_detay'] = kosu_cins_detay
            
            # Şimdi bilgileri atlara ekle ve best_bets için hazırla
            for at_info in kosu_atlar_info:
                at = at_info['at']
                at_adi = at_info['at_adi']
                olasilik = at_info['olasilik']
                ganyan = at_info['ganyan']
                agf1 = at_info['agf1']
                agf2 = at_info['agf2']
                agf1_sira = at_info['agf1_sira']
                agf2_sira = at_info.get('agf2_sira')
                olasilik_sira = at_info['olasilik_sira']
                pist_tur = at_info.get('pist_tur')
                jokey_adi = at_info.get('jokey_adi')
                at_no = at_info.get('at_no')
                derece_sonuc = at_info.get('derece_sonuc')
                
                # Son 5 yarış bilgisini al
                son_6_yaris = []
                csv_path = f'data/{hipodrom}_races.csv'
                if os.path.exists(csv_path):
                    try:
                        df = pd.read_csv(csv_path, encoding='utf-8')
                        # Türkiye timezone'una göre tarih al
                        turkey_tz = pytz.timezone('Europe/Istanbul')
                        today = datetime.now(turkey_tz).strftime('%d/%m/%Y')
                        
                        # Bugünün tarihinden önceki yarışları al
                        past_df = df[df['tarih'] != today].copy()
                        if 'tarih' in past_df.columns:
                            # At adına göre filtrele
                            at_df = past_df[past_df['at_adi'].str.upper().str.strip() == at_adi.upper().strip()].copy()
                            
                            if len(at_df) > 0:
                                # Tarih sıralaması için tarih sütununu datetime'a çevir
                                try:
                                    at_df['tarih_datetime'] = pd.to_datetime(at_df['tarih'], format='%d/%m/%Y', errors='coerce')
                                    at_df = at_df.sort_values('tarih_datetime', ascending=False)
                                    at_df = at_df.head(5)  # Son 5 yarış
                                    
                                    for _, row in at_df.iterrows():
                                        mesafe = row.get('mesafe', '')
                                        pist = row.get('pist', '')
                                        sinif = row.get('sinif', '')
                                        handikap = row.get('handikap', '')
                                        cins_detay = row.get('cins_detay', '')
                                        sonuc = row.get('sonuc', None)
                                        derece = row.get('derece', None)
                                        tarih = row.get('tarih', None)
                                        agf1_sira_val = row.get('agf1_sira', None)
                                        agf2_sira_val = row.get('agf2_sira', None)
                                        jokey_val = row.get('jokey_adi', None)
                                        
                                        # Koşu numarasını bul
                                        kosu_no_val = None
                                        for col in ['kosu_no', 'no', 'kosu', 'yaris_kosu_key']:
                                            kosu_val = row.get(col, None)
                                            if pd.notna(kosu_val) and str(kosu_val).strip() and str(kosu_val) != '<nil>':
                                                try:
                                                    # yaris_kosu_key formatı: "kosu_2" gibi olabilir
                                                    kosu_str = str(kosu_val).strip()
                                                    if col == 'yaris_kosu_key' and 'kosu_' in kosu_str:
                                                        kosu_no_val = int(kosu_str.split('_')[1])
                                                    else:
                                                        kosu_no_val = int(float(kosu_str))
                                                    break
                                                except:
                                                    pass
                                        
                                        # Mesafe formatla
                                        mesafe_str = ''
                                        if pd.notna(mesafe) and str(mesafe).strip() and str(mesafe) != '<nil>':
                                            mesafe_str = str(mesafe).strip()
                                            # Sadece sayıları al
                                            mesafe_num = ''.join(filter(str.isdigit, mesafe_str))
                                            if mesafe_num:
                                                mesafe_str = f"{mesafe_num}m"
                                        
                                        # Pist türü formatla (baş harfi büyük: Çim, Kum)
                                        pist_str = ''
                                        if pd.notna(pist) and str(pist).strip() and str(pist) != '<nil>':
                                            pist_val = str(pist).strip()
                                            # Baş harfi büyük yap
                                            if pist_val:
                                                pist_str = pist_val[0].upper() + pist_val[1:].lower() if len(pist_val) > 1 else pist_val.upper()
                                            # Türkçe karakterler için özel düzenleme
                                            pist_str = pist_str.replace('CIM', 'Çim').replace('cim', 'Çim').replace('Cim', 'Çim')
                                            pist_str = pist_str.replace('KUM', 'Kum').replace('kum', 'Kum').replace('Kum', 'Kum')
                                        
                                        # Cins detay formatla (G1, Handikap 16, Şartlı 3 gibi)
                                        cins_detay_str = ''
                                        if pd.notna(cins_detay) and str(cins_detay).strip() and str(cins_detay) != '<nil>':
                                            cins_detay_val = str(cins_detay).strip()
                                            # Cins detay değerini temizle ve formatla
                                            if cins_detay_val:
                                                # "G1", "Handikap 16", "Şartlı 3" gibi formatları koru
                                                cins_detay_str = cins_detay_val
                                        
                                        # Eğer cins_detay yoksa handikap kullan (geriye dönük uyumluluk için)
                                        if not cins_detay_str and pd.notna(handikap) and str(handikap).strip() and str(handikap) != '<nil>':
                                            try:
                                                handikap_val = str(handikap).strip()
                                                # Handikap değerini al (sadece sayı olabilir)
                                                if handikap_val.isdigit():
                                                    # Çok büyük sayılar (960 gibi) muhtemelen yanlış veri, atla
                                                    handikap_num = int(handikap_val)
                                                    if handikap_num < 100:  # Sadece mantıklı handikap değerleri (0-99)
                                                        cins_detay_str = f"Handikap {handikap_num}"
                                                else:
                                                    # Sayı içeriyorsa al
                                                    handikap_num = ''.join(filter(str.isdigit, handikap_val))
                                                    if handikap_num and int(handikap_num) < 100:
                                                        cins_detay_str = f"Handikap {handikap_num}"
                                            except:
                                                pass
                                        
                                        # Eğer hala yoksa sınıf kullan
                                        if not cins_detay_str and pd.notna(sinif) and str(sinif).strip() and str(sinif) != '<nil>':
                                            cins_detay_str = str(sinif).strip()
                                        
                                        # Sonuç formatla
                                        sonuc_str = ''
                                        if pd.notna(sonuc) and str(sonuc).strip() and str(sonuc) != '<nil>':
                                            try:
                                                sonuc_int = int(float(str(sonuc).strip()))
                                                if sonuc_int == 1:
                                                    sonuc_str = 'Kazandı'
                                                else:
                                                    sonuc_str = f'{sonuc_int}. oldu'
                                            except:
                                                pass
                                        
                                        if not sonuc_str and pd.notna(derece) and str(derece).strip() and str(derece) != '<nil>':
                                            try:
                                                derece_str = str(derece).strip()
                                                if derece_str.isdigit():
                                                    derece_int = int(derece_str)
                                                    if derece_int == 1:
                                                        sonuc_str = 'Kazandı'
                                                    else:
                                                        sonuc_str = f'{derece_int}. oldu'
                                            except:
                                                pass
                                        
                                        # Tarih formatla
                                        tarih_str = None
                                        if pd.notna(tarih) and str(tarih).strip() and str(tarih) != '<nil>':
                                            tarih_str = str(tarih).strip()
                                        
                                        # AGF1_sira formatla
                                        agf1_sira_str = None
                                        if pd.notna(agf1_sira_val) and str(agf1_sira_val).strip() and str(agf1_sira_val) != '<nil>':
                                            try:
                                                agf1_sira_str = int(float(str(agf1_sira_val).strip()))
                                            except:
                                                pass
                                        
                                        # AGF2_sira formatla
                                        agf2_sira_str = None
                                        if pd.notna(agf2_sira_val) and str(agf2_sira_val).strip() and str(agf2_sira_val) != '<nil>':
                                            try:
                                                agf2_sira_str = int(float(str(agf2_sira_val).strip()))
                                            except:
                                                pass
                                        
                                        # Jokey formatla
                                        jokey_str = None
                                        if pd.notna(jokey_val) and str(jokey_val).strip() and str(jokey_val) != '<nil>':
                                            jokey_str = str(jokey_val).strip()
                                        
                                        # Formatla: "1200m Çim, G1, Kazandı" veya "1200m Çim, Handikap 16, 2. oldu"
                                        if mesafe_str or pist_str or cins_detay_str or sonuc_str:
                                            parts = []
                                            if mesafe_str:
                                                parts.append(mesafe_str)
                                            if pist_str:
                                                parts.append(pist_str)
                                            if cins_detay_str:
                                                parts.append(cins_detay_str)
                                            if sonuc_str:
                                                parts.append(sonuc_str)
                                            
                                            if parts:
                                                # Detaylı bilgi ile birlikte ekle
                                                yaris_info = {
                                                    'text': ', '.join(parts),
                                                    'tarih': tarih_str,
                                                    'kosu_no': kosu_no_val,
                                                    'agf1_sira': agf1_sira_str,
                                                    'agf2_sira': agf2_sira_str,
                                                    'jokey': jokey_str
                                                }
                                                son_6_yaris.append(yaris_info)
                                except Exception as e:
                                    print(f"Son 5 yarış parse hatası ({at_adi}): {e}")
                                    pass
                    except Exception as e:
                        print(f"Son 5 yarış okuma hatası ({at_adi}): {e}")
                        pass
                
                # Son 5 yarış bilgisini at objesine ekle
                at['son_6_yaris'] = son_6_yaris
                
                # Son 10 ganyan geçmişini al (JSON dosyasından)
                son_10_ganyan = get_ganyan_history(hipodrom, at_adi)
                at['son_10_ganyan'] = son_10_ganyan
                
                # Ganyan ve AGF bilgilerini ekle
                at['ganyan'] = ganyan
                at['agf1'] = agf1
                at['agf2'] = agf2
                at['agf1_sira'] = agf1_sira
                at['agf2_sira'] = agf2_sira
                at['olasilik_sira'] = olasilik_sira
                at['jokey_adi'] = jokey_adi
                at['at_no'] = at_no
                at['en_iyi_derece'] = at_info.get('en_iyi_derece')
                at['en_iyi_derece_farkli_hipodrom'] = at_info.get('en_iyi_derece_farkli_hipodrom', False)
                
                # Bitmiş koşularda kazanan bilgisini ekle
                at['is_winner'] = False
                at['derece_sonuc'] = derece_sonuc
                if kosu_finished and race_winner:
                    at['is_winner'] = (at_adi.upper().strip() == race_winner.upper().strip())
                
                # AGF1 veya AGF2'den biri olmalı - ikisi de yoksa varsayılan değer kullan
                # AGF1 varsa her zaman AGF1 kullan (koşu numarasına bakmadan)
                # AGF1 yoksa AGF2 kullan
                # İkisi de yoksa 0 kullan (AGF bilgisi olmayan atlar için)
                agf_value = None
                agf_type = None
                
                if agf1 is not None and agf1 > 0:
                    # AGF1 varsa her zaman AGF1 kullan
                    agf_value = agf1
                    agf_type = 'AGF1'
                elif agf2 is not None and agf2 > 0:
                    # AGF1 yoksa AGF2 kullan
                    agf_value = agf2
                    agf_type = 'AGF2'
                else:
                    # AGF1 ve AGF2 bilgisi yoksa varsayılan değer kullan (0)
                    agf_value = 0
                    agf_type = None
                
                # AGF ve yapay zeka skorunu birleştir
                # Olasılık skoru (combined_score) = AGF skoru (%40) + AI olasılık skoru (%60)
                combined_score = None
                value_score = None
                profit_score = None
                profit_from_score = None
                
                # Yapay zeka skoru: olasılık (0-100 arası) -> 0-1 arasına normalize et
                ai_score = olasilik / 100.0  # 0-1 arası
                
                # AGF skoru: yüksek AGF = güçlü at (yüksek skor)
                # Normalize et: AGF yüksek = yüksek skor
                # Örnek: AGF=50 -> skor=1.0, AGF=1 -> skor=0.0
                min_agf = 1.0  # Minimum AGF (zayıf)
                max_agf = 100.0  # Maximum AGF (güçlü)
                
                # AGF'i normalize et: yüksek AGF = yüksek skor
                if agf_value is None or agf_value <= 0:
                    agf_score = 0.0
                elif agf_value >= max_agf:
                    agf_score = 1.0
                elif agf_value <= min_agf:
                    agf_score = 0.0
                else:
                    # Lineer interpolasyon: yüksek AGF = yüksek skor
                    agf_score = (agf_value - min_agf) / (max_agf - min_agf)
                
                # Birleştirilmiş skor (Olasılık Skoru): AGF ve AI skorunun ağırlıklı ortalaması
                # AGF %40, AI olasılık skoru %60 ağırlık (daha fazla AI'a güven)
                combined_score = (0.4 * agf_score) + (0.6 * ai_score)
                
                # Value skoru hesapla (sadece yakındaki koşular için)
                if kosu_soon and ganyan:
                    value_score = calculate_value_score(olasilik, ganyan)
                    profit_score = calculate_profit_score(olasilik, ganyan)
                    at['value_score'] = value_score
                    at['profit_score'] = profit_score
                else:
                    at['value_score'] = None
                    at['profit_score'] = None
                
                # Skor ve Ganyan'dan kazanç skoru hesapla (ganyan varsa)
                if ganyan and combined_score is not None:
                    profit_from_score = calculate_profit_from_score_and_ganyan(combined_score, ganyan)
                
                # Kazandı mı kontrol et
                is_winner = False
                if kosu_finished and race_winner:
                    is_winner = (at_adi.upper().strip() == race_winner.upper().strip())
                
                # En iyi derece bilgisi
                en_iyi_derece = at_info.get('en_iyi_derece')
                en_iyi_derece_farkli_hipodrom = at_info.get('en_iyi_derece_farkli_hipodrom', False)
                
                # AGF1 veya AGF2'ye sahip atları ekle
                all_candidates.append({
                    'kosu_no': kosu['kosu_no'],
                    'kosu_saat': kosu['saat'],
                    'kosu_sinif': kosu['sinif'],
                    'kosu_mesafe': kosu.get('mesafe'),  # Koşu mesafesi eklendi
                    'pist_tur': pist_tur,  # Pist türü eklendi
                    'jokey_adi': jokey_adi,  # Jokey adı eklendi
                    'at_no': at_no,  # At numarası eklendi
                    'at_adi': at_adi,
                    'olasilik': olasilik,
                    'olasilik_sira': olasilik_sira,
                    'agf1': agf1,  # Orijinal AGF1 değeri (varsa)
                    'agf2': agf2,  # Orijinal AGF2 değeri (varsa)
                    'agf_value': agf_value,  # Kullanılan AGF değeri (AGF1 veya AGF2)
                    'agf_type': agf_type,  # 'AGF1' veya 'AGF2'
                    'agf1_sira': agf1_sira,  # AGF1 sırası (varsa)
                    'agf2_sira': agf2_sira,  # AGF2 sırası (varsa)
                    'ganyan': ganyan,  # Her zaman ekle (göstermek için)
                    'en_iyi_derece': en_iyi_derece,  # En iyi derece (varsa)
                    'en_iyi_derece_farkli_hipodrom': en_iyi_derece_farkli_hipodrom,  # Farklı hipodrom mu
                    'value_score': value_score,
                    'profit_score': profit_score if kosu_soon and ganyan else None,
                    'profit_from_score': profit_from_score,  # Skor ve Ganyan'dan hesaplanan
                    'combined_score': combined_score,
                    'is_soon': kosu_soon,
                    'is_finished': kosu_finished,
                    'is_winner': is_winner,
                    'race_winner': race_winner if kosu_finished else None,  # Her at için race_winner ekle (bitmiş koşularda)
                    'derece_sonuc': derece_sonuc  # Bitmiş koşularda atın kaçıncı olduğu
                })
        
        # Koşu bazında grupla ve her koşu için en yüksek 3 atı al
        # Önce aktif olanları, sonra bitmişleri işle
        active_bets = [b for b in all_candidates if not b.get('is_finished', False)]
        finished_bets = [b for b in all_candidates if b.get('is_finished', False)]
        
        print(f"📊 {hipodrom} - Toplam aday: {len(all_candidates)}, Aktif: {len(active_bets)}, Bitmiş: {len(finished_bets)}")
        
        # Koşu bazında grupla (debug için)
        races_debug = {}
        for bet in all_candidates:
            race_key = f"{bet['kosu_no']}_{bet['kosu_saat']}"
            if race_key not in races_debug:
                races_debug[race_key] = {'is_finished': bet.get('is_finished', False), 'count': 0}
            races_debug[race_key]['count'] += 1
        
        print(f"📊 {hipodrom} - Toplam koşu sayısı: {len(races_debug)}")
        for race_key, info in sorted(races_debug.items()):
            print(f"  - Koşu {race_key}: {'Bitmiş' if info['is_finished'] else 'Aktif'}, {info['count']} at")
        
        def get_top_3_per_race(bets):
            """Koşu bazında grupla ve her koşu için en yüksek 3 atı al"""
            # Koşu bazında grupla (koşu_no, kosu_saat kombinasyonu)
            races_dict = {}
            for bet in bets:
                race_key = f"{bet['kosu_no']}_{bet['kosu_saat']}"
                if race_key not in races_dict:
                    races_dict[race_key] = []
                races_dict[race_key].append(bet)
            
            # Her koşu için en yüksek 3 atı al (combined_score'a göre)
            result = []
            for race_key, race_bets in races_dict.items():
                # Combined_score'a göre sırala (yüksekten düşüğe)
                race_bets.sort(key=lambda x: x['combined_score'] if x['combined_score'] is not None else -1, reverse=True)
                # En yüksek 3 atı al
                result.extend(race_bets[:3])
            
            # Koşu numarasına göre sırala
            result.sort(key=lambda x: (x['kosu_no'], -(x['combined_score'] if x['combined_score'] is not None else -1)))
            return result
        
        # Aktif koşular için en yüksek 3 atı al
        active_top_bets = get_top_3_per_race(active_bets)
        
        # Bitmiş koşular için en yüksek 3 atı al
        finished_top_bets = get_top_3_per_race(finished_bets)
        
        # Önce aktifleri, sonra bitmişleri ekle
        all_candidates_sorted = active_top_bets + finished_top_bets
        
        # En mantıklı oyunlar: Koşu bazında gruplanmış, her koşu için en yüksek 3 at
        data['best_bets'] = all_candidates_sorted
        
        # Response'u hazırla
        response_data = data
        
        # Cache'e kaydet (parse edilmiş data'yı da sakla)
        _tahmin_cache[hipodrom] = {
            'data': response_data,
            'timestamp': datetime.now(),
            'file_mtime': file_mtime,
            'parsed_data': data  # Parse edilmiş data'yı da sakla (tekrar parse etmemek için)
        }
        
        return jsonify(response_data)
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"❌ API hatası ({hipodrom}): {str(e)}")
        print(f"Traceback: {error_trace}")
        return jsonify({'error': str(e), 'traceback': error_trace}), 500

@app.route('/api/manual-update', methods=['POST'])
def api_manual_update():
    """Manuel güncelleme tetikle (test için)"""
    try:
        print("="*60)
        print("🔄 Manuel güncelleme tetiklendi...")
        print(f"📅 Zaman: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        print("="*60)
        # Background thread'de çalıştır
        import threading
        def update_in_background():
            try:
                print("📥 CSV verileri güncelleniyor...")
                update_all_data()
                print("✅ CSV güncellemesi tamamlandı")
                print("🎯 Tahminler oluşturuluyor...")
                run_daily_update()
                print("="*60)
                print("✅ Manuel güncelleme tamamlandı!")
                print(f"📅 Zaman: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
                print("="*60)
            except Exception as e:
                print("="*60)
                print(f"❌ Manuel güncelleme hatası: {e}")
                import traceback
                traceback.print_exc()
                print("="*60)
        
        thread = threading.Thread(target=update_in_background, daemon=True)
        thread.start()
        
        return jsonify({
            'status': 'success',
            'message': 'Güncelleme başlatıldı, arka planda çalışıyor... Log\'ları kontrol et. 10-15 dakika sürebilir.'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/scheduler-status')
def api_scheduler_status():
    """Scheduler durumunu kontrol et"""
    try:
        jobs = scheduler.get_jobs()
        job_info = []
        for job in jobs:
            job_info.append({
                'id': job.id,
                'name': job.name,
                'next_run': str(job.next_run_time) if job.next_run_time else None
            })
        return jsonify({
            'scheduler_running': scheduler.running,
            'jobs': job_info,
            'total_jobs': len(jobs)
        })
    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500

@app.route('/api/completed-races')
def api_completed_races():
    """Tüm şehirlerden son 5 tamamlanan koşuyu döndür (carousel widget için) - En Mantıklı Oyunlar'daki kazananlar"""
    try:
        completed_races = []
        
        # Tüm hipodromlar için tamamlanan koşuları topla
        for hipodrom in HIPODROMLAR:
            try:
                # api_tahminler endpoint'ini çağır ve best_bets'i al
                # Direkt fonksiyonu çağırmak yerine, parse_tahmin_dosyasi kullan
                try:
                    file_path = f'output/{hipodrom}_tahminler.txt'
                    if os.path.exists(file_path):
                        # Tahmin dosyasını parse et
                        data = parse_tahmin_dosyasi(file_path)
                        if data:
                            try:
                                # Ganyan ve AGF verilerini ekle
                                ganyan_agf_data = get_ganyan_agf_data(hipodrom)
                                
                                # En mantıklı oyunlar listesi oluştur
                                if 'kosular' in data and data['kosular']:
                                    # Türkiye timezone'una göre saat al
                                    turkey_tz = pytz.timezone('Europe/Istanbul')
                                    current_time = datetime.now(turkey_tz)
                                    current_hour = current_time.hour
                                    current_minute = current_time.minute
                                    
                                    def is_race_finished_local(kosu_saat):
                                        """Koşu bitmiş mi? (saati geçmiş mi?)"""
                                        try:
                                            race_hour, race_minute = map(int, kosu_saat.split(':'))
                                            race_total_minutes = race_hour * 60 + race_minute
                                            current_total_minutes = current_hour * 60 + current_minute
                                            time_diff = current_total_minutes - race_total_minutes
                                            return time_diff >= 10
                                        except:
                                            return False
                                    
                                    # Best bets oluştur
                                    all_candidates = []
                                    for kosu in data['kosular']:
                                        kosu_finished = is_race_finished_local(kosu.get('saat', ''))
                                        race_winner = get_race_winner_helper(hipodrom, kosu.get('kosu_no'), kosu.get('saat')) if kosu_finished else None
                                        
                                        for at in kosu.get('atlar', []):
                                            at_no = at.get('at_no')
                                            at_adi = at.get('at_adi')
                                            
                                            # Ganyan ve AGF verilerini al
                                            ganyan_value = ganyan_agf_data.get(at_adi, {}).get('ganyan')
                                            agf1_value = ganyan_agf_data.get(at_adi, {}).get('agf1')
                                            
                                            # Combined score hesapla
                                            ai_score = at.get('ai_score', 0)
                                            combined_score = (ai_score * 0.7) + ((1.0 / (agf1_value or 100)) * 30)
                                            
                                            is_winner = race_winner and str(at_no) == str(race_winner)
                                            
                                            all_candidates.append({
                                                'hipodrom': hipodrom,
                                                'kosu_no': kosu.get('kosu_no'),
                                                'kosu_saat': kosu.get('saat'),
                                                'at_no': at_no,
                                                'at_adi': at_adi,
                                                'jokey_adi': at.get('jokey_adi'),
                                                'ai_score': ai_score,
                                                'combined_score': combined_score,
                                                'ganyan': ganyan_value,
                                                'agf1': agf1_value,
                                                'is_finished': kosu_finished,
                                                'is_winner': is_winner
                                            })
                                    
                                    # Koşu bazında en yüksek 3 atı al
                                    def get_top_3_per_race_local(bets):
                                        races_dict = {}
                                        for bet in bets:
                                            race_key = f"{bet.get('kosu_no')}_{bet.get('kosu_saat')}"
                                            if race_key not in races_dict:
                                                races_dict[race_key] = []
                                            races_dict[race_key].append(bet)
                                        
                                        top_bets = []
                                        for race_key, race_bets in races_dict.items():
                                            sorted_bets = sorted(race_bets, key=lambda x: x.get('combined_score', 0), reverse=True)
                                            top_bets.extend(sorted_bets[:3])
                                        return top_bets
                                    
                                    # Bitmiş ve aktif koşuları ayır
                                    finished_bets = [b for b in all_candidates if b.get('is_finished')]
                                    active_bets = [b for b in all_candidates if not b.get('is_finished')]
                                    
                                    # Her gruptan en yüksek 3 atı al
                                    finished_top_bets = get_top_3_per_race_local(finished_bets)
                                    
                                    # Bitmiş koşulardan kazananları al
                                    finished_winners = [bet for bet in finished_top_bets if bet.get('is_winner')]
                                    
                                    # Eğer kazanan yoksa, bitmiş koşulardan en yüksek skorlu atları al
                                    if len(finished_winners) == 0 and len(finished_top_bets) > 0:
                                        races_dict = {}
                                        for bet in finished_top_bets:
                                            race_key = f"{bet.get('kosu_no')}_{bet.get('kosu_saat')}"
                                            if race_key not in races_dict:
                                                races_dict[race_key] = []
                                            races_dict[race_key].append(bet)
                                        
                                        for race_key, bets in races_dict.items():
                                            bets_sorted = sorted(bets, key=lambda x: x.get('combined_score', 0), reverse=True)
                                            if len(bets_sorted) > 0:
                                                top_bet = bets_sorted[0].copy()
                                                top_bet['is_winner'] = False
                                                finished_winners.append(top_bet)
                                
                                    # Her kazanan için completed_races'e ekle
                                    try:
                                        for bet in finished_winners:
                                            # Timestamp hesapla
                                            try:
                                                race_hour, race_minute = map(int, bet['kosu_saat'].split(':'))
                                                race_total_minutes = race_hour * 60 + race_minute
                                            except:
                                                race_total_minutes = 0
                                            
                                            # Ganyan değerini al (float veya None olabilir)
                                            ganyan_value = bet.get('ganyan')
                                            if ganyan_value is not None:
                                                try:
                                                    # String ise float'a çevir
                                                    if isinstance(ganyan_value, str):
                                                        ganyan_value = float(ganyan_value.replace(',', '.'))
                                                    elif isinstance(ganyan_value, (int, float)):
                                                        ganyan_value = float(ganyan_value)
                                                except (ValueError, TypeError):
                                                    ganyan_value = None
                                            
                                            completed_races.append({
                                                'hipodrom': bet.get('hipodrom', hipodrom),
                                                'kosu_no': bet.get('kosu_no'),
                                                'kosu_saat': bet.get('kosu_saat'),
                                                'kosu_mesafe': bet.get('kosu_mesafe'),
                                                'pist_tur': bet.get('pist_tur'),
                                                'kosu_sinif': bet.get('kosu_sinif'),
                                                'cins_detay': bet.get('cins_detay'),
                                                'at_no': bet.get('at_no'),
                                                'at_adi': bet.get('at_adi'),
                                                'jokey_adi': bet.get('jokey_adi'),
                                                'is_winner': True,
                                                'derece_sonuc': 1,
                                                'combined_score': bet.get('combined_score'),
                                                'ganyan': ganyan_value,
                                                'timestamp': race_total_minutes
                                            })
                                    except Exception as e:
                                        print(f"⚠️ {hipodrom} için completed_races eklenirken hata: {e}")
                                        import traceback
                                        traceback.print_exc()
                                        continue
                            except Exception as e:
                                print(f"❌ {hipodrom} tamamlanan koşular parse edilirken hata: {e}")
                                import traceback
                                traceback.print_exc()
                                continue
                except Exception as e:
                    print(f"❌ {hipodrom} dosya okuma hatası: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
            except Exception as e:
                print(f"❌ {hipodrom} tamamlanan koşular işlenirken hata: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        # Timestamp'e göre sırala (en yeni en son) ve son 5'i al
        completed_races.sort(key=lambda x: x['timestamp'], reverse=True)
        completed_races = completed_races[:5]
        
        print(f"📊 Tamamlanan koşular (ilk 3'te kazanan): {len(completed_races)} adet")
        for race in completed_races:
            print(f"  - {race['hipodrom']} {race['kosu_no']}. Koşu: {race['at_adi']} (Kazanan)")
        
        return jsonify({
            'completed_races': completed_races
        })
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"❌ Tamamlanan koşular API hatası: {str(e)}")
        print(f"Traceback: {error_trace}")
        return jsonify({'error': str(e), 'traceback': error_trace}), 500

@app.route('/tahminler/<hipodrom>')
def tahminler(hipodrom):
    """Tahminler sayfası"""
    hipodrom = hipodrom.upper()
    return render_template('predictions.html', hipodrom=hipodrom)

def update_ganyan_history(hipodrom):
    """CSV'den bugünkü ganyan değerlerini al ve her at için son 10 ganyan geçmişini güncelle"""
    ganyan_history_file = f'data/{hipodrom}_ganyan_history.json'
    csv_path = f'data/{hipodrom}_races.csv'
    
    if not os.path.exists(csv_path):
        return
    
    try:
        # Mevcut geçmişi yükle
        ganyan_history = {}
        if os.path.exists(ganyan_history_file):
            try:
                with open(ganyan_history_file, 'r', encoding='utf-8') as f:
                    ganyan_history = json.load(f)
            except:
                ganyan_history = {}
        
        # CSV'den bugünkü verileri oku
        df = pd.read_csv(csv_path, encoding='utf-8')
        # Türkiye timezone'una göre tarih al
        turkey_tz = pytz.timezone('Europe/Istanbul')
        today = datetime.now(turkey_tz).strftime('%d/%m/%Y')
        
        if 'tarih' not in df.columns:
            return
        
        today_df = df[df['tarih'] == today].copy()
        
        if len(today_df) == 0:
            return
        
        # Bugünkü her at için ganyan değerini al ve geçmişe ekle
        for _, row in today_df.iterrows():
            at_adi = str(row.get('at_adi', '')).strip().upper()
            if not at_adi:
                continue
            
            ganyan_val = row.get('ganyan', None)
            if pd.notna(ganyan_val) and str(ganyan_val).strip() and str(ganyan_val) != '<nil>':
                try:
                    ganyan_str = str(ganyan_val).replace(',', '.')
                    ganyan_float = float(ganyan_str)
                    if ganyan_float > 0:  # Sadece geçerli ganyan değerleri
                        # At için geçmiş yoksa oluştur
                        if at_adi not in ganyan_history:
                            ganyan_history[at_adi] = []
                        
                        # Bugünkü ganyan değerini ekle
                        ganyan_history[at_adi].append(ganyan_float)
                        
                        # Son 10'u tut (en yeni değerler)
                        if len(ganyan_history[at_adi]) > 10:
                            ganyan_history[at_adi] = ganyan_history[at_adi][-10:]
                except:
                    pass
        
        # Geçmişi dosyaya kaydet
        with open(ganyan_history_file, 'w', encoding='utf-8') as f:
            json.dump(ganyan_history, f, ensure_ascii=False, indent=2)
        
    except Exception as e:
        print(f"❌ {hipodrom} ganyan geçmişi güncelleme hatası: {e}")

def get_ganyan_history(hipodrom, at_adi):
    """Belirli bir at için son 10 ganyan geçmişini döndür"""
    ganyan_history_file = f'data/{hipodrom}_ganyan_history.json'
    
    if not os.path.exists(ganyan_history_file):
        return []
    
    try:
        with open(ganyan_history_file, 'r', encoding='utf-8') as f:
            ganyan_history = json.load(f)
        
        at_key = at_adi.upper().strip()
        return ganyan_history.get(at_key, [])
    except:
        return []

def update_data_for_hipodrom(hipodrom):
    """Belirli bir hipodrom için CSV verilerini güncelle ve ganyan geçmişini güncelle"""
    try:
        print(f"📥 {hipodrom} verisi güncelleniyor...")
        
        # Data klasörünün var olduğundan emin ol
        data_dir = 'data'
        if not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)
            print(f"📁 Data klasörü oluşturuldu: {data_dir}")
        
        from horse_racing_predictor import HorseRacingPredictor
        predictor = HorseRacingPredictor(hipodrom)
        success = predictor.download_data()
        
        if not success:
            print(f"⚠️ {hipodrom} verisi indirilemedi")
            return False
        
        # Dosyanın gerçekten oluştuğunu kontrol et
        csv_path = f'data/{hipodrom}_races.csv'
        if os.path.exists(csv_path):
            file_size = os.path.getsize(csv_path)
            print(f"✅ {hipodrom} CSV dosyası oluşturuldu: {csv_path} ({file_size} bytes)")
        else:
            print(f"❌ {hipodrom} CSV dosyası oluşturulamadı: {csv_path}")
            return False
        
        # CSV güncellendikten sonra ganyan geçmişini güncelle
        update_ganyan_history(hipodrom)
        
        print(f"✅ {hipodrom} verisi güncellendi")
        return True
    except Exception as e:
        print(f"❌ {hipodrom} veri güncelleme hatası: {e}")
        import traceback
        traceback.print_exc()
        return False

def update_predictions_for_hipodrom(hipodrom):
    """Belirli bir hipodrom için tahminleri güncelle (model her seferinde yeniden eğitilir)"""
    try:
        print(f"🔄 {hipodrom} için model eğitiliyor ve tahminler oluşturuluyor...")
        result = subprocess.run(
            ['python3', 'tahmin_yap.py', hipodrom],
            capture_output=True,
            text=True,
            timeout=300  # 5 dakika timeout
        )
        if result.returncode == 0:
            print(f"✅ {hipodrom} model eğitildi ve tahminler oluşturuldu")
            return True
        else:
            print(f"❌ {hipodrom} güncelleme hatası: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ {hipodrom} güncelleme hatası: {e}")
        return False

def update_all_data():
    """Tüm hipodromlar için sadece CSV verilerini güncelle (tahminler güncellenmez)"""
    global last_update_time
    print(f"🔄 CSV verileri güncelleniyor... ({datetime.now()})")
    
    # Data ve output klasörlerinin var olduğundan emin ol
    for dir_name in ['data', 'output']:
        if not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)
            print(f"📁 {dir_name} klasörü oluşturuldu")
    
    # Sadece CSV verilerini güncelle
    print("📥 CSV verileri güncelleniyor...")
    success_count = 0
    for hipodrom in HIPODROMLAR:
        if update_data_for_hipodrom(hipodrom):
            success_count += 1
    
    # Son güncelleme zamanını güncelle (site yenileme için)
    last_update_time = datetime.now().isoformat()
    
    print(f"✅ CSV güncellemeleri tamamlandı ({success_count}/{len(HIPODROMLAR)} başarılı) ({datetime.now()})")

def update_all_data_and_predictions():
    """Tüm hipodromlar için önce verileri, sonra tahminleri güncelle (model her seferinde yeniden eğitilir)"""
    print(f"🔄 Tüm veriler ve tahminler güncelleniyor... ({datetime.now()})")
    
    # Önce verileri güncelle
    print("📥 CSV verileri güncelleniyor...")
    for hipodrom in HIPODROMLAR:
        update_data_for_hipodrom(hipodrom)
    
    # Tahminleri güncelle (model her seferinde yeniden eğitilir)
    print("🔄 Modeller eğitiliyor ve tahminler oluşturuluyor...")
    for hipodrom in HIPODROMLAR:
        update_predictions_for_hipodrom(hipodrom)
    
    print(f"✅ Tüm güncellemeler tamamlandı ({datetime.now()})")

def run_daily_update():
    """Günlük otomatik güncelleme - bugün koşu olan şehirler için tahmin çalıştır"""
    print(f"🔄 Günlük otomatik güncelleme başlatılıyor... ({datetime.now()})")
    try:
        result = subprocess.run(
            ['python3', 'daily_update.py'],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True,
            text=True,
            timeout=3600  # 1 saat timeout
        )
        if result.returncode == 0:
            print(f"✅ Günlük otomatik güncelleme tamamlandı ({datetime.now()})")
            print(result.stdout)
        else:
            print(f"❌ Günlük otomatik güncelleme hatası: {result.stderr}")
    except Exception as e:
        print(f"❌ Günlük otomatik güncelleme hatası: {e}")

# İlk güncelleme zamanını ayarla (uygulama başlarken)
last_update_time = datetime.now().isoformat()

def initial_data_update():
    """Uygulama başlarken ilk veri güncellemesini yap (background'da)"""
    import threading
    import time
    def update_in_background():
        # 10 saniye bekle (uygulama tamamen başlasın) - Render için daha hızlı
        time.sleep(10)
        print("="*60)
        print("🔄 İlk veri güncellemesi başlatılıyor...")
        print(f"📅 Zaman: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        print("="*60)
        try:
            # Önce CSV verilerini güncelle
            print("📥 1. Adım: CSV verileri güncelleniyor...")
            update_all_data()
            print("✅ CSV güncellemesi tamamlandı")
            
            # Sonra bugün koşu olan şehirler için tahmin çalıştır
            print("🎯 2. Adım: Tahminler oluşturuluyor...")
            run_daily_update()
            print("="*60)
            print("✅ İlk veri güncellemesi tamamlandı!")
            print(f"📅 Zaman: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
            print("="*60)
        except Exception as e:
            print("="*60)
            print(f"❌ İlk veri güncellemesi hatası: {e}")
            import traceback
            traceback.print_exc()
            print("="*60)
    
    # Background thread'de çalıştır (uygulama başlamasını engellemesin)
    thread = threading.Thread(target=update_in_background, daemon=True)
    thread.start()
    print("✅ İlk güncelleme thread'i başlatıldı (10 saniye sonra başlayacak)")

# Uygulama başlarken ilk güncellemeyi yap
initial_data_update()

# 5 dakikada bir sadece CSV verilerini güncelle (tahminler güncellenmez)
# Render'da scheduler'ın çalıştığından emin olmak için hemen başlat
scheduler.add_job(
    func=update_all_data,
    trigger=IntervalTrigger(minutes=5),
    id='update_data',
    name='Update CSV data every 5 minutes (predictions not updated)',
    replace_existing=True
)
print(f"✅ Scheduler başlatıldı: {scheduler.running}")
print(f"📋 Aktif job'lar: {[job.id for job in scheduler.get_jobs()]}")

# Her gün sabah 07:00'da bugün koşu olan şehirler için tahmin çalıştır
scheduler.add_job(
    func=run_daily_update,
    trigger=CronTrigger(hour=7, minute=0),
    id='daily_update',
    name='Daily update: Run predictions for cities with races today',
    replace_existing=True
)

if __name__ == '__main__':
    # Production'da port environment variable'dan alınır
    port = int(os.environ.get('PORT', 5001))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(debug=debug, host='0.0.0.0', port=port)
