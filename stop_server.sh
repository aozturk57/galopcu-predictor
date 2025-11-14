#!/bin/bash

# At Yarışı Tahmin Sistemi - Durdurma Scripti
PORT=5001
PID_FILE="/tmp/galopcu_predictor_${PORT}.pid"

# PID dosyasından process'i öldür
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "🛑 Flask uygulaması durduruluyor (PID: $PID)..."
        kill -9 "$PID" 2>/dev/null
        echo "✅ Durduruldu"
    else
        echo "⚠️ Process zaten durmuş"
    fi
    rm -f "$PID_FILE"
else
    echo "⚠️ PID dosyası bulunamadı"
fi

# Port'u kullanan process'i öldür
lsof -ti:$PORT | xargs kill -9 2>/dev/null || true
pkill -f "python.*web_app" 2>/dev/null || true

echo "✅ Tüm Flask process'leri temizlendi"



