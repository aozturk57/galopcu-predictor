#!/bin/bash

# At Yarışı Tahmin Sistemi - Otomatik Başlatma Scripti
cd "$(dirname "$0")"

PORT=5001
PID_FILE="/tmp/galopcu_predictor_${PORT}.pid"
LOG_FILE="/tmp/flask_${PORT}.log"

# Eski process'i öldür
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "🔄 Eski process öldürülüyor (PID: $OLD_PID)..."
        kill -9 "$OLD_PID" 2>/dev/null
    fi
    rm -f "$PID_FILE"
fi

# Port'u kullanan process'i öldür
lsof -ti:$PORT | xargs kill -9 2>/dev/null || true
pkill -f "python.*web_app" 2>/dev/null || true

# Biraz bekle
sleep 1

# Flask uygulamasını başlat
echo "🚀 Flask uygulaması başlatılıyor (Port: $PORT)..."
nohup python3 web_app.py > "$LOG_FILE" 2>&1 &
NEW_PID=$!

# PID'yi kaydet
echo $NEW_PID > "$PID_FILE"

# Biraz bekle ve kontrol et
sleep 2
if kill -0 "$NEW_PID" 2>/dev/null; then
    echo "✅ Flask uygulaması başlatıldı (PID: $NEW_PID)"
    echo "📊 Site: http://localhost:$PORT"
    echo "📝 Log: $LOG_FILE"
    echo "🛑 Durdurmak için: kill $NEW_PID"
else
    echo "❌ Flask uygulaması başlatılamadı!"
    echo "📝 Log dosyasını kontrol edin: $LOG_FILE"
    exit 1
fi



