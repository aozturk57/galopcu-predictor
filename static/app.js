// Modern JavaScript for At Yarışı Tahmin Web App

// API Base URL
const API_BASE = '';

// Utility Functions
function formatDate(dateString) {
    if (!dateString) return '-';
    return dateString;
}

function formatOlasilik(olasilik) {
    return olasilik.toFixed(1) + '%';
}

function getIconClass(icon) {
    if (icon === '📈') return 'icon-up';
    if (icon === '📉') return 'icon-down';
    if (icon === '🔥') return 'icon-fire';
    return '';
}

// Ganyan grafik SVG'si oluştur (son 10 ganyan değeri için)
function createGanyanChartSVG(ganyanValues) {
    if (!ganyanValues || ganyanValues.length === 0) {
        return '';
    }
    
    const width = 60;
    const height = 24;
    const padding = 2;
    const chartWidth = width - (padding * 2);
    const chartHeight = height - (padding * 2);
    
    // Değerleri normalize et (0-1 arası)
    const min = Math.min(...ganyanValues);
    const max = Math.max(...ganyanValues);
    const range = max - min || 1; // range 0 ise 1 yap
    
    const normalizedValues = ganyanValues.map(val => (val - min) / range);
    
    // Noktaları hesapla
    const numPoints = normalizedValues.length;
    const points = normalizedValues.map((val, index) => {
        const x = padding + (numPoints > 1 ? (index / (numPoints - 1)) * chartWidth : chartWidth / 2);
        const y = padding + chartHeight - (val * chartHeight);
        return { x, y, isLast: index === numPoints - 1 };
    });
    
    // Path için pathData oluştur
    let pathData = '';
    if (numPoints === 1) {
        // Tek nokta için yatay çizgi çiz
        const point = points[0];
        pathData = `M ${padding} ${point.y} L ${width - padding} ${point.y}`;
    } else {
        pathData = points.map((point, index) => {
            return index === 0 ? `M ${point.x} ${point.y}` : `L ${point.x} ${point.y}`;
        }).join(' ');
    }
    
    // Son nokta koordinatları
    const lastPoint = points[points.length - 1];
    
    // Tüm noktalar için küçük circle'lar oluştur (son nokta hariç)
    const pointCircles = points.slice(0, -1).map((point, index) => {
        // Her nokta için küçük circle
        return `<circle cx="${point.x}" cy="${point.y}" r="1.2" fill="#10b981" stroke="#34d399" stroke-width="0.3" opacity="0.7"/>`;
    }).join('');
    
    return `
        <svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" style="display: block;">
            <path d="${pathData}" 
                  stroke="#10b981" 
                  stroke-width="1.5" 
                  fill="none" 
                  stroke-linecap="round" 
                  stroke-linejoin="round"/>
            <!-- Küçük noktalar (son nokta hariç) - path'ten sonra render et ki üstte görünsün -->
            ${pointCircles || ''}
            <!-- Pulse glow ring (sadece son nokta için) -->
            <circle cx="${lastPoint.x}" cy="${lastPoint.y}" r="3.5" fill="rgba(16, 185, 129, 0.4)" opacity="0.6">
                <animate attributeName="r" values="3.5;5.5;3.5" dur="2s" repeatCount="indefinite" calcMode="spline" keySplines="0.4 0 0.2 1; 0.4 0 0.2 1"/>
                <animate attributeName="opacity" values="0.6;0.1;0.6" dur="2s" repeatCount="indefinite" calcMode="spline" keySplines="0.4 0 0.2 1; 0.4 0 0.2 1"/>
            </circle>
            <!-- Son nokta (en belirgin) - en üstte -->
            <circle cx="${lastPoint.x}" cy="${lastPoint.y}" r="2.5" fill="#34d399" stroke="#10b981" stroke-width="1" opacity="0.9"/>
            <circle cx="${lastPoint.x}" cy="${lastPoint.y}" r="1.5" fill="#6ee7b7" opacity="1"/>
        </svg>
    `;
}

// Tarihi YYYYMMDD formatına çevir (DD/MM/YYYY veya Date object'den)
function formatDateForSanalganyan(dateString) {
    // Her zaman bugünün tarihini kullan (daha güvenilir)
    const today = new Date();
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, '0');
    const day = String(today.getDate()).padStart(2, '0');
    return `${year}${month}${day}`;
}

// Sanalganyan at detay URL'si oluştur
function getSanalganyanAtUrl(hipodrom, kosuNo, atAdi, tarih = null) {
    const formattedDate = formatDateForSanalganyan(tarih);
    const encodedAtAdi = encodeURIComponent(atAdi);
    return `https://www.sanalganyan.com/at-detay?tarih=${formattedDate}&hipodrom=${hipodrom}&kosu=${kosuNo}&at=${encodedAtAdi}`;
}

// Sanalganyan sonuçlar URL'si oluştur (DD/MM/YYYY formatından YYYYMMDD'ye çevir)
function getSanalganyanSonuclarUrl(hipodrom, kosuNo, tarihStr) {
    let formattedDate = formatDateForSanalganyan(null); // Default: bugünün tarihi
    
    // Eğer tarih string'i varsa, DD/MM/YYYY formatından YYYYMMDD'ye çevir
    if (tarihStr && typeof tarihStr === 'string') {
        const parts = tarihStr.split('/');
        if (parts.length === 3) {
            const day = parts[0].padStart(2, '0');
            const month = parts[1].padStart(2, '0');
            const year = parts[2];
            formattedDate = `${year}${month}${day}`;
        }
    }
    
    return `https://www.sanalganyan.com/sonuclar?tarih=${formattedDate}&hipodrom=${hipodrom.toUpperCase()}&kosu=${kosuNo}`;
}

// Main Page Functions
async function loadHipodromlar(skipAutoSelect = false) {
    const tabsContainer = document.getElementById('tabsContainer');
    const tabsLoading = document.getElementById('tabsLoading');
    
    try {
        const response = await fetch(`${API_BASE}/api/hipodromlar`);
        const hipodromlar = await response.json();
        
        tabsLoading.style.display = 'none';
        
        // Sadece mevcut hipodromları filtrele (API'den zaten sıralı geliyor - yakında yarış olanlar başta)
        const availableHipodromlar = hipodromlar.filter(h => h.var);
        
        if (availableHipodromlar.length === 0) {
            tabsContainer.innerHTML = '<div style="text-align: center; padding: 2rem 0;"><p style="color: var(--text-light);">Henüz hiç hipodrom bulunmuyor.</p></div>';
            return;
        }
        
        // Tabs oluştur - Sanalganyan stili (API'den gelen sıralama korunuyor - yakında yarış olanlar başta)
        const tabsList = document.getElementById('tabsList');
        if (!tabsList) {
            console.error('❌ tabsList bulunamadı');
            return;
        }
        const tabsHTML = `
            ${availableHipodromlar.map((hipodrom, index) => {
                const formattedName = formatCityName(hipodrom.adi);
                return `
                    <button class="tab-button ${index === 0 ? 'active' : ''}" 
                            data-hipodrom="${hipodrom.adi}">
                    ${hipodrom.has_race_soon ? '<span class="fire-emoji">🔥</span> ' : ''}${formattedName}
                    </button>
            `;
            }).join('')}
        `;
        
        tabsList.innerHTML = tabsHTML;
        
        // Tab button event listeners
        const tabButtons = tabsList.querySelectorAll('button');
        tabButtons.forEach(button => {
            button.addEventListener('click', async () => {
                // Remove active styling from all tabs
                tabButtons.forEach(btn => {
                    btn.classList.remove('active');
                });
                // Add active styling to clicked tab
                button.classList.add('active');
                
                const hipodrom = button.dataset.hipodrom;
                // Şehir değiştirildiğinde her zaman AI Tahminler tab'ını açmak için
                // autoSelectingRace ve preservingTab flag'lerini sıfırla
                window.autoSelectingRace = false;
                window.preservingTab = false;
                await loadTahminler(hipodrom, false, false);
                
                // Yeni hipodrom seçildiğinde auto-refresh'i güncelle
                startAutoRefresh(hipodrom);
            });
        });
        
        // Sıradaki koşuyu bul ve default seç (sadece ilk yüklemede)
        if (availableHipodromlar.length > 0 && !skipAutoSelect) {
            findAndSelectNextRace(availableHipodromlar);
        }
        
    } catch (error) {
        console.error('Hipodromlar yüklenirken hata:', error);
        tabsLoading.style.display = 'none';
        tabsContainer.innerHTML = '<div style="text-align: center; padding: 2rem 0;"><p style="color: #dc2626; font-weight: 500;">Hipodromlar yüklenirken bir hata oluştu.</p></div>';
    }
}

// Sıradaki koşuyu bul ve default seç
async function findAndSelectNextRace(availableHipodromlar) {
    try {
        const now = new Date();
        const currentHour = now.getHours();
        const currentMinute = now.getMinutes();
        const currentTotalMinutes = currentHour * 60 + currentMinute;
        
        let nextRace = null;
        let nextRaceTime = null;
        let nextRaceHipodrom = null;
        
        // Tüm şehirler için koşuları kontrol et
        for (const hipodrom of availableHipodromlar) {
            try {
                const response = await fetch(`${API_BASE}/api/tahminler/${hipodrom.adi}`);
                const data = await response.json();
                
                if (data.kosular && data.kosular.length > 0) {
                    for (const kosu of data.kosular) {
                        // Bitmiş koşuları atla
                        if (kosu.is_finished) {
                            continue;
                        }
                        
                        // Saat bilgisini parse et
                        if (kosu.saat) {
                            try {
                                const [raceHour, raceMinute] = kosu.saat.split(':').map(Number);
                                const raceTotalMinutes = raceHour * 60 + raceMinute;
                                
                                // Geçmiş saatleri atla (bugünkü yarışlar için)
                                if (raceTotalMinutes < currentTotalMinutes) {
                                    continue;
                                }
                                
                                // En yakın koşuyu bul
                                if (!nextRace || raceTotalMinutes < nextRaceTime) {
                                    nextRace = kosu;
                                    nextRaceTime = raceTotalMinutes;
                                    nextRaceHipodrom = hipodrom.adi;
                                }
                            } catch (e) {
                                // Saat parse hatası - atla
                                continue;
                            }
                        }
                    }
                }
            } catch (error) {
                console.error(`❌ ${hipodrom.adi} için koşular yüklenirken hata:`, error);
                continue;
            }
        }
        
        // İlk açılışta her zaman AI Tahminler tab'ını aç
        window.autoSelectingRace = true; // Otomatik seçim yapıldığını işaretle
        
        if (nextRace && nextRaceHipodrom) {
            console.log(`✅ Sıradaki koşu bulundu: ${nextRaceHipodrom} - ${nextRace.kosu_no}. Koşu (${nextRace.saat})`);
            
            // Şehir tab'ini seç
            const cityTab = document.querySelector(`button[data-hipodrom="${nextRaceHipodrom}"]`);
            if (cityTab) {
                // Tab'ı aktif yap
                document.querySelectorAll('#tabsList .tab-button').forEach(btn => {
                    btn.classList.remove('active');
                });
                cityTab.classList.add('active');
            }
            
            // Tahminleri yükle - AI Tahminler tab'ı otomatik açılacak
            await loadTahminler(nextRaceHipodrom);
            
            // AI Tahminler tab'ını aç (biraz gecikme ile - DOM hazır olmalı)
            setTimeout(() => {
                const tahminlerTab = document.querySelector(`#kosuTabsList .tab-button[data-tab-type="tahminler"]`);
                if (tahminlerTab) {
                    // Tüm koşu tablarını pasif yap
                    document.querySelectorAll('#kosuTabsList .tab-button').forEach(btn => {
                        btn.classList.remove('active');
                    });
                    tahminlerTab.classList.add('active');
                    // Tab'a tıkla - event listener showTahminler'i çağıracak
                    tahminlerTab.click();
                }
                window.autoSelectingRace = false; // İşaretleme tamamlandı
            }, 300);
            
            startAutoRefresh(nextRaceHipodrom);
        } else {
            // Tüm koşular tamamlandıysa ilk şehirde AI Tahminler'i aç
            console.log('ℹ️ Sıradaki koşu bulunamadı, ilk şehirde AI Tahminler açılıyor');
            const firstHipodrom = availableHipodromlar[0].adi;
            
            // İlk şehir tab'ini seç
            const firstCityTab = document.querySelector(`button[data-hipodrom="${firstHipodrom}"]`);
            if (firstCityTab) {
                document.querySelectorAll('#tabsList .tab-button').forEach(btn => {
                    btn.classList.remove('active');
                });
                firstCityTab.classList.add('active');
            }
            
            await loadTahminler(firstHipodrom, false, false);
            
            // AI Tahminler tab'ını aç
            setTimeout(() => {
                const tahminlerTab = document.querySelector(`#kosuTabsList .tab-button[data-tab-type="tahminler"]`);
                if (tahminlerTab) {
                    tahminlerTab.classList.add('active');
                    tahminlerTab.click();
                }
                window.autoSelectingRace = false; // İşaretleme tamamlandı
            }, 300);
            
            startAutoRefresh(firstHipodrom);
        }
    } catch (error) {
        console.error('❌ Sıradaki koşu bulunurken hata:', error);
        // Hata durumunda ilk şehri seç
        const firstHipodrom = availableHipodromlar[0].adi;
        loadTahminler(firstHipodrom);
        startAutoRefresh(firstHipodrom);
        window.autoSelectingRace = false; // İşaretleme tamamlandı
    }
}

// Tamamlanan koşular carousel widget'ını yükle
async function loadCompletedRacesCarousel() {
    const carouselContainer = document.getElementById('completedRacesCarousel');
    const carouselTrack = document.getElementById('carouselTrack');
    
    if (!carouselContainer || !carouselTrack) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/api/completed-races`);
        const data = await response.json();
        
        if (!data.completed_races || data.completed_races.length === 0) {
            console.log('ℹ️ Tamamlanan koşu bulunamadı veya ilk 3 tahminimizde kazanan yok');
            // Widget'ı gizle ama console'da bilgi ver
            carouselContainer.style.display = 'none';
            // Debug: Widget'ın HTML'de olduğunu kontrol et
            console.log('🔍 Widget HTML elementi:', carouselContainer);
            return;
        }
        
        console.log(`✅ ${data.completed_races.length} tamamlanan koşu bulundu`);
        carouselContainer.style.display = 'block';
        
        // Her koşu için kart oluştur
        const races = data.completed_races;
        const cityNameMap = {
            'ISTANBUL': 'İstanbul',
            'ELAZIG': 'Elazığ',
            'ANKARA': 'Ankara',
            'IZMIR': 'İzmir',
            'BURSA': 'Bursa',
            'KOCAELI': 'Kocaeli',
            'ADANA': 'Adana',
            'SANLIURFA': 'Şanlıurfa',
            'DBAKIR': 'Diyarbakır',
            'BELMONTBIG': 'Belmont Big',
            'SELANGOR': 'Selangor'
        };
        
        const itemsHTML = races.map((race, index) => {
            const cityName = cityNameMap[race.hipodrom] || race.hipodrom;
            
            // Koşu bilgilerini badge'ler halinde oluştur (Anlık Yapay Zeka Tahminleri formatında)
            const raceInfoBadges = [];
            
            // Şehir badge'i (en başta)
            raceInfoBadges.push(`<span class="kosu-info-badge city-badge">${cityName}</span>`);
            
            // Koşu numarası
            raceInfoBadges.push(`<span class="kosu-info-badge race-number">${race.kosu_no}. Koşu</span>`);
            
            // Saat
            if (race.kosu_saat) {
                raceInfoBadges.push(`<span class="kosu-info-badge time">${race.kosu_saat}</span>`);
            }
            
            // Mesafe ve Pist türü birleşik (2100m Çim)
            if (race.kosu_mesafe || race.pist_tur) {
                const mesafeStr = race.kosu_mesafe ? `${race.kosu_mesafe}m` : '';
                const pistTurStr = race.pist_tur ? formatPistTur(race.pist_tur) : '';
                const combinedStr = [mesafeStr, pistTurStr].filter(Boolean).join(' ');
                if (combinedStr) {
                    // Pist türüne göre class ekle
                    let pistClass = 'distance';
                    if (race.pist_tur) {
                        const pistTurLower = race.pist_tur.toLowerCase();
                        if (pistTurLower.includes('çim') || pistTurLower.includes('cim')) {
                            pistClass = 'distance track-cim';
                        } else if (pistTurLower.includes('kum')) {
                            pistClass = 'distance track-kum';
                        } else if (pistTurLower.includes('sentetik')) {
                            pistClass = 'distance track-sentetik';
                        }
                    }
                    raceInfoBadges.push(`<span class="kosu-info-badge ${pistClass}">${combinedStr}</span>`);
                }
            }
            
            // Sınıf (SATIŞ 3 gibi) - en sonda
            const sinifText = race.kosu_sinif || race.cins_detay || '';
            if (sinifText) {
                raceInfoBadges.push(`<span class="kosu-info-badge class">${sinifText}</span>`);
            }
            
            // At adından emojiyi kaldır
            let atAdi = race.at_adi || '';
            atAdi = atAdi.replace(/[⭐📈📉🔥]/g, '').trim();
            
            return `
                <div class="carousel-item-wrapper">
                    <div class="carousel-race-group">
                        <div class="carousel-race-header">
                            <div class="race-title">
                                <div class="kosu-title">
                                    ${raceInfoBadges.join('')}
                                </div>
                            </div>
                        </div>
                        <div class="race-horses">
                            <a href="#" class="best-bet-card-link">
                                <div class="best-bet-card finished winner">
                                    <div class="best-bet-content">
                                        <div class="best-bet-info">
                                            <div class="best-bet-header-row">
                                                <div class="best-bet-number">1</div>
                                                <div class="best-bet-name">
                                                    ${(race.at_no !== null && race.at_no !== undefined) ? `${race.at_no} - ` : ''}${atAdi}${race.jokey_adi ? `<span class="jokey-name-light"> | ${race.jokey_adi}</span>` : ''}
                                                </div>
                                            </div>
                                        </div>
                                        <div class="best-bet-values">
                                            <div class="score-box">
                                                ${race.combined_score !== null && race.combined_score !== undefined ? `
                                                <div class="value-item">
                                                    <div class="value-label">Olasılık Skoru</div>
                                                    <div class="score-main">${(race.combined_score * 100).toFixed(1)}%</div>
                                                </div>
                                                ` : ''}
                                                ${race.ganyan !== null && race.ganyan !== undefined && !isNaN(parseFloat(race.ganyan)) ? `
                                                <div class="value-item">
                                                    <div class="value-label">Ganyan</div>
                                                    <div class="score-main ganyan">${parseFloat(race.ganyan).toFixed(2)}</div>
                                                </div>
                                                ` : ''}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </a>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
        
        // Carousel için items'ı ekle (başlığı ve toggle butonunu koruyarak)
        const widgetContent = carouselTrack.querySelector('.widget-content');
        if (widgetContent) {
            widgetContent.innerHTML = itemsHTML;
        } else {
            // Eğer widget-content yoksa, başlık ve toggle butonu ile birlikte oluştur
            const titleWrapper = carouselTrack.querySelector('.section-title-wrapper');
            if (titleWrapper) {
                // Başlık zaten var, sadece içeriği ekle
                const contentDiv = document.createElement('div');
                contentDiv.className = 'widget-content';
                contentDiv.id = 'widgetContent';
                contentDiv.innerHTML = itemsHTML;
                carouselTrack.appendChild(contentDiv);
            } else {
                // Başlık ve toggle butonu yok, hepsini oluştur
                carouselTrack.innerHTML = `
                    <div class="section-title-wrapper">
                        <h2 class="section-title">
                            <span class="confetti-emoji">🎉</span>
                            Son Kazanan Tahminler
                        </h2>
                        <button class="toggle-widget-btn" id="toggleWidgetBtn" aria-label="Aç/Kapat">
                            <svg class="toggle-icon" width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <path d="M5 7.5L10 12.5L15 7.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                            </svg>
                        </button>
                    </div>
                    <div class="widget-content" id="widgetContent">
                        ${itemsHTML}
                    </div>
                `;
            }
        }
        
        // Toggle butonu event listener'ı ekle
        setupWidgetToggle();
        
    } catch (error) {
        console.error('❌ Carousel widget yüklenirken hata:', error);
        console.error('❌ Hata detayı:', error.stack);
        if (carouselContainer) {
            carouselContainer.style.display = 'none';
        }
    }
}

// Widget toggle fonksiyonu
let widgetToggleHandler = null; // Event handler referansını sakla

function setupWidgetToggle() {
    const toggleBtn = document.getElementById('toggleWidgetBtn');
    const widgetContent = document.getElementById('widgetContent');
    
    if (!toggleBtn || !widgetContent) {
        return;
    }
    
    // Eğer önceki event listener varsa, kaldır
    if (widgetToggleHandler) {
        toggleBtn.removeEventListener('click', widgetToggleHandler);
        widgetToggleHandler = null;
    }
    
    // LocalStorage'dan durumu oku (varsayılan: açık)
    const isCollapsed = localStorage.getItem('completedRacesWidgetCollapsed') === 'true';
    
    if (isCollapsed) {
        widgetContent.classList.add('collapsed');
        toggleBtn.classList.add('collapsed');
    } else {
        widgetContent.classList.remove('collapsed');
        toggleBtn.classList.remove('collapsed');
    }
    
    // Yeni event handler oluştur
    widgetToggleHandler = () => {
        const isCollapsed = widgetContent.classList.contains('collapsed');
        
        if (isCollapsed) {
            widgetContent.classList.remove('collapsed');
            toggleBtn.classList.remove('collapsed');
            localStorage.setItem('completedRacesWidgetCollapsed', 'false');
        } else {
            widgetContent.classList.add('collapsed');
            toggleBtn.classList.add('collapsed');
            localStorage.setItem('completedRacesWidgetCollapsed', 'true');
        }
    };
    
    // Event listener'ı ekle
    toggleBtn.addEventListener('click', widgetToggleHandler);
}

// Şehir ismini formatla (ISTANBUL -> İstanbul, ELAZIG -> Elazığ)
function formatCityName(hipodrom) {
    if (!hipodrom) return '';
    
    // Özel durumlar
    const specialCases = {
        'ISTANBUL': 'İstanbul',
        'ELAZIG': 'Elazığ',
        'ANKARA': 'Ankara',
        'IZMIR': 'İzmir',
        'BURSA': 'Bursa',
        'KOCAELI': 'Kocaeli',
        'ADANA': 'Adana',
        'SANLIURFA': 'Şanlıurfa',
        'DBAKIR': 'Diyarbakır',
        'BELMONTBIG': 'Belmont Big',
        'SELANGOR': 'Selangor'
    };
    
    if (specialCases[hipodrom.toUpperCase()]) {
        return specialCases[hipodrom.toUpperCase()];
    }
    
    // Genel durum: İlk harfi büyük, geri kalanını küçük yap
    return hipodrom.charAt(0) + hipodrom.slice(1).toLowerCase();
}

function formatPistTur(pistTur) {
    if (!pistTur) return '';
    const tur = pistTur.toString().toLowerCase();
    if (tur === 'cim' || tur === 'çim') {
        return 'Çim';
    } else if (tur === 'kum') {
        return 'Kum';
    } else if (tur === 'sentetik') {
        return 'Sentetik';
    }
    // Fallback: ilk harfi büyük yap
    return tur.charAt(0).toUpperCase() + tur.slice(1);
}

// Cins detay açıklaması getir
function getCinsDetayAciklama(cinsDetay) {
    if (!cinsDetay) return '';
    
    const detay = cinsDetay.toString().toUpperCase();
    const originalText = cinsDetay.toString();
    
    // G1 (Grup 1)
    if (detay.includes('G1') || detay.includes('GRUP 1')) {
        return '• En prestijli yarışlardır (örneğin Gazi Koşusu, Cumhurbaşkanlığı Koşusu)<br/>• Ülke veya uluslararası düzeyde en iyi safkanlar katılır<br/>• Yüksek ödül, rekor performanslar, damızlık değeri açısından zirvededir';
    }
    
    // G2 (Grup 2)
    if (detay.includes('G2') || detay.includes('GRUP 2')) {
        return '• G1 kadar elit olmasa da, üst seviye safkanların yarıştığı prestijli koşulardır<br/>• Genellikle G1\'e hazırlık veya seçme niteliği taşır';
    }
    
    // G3 (Grup 3)
    if (detay.includes('G3') || detay.includes('GRUP 3')) {
        return '• Kaliteli ama bir seviye daha alt gruptaki safkanlar koşar<br/>• Genelde G2\'ye hazırlık koşusudur';
    }
    
    // KV (Kısa Vadeli)
    if (detay.includes('KV')) {
        return '• KV-9, KV-8, KV-7 … KV-1 şeklinde seviye düşer<br/>• Rakam küçüldükçe yarışın seviyesi azalır (KV-9 en üst KV koşusudur)<br/>• Belirli handikap puanı ve başarı düzeyine sahip atlara açıktır';
    }
    
    // Handikap
    if (detay.includes('HANDİKAP') || detay.includes('HANDIKAP')) {
        return '• Atların form, kilo, başarı farklarını dengelemek için kilolar farklı verilir<br/>• "Handikap 16", "Handikap 15", "Handikap 14" gibi derecelendirilir<br/>• Rakam büyüdükçe kalite artar (Handikap 17 > Handikap 14)<br/>• Genellikle sürprize açık, kalabalık koşulardır';
    }
    
    // Şartlı
    if (detay.includes('ŞARTLI') || detay.includes('SARTLI')) {
        return '• Atların kariyer basamaklarını gösterir: Şartlı 1 en düşük, Şartlı 5 en yüksek seviyedir<br/>• Yeni başlayan atlar alt şartlardan başlayarak yükselir<br/>• "Şartlı 1" = İlk yarış, "Şartlı 5" = Tecrübeli ama üst seviye olmayan safkanlar';
    }
    
    // Satış
    if (detay.includes('SATIŞ') || detay.includes('SATIS')) {
        return '• Atların satışa çıktığı yarışlardır<br/>• Performans seviyesi düşük ya da el değiştirme potansiyeli olan safkanlar koşar<br/>• Prestijden çok ekonomik amaç taşır';
    }
    
    // Maiden
    if (detay.includes('MAİDEN') || detay.includes('MAIDEN')) {
        return '• Henüz hiç kazanamamış atların yarıştığı en alt seviye koşudur<br/>• Genellikle genç safkanların kariyer başlangıcıdır';
    }
    
    return '';
}

// Predictions Page Functions
async function loadTahminler(hipodrom, preserveScroll = false, skipAutoSelect = false) {
    // Koşu tablarını gizle (yeni hipodrom yüklenirken)
    const kosuTabsContainer = document.getElementById('kosuTabsContainer');
    if (kosuTabsContainer) {
        kosuTabsContainer.style.display = 'none';
    }
    const loading = document.getElementById('contentLoading');
    const content = document.getElementById('tahminlerContent');
    const error = document.getElementById('errorMessage');
    
    if (!hipodrom && window.currentHipodrom) {
        hipodrom = window.currentHipodrom;
    }
    
    if (!hipodrom) {
        console.error('Hipodrom tanımlı değil!');
        loading.style.display = 'none';
        error.style.display = 'block';
        error.innerHTML = '<p style="color: #991b1b; font-weight: 500;">Hipodrom bilgisi bulunamadı.</p>';
        return;
    }
    
    window.currentHipodrom = hipodrom;
    
    // Scroll pozisyonunu kaydet (eğer preserveScroll true ise)
    let scrollPosition = 0;
    if (preserveScroll) {
        scrollPosition = window.pageYOffset || document.documentElement.scrollTop || document.body.scrollTop || 0;
        console.log('Scroll pozisyonu kaydedildi:', scrollPosition);
    }
    
    // Loading spinner'ı sadece ilk yüklemede göster, otomatik yenilemede gösterme
    if (!preserveScroll) {
        loading.style.display = 'flex';
        content.style.display = 'none';
    } else {
        // Otomatik yenilemede içeriği görünür tut (hiçbir şey kaybolmasın)
        loading.style.display = 'none';
        if (content) {
            content.style.display = 'block';
            // Mevcut içeriği koru (görsel kayma olmasın)
            content.style.transition = 'opacity 0.2s';
        }
    }
    error.style.display = 'none';
    
    try {
        const url = `${API_BASE}/api/tahminler/${hipodrom}`;
        console.log('API çağrısı yapılıyor:', url);
        
        const response = await fetch(url);
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error('API hatası:', response.status, errorText);
            
            // Loading'i gizle ve hata mesajı göster
            loading.style.display = 'none';
            error.style.display = 'block';
            
            if (response.status === 404) {
                error.innerHTML = `
                    <p style="color: #991b1b; font-weight: 500; margin-bottom: 1rem;">
                        ⏳ ${hipodrom} için tahminler henüz hazırlanıyor...
                    </p>
                    <p style="color: var(--text-light); font-size: 0.9rem;">
                        Veriler güncelleniyor, lütfen birkaç dakika sonra tekrar deneyin.
                    </p>
                `;
            } else {
                error.innerHTML = `
                    <p style="color: #991b1b; font-weight: 500;">
                        ❌ Hata: ${response.status}
                    </p>
                    <p style="color: var(--text-light); font-size: 0.9rem;">
                        ${errorText || 'Bilinmeyen bir hata oluştu'}
                    </p>
                `;
            }
            return;
        }
        
        const data = await response.json();
        console.log('API yanıtı alındı:', data);
        console.log('Best bets:', data.best_bets);
        console.log('Best bets sayısı:', data.best_bets ? data.best_bets.length : 0);
        
        // Veriyi global olarak sakla (refreshAllData için)
        window.currentTahminlerData = data;
        
        // Info section - kaldırıldı
        
        // Koşu tablarını oluştur
        try {
            const kosuTabsList = document.getElementById('kosuTabsList');
            
            console.log('📊 Koşular verisi:', data.kosular);
            console.log('📊 Koşu sayısı:', data.kosular ? data.kosular.length : 0);
            
            if (data.kosular && data.kosular.length > 0 && kosuTabsList) {
                // AI ikonu SVG (üst üste iki 4 köşeli yıldız - sparkles)
                const aiIconSVG = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="display: inline-block; vertical-align: middle; margin-right: 0.25rem;">
                    <!-- Üst yıldız -->
                    <path d="M12 2L13.5 8.5L20 10L13.5 11.5L12 18L10.5 11.5L4 10L10.5 8.5L12 2Z" fill="currentColor" opacity="0.9"/>
                    <!-- Alt yıldız (biraz daha küçük ve kaydırılmış) -->
                    <path d="M12 6L12.75 9.25L16 10L12.75 10.75L12 14L11.25 10.75L8 10L11.25 9.25L12 6Z" fill="currentColor" opacity="0.7"/>
                </svg>`;
                
                // Canlı badge (yanıp sönen)
                const canliBadge = `<span class="canli-badge">Canlı</span>`;
                
                // Koşu tablarını oluştur (AI Tahminler en başta, sonra 1. Koşu, 2. Koşu, ...)
                const kosuTabsHTML = `
                    <button class="tab-button active" 
                            data-tab-type="tahminler">
                        ${aiIconSVG}AI Tahminler ${canliBadge}
                    </button>
                ` + data.kosular.map((kosu, index) => `
                    <button class="tab-button" 
                            data-kosu-no="${kosu.kosu_no}"
                            data-tab-type="kosu">
                        ${kosu.kosu_no}. Koşu
                    </button>
                `).join('');
                
                kosuTabsList.innerHTML = kosuTabsHTML;
                const kosuTabsContainer = document.getElementById('kosuTabsContainer');
                if (kosuTabsContainer) {
                    kosuTabsContainer.style.display = 'block';
                }
                
                // Koşu tab event listener'ları
                kosuTabsList.querySelectorAll('.tab-button').forEach(button => {
                    button.addEventListener('click', (e) => {
                        // Eğer swipe yapılıyorsa click'i ignore et
                        if (button.dataset.swiping === 'true') {
                            return;
                        }
                        
                        // Tüm tabları pasif yap
                        kosuTabsList.querySelectorAll('.tab-button').forEach(btn => {
                            btn.classList.remove('active');
                        });
                        // Tıklanan tabı aktif yap
                        button.classList.add('active');
                        
                        // Mobilde aktif tab'ı görünür alana getir
                        if (window.innerWidth <= 768) {
                            button.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
                        }
                        
                        const tabType = button.getAttribute('data-tab-type');
                        if (tabType === 'kosu') {
                            const kosuNo = parseInt(button.getAttribute('data-kosu-no'));
                            showKosu(kosuNo, data);
                        } else if (tabType === 'tahminler') {
                            showTahminler(data);
                        }
                    });
                });
                
                // Mobilde swipe desteği ekle
                let touchStartX = 0;
                let touchStartY = 0;
                let isScrolling = false;
                
                kosuTabsList.addEventListener('touchstart', (e) => {
                    touchStartX = e.touches[0].clientX;
                    touchStartY = e.touches[0].clientY;
                    isScrolling = false;
                }, { passive: true });
                
                kosuTabsList.addEventListener('touchmove', (e) => {
                    if (!touchStartX || !touchStartY) return;
                    
                    const touchEndX = e.touches[0].clientX;
                    const touchEndY = e.touches[0].clientY;
                    const diffX = touchStartX - touchEndX;
                    const diffY = touchStartY - touchEndY;
                    
                    // Yatay scroll mu dikey scroll mu?
                    if (Math.abs(diffX) > Math.abs(diffY)) {
                        // Yatay scroll - swipe yapılıyor
                        isScrolling = true;
                        // Tüm tabları işaretle
                        kosuTabsList.querySelectorAll('.tab-button').forEach(btn => {
                            btn.dataset.swiping = 'true';
                        });
                    }
                }, { passive: true });
                
                kosuTabsList.addEventListener('touchend', () => {
                    // Swipe bitince işareti kaldır
                    setTimeout(() => {
                        kosuTabsList.querySelectorAll('.tab-button').forEach(btn => {
                            btn.dataset.swiping = 'false';
                        });
                    }, 100);
                    touchStartX = 0;
                    touchStartY = 0;
                    isScrolling = false;
                }, { passive: true });
                
                // İlk olarak "AI Tahminler" tab'ını göster (varsayılan)
                // Eğer findAndSelectNextRace çağrılmadıysa ve tab koruma modunda değilsek ve skipAutoSelect false ise
                if (!window.autoSelectingRace && !window.preservingTab && !skipAutoSelect) {
                    // AI Tahminler tab'ını aktif yap ve göster
                    const tahminlerTab = document.querySelector(`#kosuTabsList .tab-button[data-tab-type="tahminler"]`);
                    if (tahminlerTab) {
                        // Tüm tab'lardan active class'ını kaldır
                        document.querySelectorAll('#kosuTabsList .tab-button').forEach(tab => tab.classList.remove('active'));
                        // AI Tahminler tab'ını aktif yap
                        tahminlerTab.classList.add('active');
                        // showTahminler fonksiyonunu çağır (DOM hazır olmalı)
                        // Fonksiyon tanımlanmadan önce çağrılabilir, bu yüzden biraz gecikme ile
                        setTimeout(() => {
                            if (typeof showTahminler === 'function') {
                                showTahminler(data);
                            } else {
                                // Eğer fonksiyon henüz tanımlanmamışsa, biraz daha bekle
                                setTimeout(() => {
                                    if (typeof showTahminler === 'function') {
                                        showTahminler(data);
                                    }
                                }, 100);
                            }
                        }, 50);
                    }
                }
            } else {
                const kosuTabsContainer = document.getElementById('kosuTabsContainer');
                if (kosuTabsContainer) {
                    kosuTabsContainer.style.display = 'none';
                }
            }
        } catch (tabError) {
            console.error('❌ Koşu tabları oluşturulurken hata:', tabError);
            // Hata olsa bile devam et
        }
        
        // Anlık Yapay Zeka Tahminleri bölümünü göster
        const bestBetsSection = document.getElementById('bestBetsSection');
        const bestBetsList = document.getElementById('bestBetsList');
        const bestBetsTabs = document.getElementById('bestBetsTabs');
        
        // Koşu gösterme fonksiyonu
        function showKosu(kosuNo, data) {
            console.log('🏁 Koşu gösteriliyor:', kosuNo);
            const kosu = data.kosular.find(k => k.kosu_no === kosuNo);
            if (!kosu) {
                console.error('❌ Koşu bulunamadı:', kosuNo);
                return;
            }
            
            // Koşu tablarını görünür tut
            const kosuTabsContainer = document.getElementById('kosuTabsContainer');
            if (kosuTabsContainer) {
                kosuTabsContainer.style.display = 'block';
            }
            
        const kosularSection = document.getElementById('kosularSection');
            
            try {
                // Sadece seçilen koşuyu göster (default: yapay zeka sıralaması)
                kosularSection.innerHTML = renderKosu(kosu, hipodrom, data.tarih, 'ai');
                kosularSection.style.display = 'block';
                bestBetsSection.style.display = 'none';
                console.log('✅ Koşu başarıyla gösterildi:', kosuNo);
                
                // Sıralama değişikliği için event listener ekle
                attachSortListener(kosuNo, hipodrom, data);
            } catch (error) {
                console.error('❌ Koşu gösterilirken hata:', error);
            }
        }
        
        // Sıralama değişikliği için event listener ekleme fonksiyonu
        function attachSortListener(kosuNo, hipodrom, data) {
            const sortSelect = document.getElementById(`kosu-sort-${kosuNo}`);
            if (sortSelect && data && data.kosular) {
                sortSelect.addEventListener('change', function(e) {
                    const newSortType = e.target.value;
                    const kosuNoForSort = parseInt(e.target.dataset.kosuNo);
                    
                    // Koşuyu bul ve yeniden render et
                    const kosuData = data.kosular.find(k => k.kosu_no === kosuNoForSort);
                    if (kosuData) {
                        const kosuContainer = document.querySelector(`.kosu-kart[data-kosu-no="${kosuNoForSort}"]`);
                        if (kosuContainer) {
                            const newHTML = renderKosu(kosuData, hipodrom, data.tarih, newSortType);
                            const tempDiv = document.createElement('div');
                            tempDiv.innerHTML = newHTML;
                            const newKosuCard = tempDiv.querySelector('.kosu-kart');
                            if (newKosuCard) {
                                kosuContainer.parentNode.replaceChild(newKosuCard, kosuContainer);
                                
                                // Yeni sıralama seçici için event listener ekle (recursive)
                                attachSortListener(kosuNoForSort, hipodrom, data);
                            }
                        }
                    }
                });
            }
        }
        
        // Tahminler gösterme fonksiyonu
        function showTahminler(data) {
            console.log('📊 showTahminler çağrıldı, data:', data);
            const kosularSection = document.getElementById('kosularSection');
            
            // Koşu tablarını görünür tut
            const kosuTabsContainer = document.getElementById('kosuTabsContainer');
            if (kosuTabsContainer) {
                kosuTabsContainer.style.display = 'block';
            }
            
            // bestBetsSection'ı kontrol et ve görünür yap
            const bestBetsSection = document.getElementById('bestBetsSection');
            if (!bestBetsSection) {
                console.error('❌ bestBetsSection bulunamadı!');
                return;
            }
            
            // Sadece Anlık Yapay Zeka Tahminleri'ni göster
            if (kosularSection) {
                kosularSection.style.display = 'none';
            }
            bestBetsSection.style.display = 'block';
            console.log('✅ bestBetsSection görünür yapıldı');
            
            // Anlık Yapay Zeka Tahminleri render işlemi (mevcut kod)
            if (typeof renderBestBetsContent === 'function') {
                renderBestBetsContent(data);
                console.log('✅ renderBestBetsContent çağrıldı');
            } else {
                console.error('❌ renderBestBetsContent fonksiyonu bulunamadı!');
            }
        }
        
        // Sıralama fonksiyonu
        function sortAtlar(atlar, sortType) {
            const atlarCopy = [...atlar];
            
            switch(sortType) {
                case 'at_no':
                    // At no'ya göre sırala (küçükten büyüğe)
                    atlarCopy.sort((a, b) => {
                        const aNo = (a.at_no !== null && a.at_no !== undefined) ? a.at_no : 999;
                        const bNo = (b.at_no !== null && b.at_no !== undefined) ? b.at_no : 999;
                        return aNo - bNo;
                    });
                    break;
                case 'favori':
                    // Favori sırasına göre sırala (AGF sırası)
                    atlarCopy.sort((a, b) => {
                        const aFavori = (a.agf1_sira !== null && a.agf1_sira !== undefined) 
                            ? a.agf1_sira 
                            : (a.agf2_sira !== null && a.agf2_sira !== undefined) 
                                ? a.agf2_sira 
                                : 999;
                        const bFavori = (b.agf1_sira !== null && b.agf1_sira !== undefined) 
                            ? b.agf1_sira 
                            : (b.agf2_sira !== null && b.agf2_sira !== undefined) 
                                ? b.agf2_sira 
                                : 999;
                        return aFavori - bFavori;
                    });
                    break;
                case 'ai':
                default:
                    // Yapay zeka (olasılık) sırasına göre sırala (büyükten küçüğe)
                    atlarCopy.sort((a, b) => {
                        const aOlasilik = a.olasilik || 0;
                        const bOlasilik = b.olasilik || 0;
                        return bOlasilik - aOlasilik;
                    });
                    break;
            }
            
            // Sıra numaralarını güncelle
            atlarCopy.forEach((at, index) => {
                at.sira = index + 1;
            });
            
            return atlarCopy;
        }
        
        // Koşu render fonksiyonu
        function renderKosu(kosu, hipodrom, tarih, sortType = 'ai') {
            if (!kosu || !kosu.atlar || kosu.atlar.length === 0) {
                console.error('❌ Koşu verisi geçersiz:', kosu);
                return '<div class="kosu-kart"><p>Koşu verisi bulunamadı.</p></div>';
            }
            
            const kosu_finished = kosu.is_finished || false;
            const race_winner = kosu.race_winner || null;
            
            // Atları sırala
            const sortedAtlar = sortAtlar(kosu.atlar, sortType);
            
            const atlarHTML = sortedAtlar.map(at => {
                const isTop = at.sira <= 3;
                const isWinner = at.is_winner || false;
                const dereceSonuc = at.derece_sonuc || null;
                
                let detaylarHTML = '';
                if (at.detaylar) {
                    const dets = [];
                    const atJokeyParts = [];
                    if (at.detaylar.jokey_at_kazanma) {
                        atJokeyParts.push(`${at.detaylar.jokey_at_kazanma}x Kazandı`);
                    }
                    if (at.detaylar.jokey_at_tabela) {
                        atJokeyParts.push(`${at.detaylar.jokey_at_tabela}x Tabela`);
                    }
                    if (atJokeyParts.length > 0) {
                        dets.push(`<span class="at-badge green">🏆 At-Jokey: ${atJokeyParts.join(', ')}</span>`);
                    }
                    // Tecrübe - At-Jokey'in hemen sonrasına taşındı
                    if (at.detaylar.badge) {
                        // Format: "1x G1, 1x G3, 2x KV" gibi olacak
                        let badgeText = typeof at.detaylar.badge === 'string' ? at.detaylar.badge : String(at.detaylar.badge);
                        // "1x G1 1x G3 2x KV" gibi ifadeleri "1x G1, 1x G3, 2x KV" yap
                        // Her "x" içeren ifadeyi (1x, 2x, vb.) ve sonrasındaki kelimeyi bir grup olarak al
                        // Örnek: "1x G1" -> bir grup, "1x G3" -> bir grup, "2x KV" -> bir grup
                        // Bu gruplar arasında virgül ekle
                        badgeText = badgeText.replace(/(\d+x\s+\S+)\s+(?=\d+x)/g, '$1, '); // "1x G1 1x G3" -> "1x G1, 1x G3"
                        // Eğer hala boşluklarla ayrılmış başka değerler varsa (G1 G2 gibi), onları da virgülle ayır
                        // Ama sadece "x" içermeyen ifadeler için
                        badgeText = badgeText.replace(/([A-Z]\d+|[A-Z]{2,})\s+(?=[A-Z])/g, '$1, '); // "G1 G2" -> "G1, G2"
                        const tecrubeTooltip = 'Önem sırası:<br/>G1 → G2 → G3 → KV → Diğer Koşu Türleri';
                        dets.push(`<span class="at-badge yellow has-tooltip">🏅 Tecrübe: ${badgeText}<span class="at-badge-tooltip">${tecrubeTooltip}</span></span>`);
                    }
                    if (kosu.mesafe && at.detaylar.mesafe_kazanma) {
                        dets.push(`<span class="at-badge purple">📏 ${kosu.mesafe}m: ${at.detaylar.mesafe_kazanma}x kazandı</span>`);
                    } else if (at.detaylar.mesafe_kazanma) {
                        dets.push(`<span class="at-badge purple">📏 Mesafe: ${at.detaylar.mesafe_kazanma}x kazandı</span>`);
                    }
                    const cityName = formatCityName(hipodrom);
                    if (at.detaylar.hipodrom_kazanma) {
                        dets.push(`<span class="at-badge indigo">🏟️ ${cityName}: ${at.detaylar.hipodrom_kazanma}x kazandı</span>`);
                    }
                    if (at.detaylar.gecti && at.detaylar.gecti.length > 0) {
                        dets.push(`<span class="at-badge red">⚔️ Geçmişte geçti: ${at.detaylar.gecti.join(', ')}</span>`);
                    }
                    detaylarHTML = dets.length > 0 ? `<div class="at-details-label">ÖNE ÇIKANLAR</div><div class="at-details">${dets.join('')}</div>` : '';
                }
                
                let extraInfoHTML = '';
                let winnerBadge = '';
                if (kosu_finished && isWinner) {
                    winnerBadge = '<span class="at-winner-badge">✓ Kazanan</span>';
                } else if (kosu_finished && dereceSonuc !== null) {
                    winnerBadge = `<span class="at-result-badge">Sonuç: ${dereceSonuc}</span>`;
                }
                
                const sanalganyanUrl = getSanalganyanAtUrl(hipodrom, kosu.kosu_no, at.at_adi, tarih);
                
                return `
                    <a href="${sanalganyanUrl}" target="_blank" rel="noopener noreferrer" class="at-kart-link">
                        <div class="at-kart ${kosu_finished ? 'finished' : ''} ${isWinner ? 'winner' : ''}">
                            <div class="at-kart-content">
                                <div class="at-info">
                                    <div class="at-header">
                                        <div class="at-number">${at.sira}</div>
                                        <div class="at-name-row">
                                            <h3 class="at-name">
                                                ${(at.at_no !== null && at.at_no !== undefined) ? `${at.at_no} - ` : ''}${at.at_adi}${at.jokey_adi ? ` <span class="at-jokey">| ${at.jokey_adi}</span>` : ''}
                                            </h3>
                                            ${winnerBadge}
                                        </div>
                                        ${(() => {
                                            const badges = [];
                                            // En iyi derece badge (ganyan'dan önce)
                                            if (at.en_iyi_derece !== null && at.en_iyi_derece !== undefined && at.en_iyi_derece !== '') {
                                                const isFarkliHipodrom = at.en_iyi_derece_farkli_hipodrom === true || at.en_iyi_derece_farkli_hipodrom === 'true' || at.en_iyi_derece_farkli_hipodrom === 1 || at.en_iyi_derece_farkli_hipodrom === '1';
                                                const badgeClass = isFarkliHipodrom ? 'en-iyi-derece farkli-hipodrom' : 'en-iyi-derece';
                                                const tooltipText = isFarkliHipodrom ? 'Farklı hipodromda yapılmıştır.' : '';
                                                const tooltipHTML = tooltipText ? `<span class="at-info-tooltip">${tooltipText}</span>` : '';
                                                const hasTooltipClass = tooltipText ? 'has-tooltip' : '';
                                                badges.push(`<span class="at-info-badge ${badgeClass} ${hasTooltipClass}">En İyi: ${at.en_iyi_derece}${tooltipHTML}</span>`);
                                            }
                                            
                                            // Ganyan badge (ganyan değeri ve grafik birleşik)
                                            if (at.ganyan !== null && at.ganyan !== undefined && at.ganyan !== '') {
                                                const ganyanValue = parseFloat(at.ganyan);
                                                const formattedGanyan = !isNaN(ganyanValue) ? ganyanValue.toFixed(2) : at.ganyan;
                                                const ganyanTooltip = 'Bahis oranıdır; oran düştükçe kazanma ihtimali artar fakat kazancın azalır.';
                                                
                                                // Ganyan grafik SVG'si (varsa)
                                                let chartSVG = '';
                                                let chartTooltip = '';
                                                if (at.son_10_ganyan && Array.isArray(at.son_10_ganyan) && at.son_10_ganyan.length > 0) {
                                                    try {
                                                        const svg = createGanyanChartSVG(at.son_10_ganyan);
                                                        if (svg) {
                                                            chartSVG = svg;
                                                            // Tooltip için ganyan değerlerini formatla (2 ondalık basamak)
                                                            const ganyanValuesStr = at.son_10_ganyan.map(val => {
                                                                const num = parseFloat(val);
                                                                return !isNaN(num) ? num.toFixed(2) : val;
                                                            }).join(', ');
                                                            chartTooltip = `Son 10 Ganyan: ${ganyanValuesStr}`;
                                                        }
                                                    } catch (e) {
                                                        console.error('Ganyan grafik oluşturma hatası:', e, 'Değerler:', at.son_10_ganyan);
                                                    }
                                                }
                                                
                                                // Birleşik badge: Sol tarafta ganyan değeri, sağ tarafta grafik
                                                const badgeContent = chartSVG 
                                                    ? `<span class="ganyan-badge-content"><span class="ganyan-value">Ganyan: ${formattedGanyan}</span><span class="ganyan-chart-wrapper">${chartSVG}</span></span>`
                                                    : `<span class="ganyan-badge-content"><span class="ganyan-value">Ganyan: ${formattedGanyan}</span></span>`;
                                                
                                                // Tooltip: Ganyan açıklaması + grafik tooltip (varsa)
                                                const combinedTooltip = chartTooltip 
                                                    ? `${ganyanTooltip}<br><br>${chartTooltip}`
                                                    : ganyanTooltip;
                                                
                                                badges.push(`<span class="at-info-badge ganyan-combined has-tooltip">${badgeContent}<span class="at-info-tooltip">${combinedTooltip}</span></span>`);
                                            }
                                            
                                            // AGF badge
                                            const agfValue = (at.agf1 !== null && at.agf1 !== undefined && at.agf1 !== '') 
                                                ? at.agf1 
                                                : (at.agf2 !== null && at.agf2 !== undefined && at.agf2 !== '') 
                                                    ? at.agf2 
                                                    : null;
                                            if (agfValue !== null) {
                                                const agfTooltip = 'Oynanan kuponların ne kadarında bu ata oynandığını gösterir.';
                                                badges.push(`<span class="at-info-badge agf has-tooltip">AGF: ${agfValue}%<span class="at-info-tooltip">${agfTooltip}</span></span>`);
                                            }
                                            // Favori sırası badge
                                            const favoriSira = (at.agf1_sira !== null && at.agf1_sira !== undefined && at.agf1_sira !== '') 
                                                ? at.agf1_sira 
                                                : (at.agf2_sira !== null && at.agf2_sira !== undefined && at.agf2_sira !== '') 
                                                    ? at.agf2_sira 
                                                    : null;
                                            if (favoriSira !== null) {
                                                const favoriClass = favoriSira === 1 ? 'favori-sira first' : 'favori-sira';
                                                const favoriTooltip = 'AGF\'ye göre en çok oynanan kaçıncı at olduğunu gösterir.';
                                                badges.push(`<span class="at-info-badge ${favoriClass} has-tooltip">Favori sırası: ${favoriSira}<span class="at-info-tooltip">${favoriTooltip}</span></span>`);
                                            }
                                            
                                            return badges.length > 0 ? `<div class="at-info-badges">${badges.join('')}</div>` : '';
                                        })()}
                                    </div>
                                    ${detaylarHTML}
                                    ${extraInfoHTML}
                                    ${at.son_6_yaris && at.son_6_yaris.length > 0 ? `
                                    <div class="at-son-6-yaris">
                                        <div class="at-son-6-label">Son 5 Yarış:</div>
                                        <div class="at-son-6-list">
                                            ${at.son_6_yaris.map((yaris, index) => {
                                                const bgOpacity = 0.1 - (index * 0.008);
                                                const bgOpacityStyle = `background: rgba(107, 143, 181, ${bgOpacity});`;
                                                const isWinner = yaris.text && yaris.text.includes('Kazandı');
                                                const yarisText = typeof yaris === 'string' ? yaris : yaris.text;
                                                let tooltipContent = '';
                                                if (typeof yaris === 'object' && yaris !== null) {
                                                    const tooltipParts = [];
                                                    if (yaris.tarih) {
                                                        tooltipParts.push(`Tarih: ${yaris.tarih}`);
                                                    }
                                                    const cityName = formatCityName(hipodrom);
                                                    tooltipParts.push(`Şehir: ${cityName}`);
                                                    // Favori sırası: agf1_sira varsa onu, yoksa agf2_sira göster
                                                    const favoriSira = (yaris.agf1_sira !== null && yaris.agf1_sira !== undefined) 
                                                        ? yaris.agf1_sira 
                                                        : (yaris.agf2_sira !== null && yaris.agf2_sira !== undefined) 
                                                            ? yaris.agf2_sira 
                                                            : null;
                                                    if (favoriSira !== null) {
                                                        tooltipParts.push(`Favori Sırası: ${favoriSira}`);
                                                    }
                                                    if (yaris.jokey) {
                                                        tooltipParts.push(`Jokey: ${yaris.jokey}`);
                                                    }
                                                    if (tooltipParts.length > 0) {
                                                        tooltipContent = tooltipParts.join('<br>');
                                                    }
                                                }
                                                let sonuclarUrl = '#';
                                                if (typeof yaris === 'object' && yaris !== null && yaris.kosu_no && yaris.tarih) {
                                                    sonuclarUrl = getSanalganyanSonuclarUrl(hipodrom, yaris.kosu_no, yaris.tarih);
                                                }
                                                return `<a href="${sonuclarUrl}" target="_blank" rel="noopener noreferrer" class="at-son-6-item ${isWinner ? 'winner' : ''}" style="${bgOpacityStyle}" ${tooltipContent ? `data-tooltip="${tooltipContent.replace(/"/g, '&quot;')}"` : ''}>
                                                    ${yarisText}
                                                    ${tooltipContent ? `<span class="at-son-6-tooltip">${tooltipContent}</span>` : ''}
                                                </a>`;
                                            }).join('')}
                                        </div>
                                    </div>
                                    ` : ''}
                                </div>
                                <div class="at-stats">
                                    <div class="at-stat">
                                        <div class="at-stat-label has-tooltip">Olasılık<span class="at-stat-tooltip">Yapay zeka analizine göre koşuyu kazanma ihtimalini gösterir.</span></div>
                                        <div class="at-stat-value">${formatOlasilik(at.olasilik)}</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </a>
                `;
            }).join('');
            
            // Kazanan badge artık kosuInfoBadges içinde (sınıf badge'inin hemen sağında)
            
            // Koşu bilgilerini badge'ler halinde oluştur
            const kosuInfoBadges = [];
            
            // Koşu numarası
            kosuInfoBadges.push(`<span class="kosu-info-badge race-number">${kosu.kosu_no}. Koşu</span>`);
            
            // Saat
            if (kosu.saat) {
                kosuInfoBadges.push(`<span class="kosu-info-badge time">${kosu.saat}</span>`);
            }
            
            // Mesafe ve Pist türü birleşik (2100m Çim)
            if (kosu.mesafe || kosu.pist_tur) {
                const mesafeStr = kosu.mesafe ? `${kosu.mesafe}m` : '';
                const pistTurStr = kosu.pist_tur ? formatPistTur(kosu.pist_tur) : '';
                const combinedStr = [mesafeStr, pistTurStr].filter(Boolean).join(' ');
                if (combinedStr) {
                    // Pist türüne göre class ekle
                    let pistClass = 'distance';
                    if (kosu.pist_tur) {
                        const pistTurLower = kosu.pist_tur.toLowerCase();
                        if (pistTurLower.includes('çim') || pistTurLower.includes('cim')) {
                            pistClass = 'distance track-cim';
                        } else if (pistTurLower.includes('kum')) {
                            pistClass = 'distance track-kum';
                        } else if (pistTurLower.includes('sentetik')) {
                            pistClass = 'distance track-sentetik';
                        }
                    }
                    kosuInfoBadges.push(`<span class="kosu-info-badge ${pistClass}">${combinedStr}</span>`);
                }
            }
            
            // Sınıf (SATIŞ 3 gibi) - en sonda, tooltip ile
            // Önce sinif'e bak, yoksa cins_detay'a bak
            const sinifText = kosu.sinif || kosu.cins_detay || '';
            if (sinifText) {
                // Tooltip için hem sinif hem de cins_detay'a bak
                const tooltipSource = kosu.cins_detay || kosu.sinif || '';
                const aciklama = getCinsDetayAciklama(tooltipSource);
                const tooltipHTML = aciklama ? `<span class="kosu-info-tooltip">${aciklama}</span>` : '';
                const tooltipClass = aciklama ? 'has-tooltip' : '';
                kosuInfoBadges.push(`<span class="kosu-info-badge class ${tooltipClass}">${sinifText}${tooltipHTML}</span>`);
            }
            
            // Yarışı izle badge'i - yarış saatinden itibaren 5 dakika içinde göster
            if (kosu.saat && !kosu_finished) {
                const now = new Date();
                const currentHour = now.getHours();
                const currentMinute = now.getMinutes();
                const currentTotalMinutes = currentHour * 60 + currentMinute;
                
                try {
                    const [raceHour, raceMinute] = kosu.saat.split(':').map(Number);
                    const raceTotalMinutes = raceHour * 60 + raceMinute;
                    
                    // Yarış saatinden sonra ve 5 dakika içindeyse göster
                    const timeDiff = currentTotalMinutes - raceTotalMinutes;
                    if (timeDiff >= 0 && timeDiff <= 5) {
                        const watchUrl = 'https://www.youtube.com/watch?v=g89RQMJtK6E';
                        const playIcon = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="display: inline-block; vertical-align: middle; margin-right: 0.25rem;"><path d="M8 5v14l11-7z" fill="currentColor"/></svg>`;
                        kosuInfoBadges.push(`<a href="${watchUrl}" target="_blank" rel="noopener noreferrer" class="kosu-info-badge watch-live">${playIcon}Yarışı izle</a>`);
                    }
                } catch (e) {
                    // Saat parse hatası - badge gösterilmez
                }
            }
            
            // Kazanan badge'ini sınıf badge'inin hemen sağına ekle
            if (kosu_finished && race_winner) {
                kosuInfoBadges.push(`<span class="kosu-info-badge race-winner">✓ Kazanan: ${race_winner}</span>`);
            }
            
            // Sıralama seçici
            const sortSelectHTML = `
                <div class="kosu-sort-selector">
                    <label for="kosu-sort-${kosu.kosu_no}" class="kosu-sort-label">Sıralama:</label>
                    <select id="kosu-sort-${kosu.kosu_no}" class="kosu-sort-select" data-kosu-no="${kosu.kosu_no}">
                        <option value="ai" ${sortType === 'ai' ? 'selected' : ''}>Yapay zekaya göre</option>
                        <option value="at_no" ${sortType === 'at_no' ? 'selected' : ''}>At no'ya göre</option>
                        <option value="favori" ${sortType === 'favori' ? 'selected' : ''}>Favoriye göre</option>
                    </select>
                </div>
            `;
            
            return `
                <div class="kosu-kart ${kosu_finished ? 'finished' : ''}" data-kosu-no="${kosu.kosu_no}">
                    <div class="kosu-baslik">
                        <div class="kosu-baslik-content">
                            <div class="kosu-title">
                                ${kosuInfoBadges.join('')}
                        </div>
                            <div class="kosu-baslik-right">
                                ${sortSelectHTML}
                    </div>
                        </div>
                    </div>
                    <div class="kosu-atlar-container">
                        ${atlarHTML}
                    </div>
                </div>
            `;
        }
        
        // İlk yüklemede bestBetsSection gizli (sadece showTahminler çağrılmadıysa)
        // showTahminler çağrıldığında bestBetsSection görünür yapılacak, bu yüzden burada gizleme yapmıyoruz
        
        // Anlık Yapay Zeka Tahminleri render fonksiyonu (mevcut renderBestBets fonksiyonunu kullan)
        function renderBestBetsContent(data) {
            // window.currentTahminlerData'ya kaydet
            window.currentTahminlerData = data;
            
            // Mevcut renderBestBets fonksiyonunu çağır
            // Her zaman olasılık skoruna göre sırala (probability)
            if (data.best_bets && data.best_bets.length > 0) {
                const sortedBets = sortBestBets(data.best_bets, 'probability');
                const activeBets = sortedBets.filter(bet => !bet.is_finished);
                const defaultTab = activeBets.length > 0 ? 'active' : 'finished';
                renderBestBets(sortedBets, defaultTab);
            } else {
                // Anlık yapay zeka tahminleri yoksa mesaj göster
                if (bestBetsList) {
                    bestBetsList.innerHTML = `
                        <div class="best-bet-card" style="text-align: center;">
                            <p style="color: var(--text-light);">Henüz ganyan oranları gelmediği için anlık yapay zeka tahminleri hesaplanamıyor.</p>
                            <p style="font-size: 0.875rem; color: var(--text-light); margin-top: 0.5rem;">Ganyan oranları geldiğinde bu bölüm otomatik olarak güncellenecektir.</p>
                        </div>
                    `;
                }
            }
        }
        
        // Sıralama fonksiyonu
        function sortBestBets(bets, sortBy) {
            const sorted = [...bets];
            switch(sortBy) {
                case 'kosu':
                    // Koşu numarasına göre sırala
                    sorted.sort((a, b) => {
                        if (a.kosu_no !== b.kosu_no) {
                            return a.kosu_no - b.kosu_no;
                        }
                        // Aynı koşuda ise, olasılık skoruna göre
                        const aScore = a.combined_score || 0;
                        const bScore = b.combined_score || 0;
                        return bScore - aScore;
                    });
                    break;
                case 'probability':
                    // Olasılık skoruna göre sırala (yüksekten düşüğe)
                    sorted.sort((a, b) => {
                        const aScore = a.combined_score || 0;
                        const bScore = b.combined_score || 0;
                        return bScore - aScore;
                    });
                    break;
                case 'profit':
                    // Kazanç skoruna göre sırala (yüksekten düşüğe)
                    sorted.sort((a, b) => {
                        const aProfit = a.profit_from_score || 0;
                        const bProfit = b.profit_from_score || 0;
                        return bProfit - aProfit;
                    });
                    break;
                case 'en_iyi_derece':
                    // En iyi dereceye göre sırala
                    sorted.sort((a, b) => {
                        const aHasEnIyiDerece = a.en_iyi_derece !== null && a.en_iyi_derece !== undefined && a.en_iyi_derece !== '';
                        const bHasEnIyiDerece = b.en_iyi_derece !== null && b.en_iyi_derece !== undefined && b.en_iyi_derece !== '';
                        
                        // En iyi derece olanlar önce
                        if (aHasEnIyiDerece && !bHasEnIyiDerece) {
                            return -1;
                        }
                        if (!aHasEnIyiDerece && bHasEnIyiDerece) {
                            return 1;
                        }
                        
                        // İkisi de en iyi derece varsa veya ikisi de yoksa, olasılık skoruna göre
                        const aScore = a.combined_score || 0;
                        const bScore = b.combined_score || 0;
                        return bScore - aScore;
                    });
                    break;
                default:
                    // Default: koşuya göre
                    sorted.sort((a, b) => a.kosu_no - b.kosu_no);
            }
            return sorted;
        }
        
        // Sıralama dropdown'ı kaldırıldı - artık her zaman olasılık skoruna göre sıralama yapılıyor
        
        // Render fonksiyonu - Koşu bazında gruplama
        function renderBestBets(bets, targetList = 'active') {
            // Aktif ve bitmiş koşuları ayır
            const activeBets = bets.filter(bet => !bet.is_finished);
            const finishedBets = bets.filter(bet => bet.is_finished);
            
            console.log('📊 Anlık Yapay Zeka Tahminleri - Aktif koşular:', activeBets.length, 'Bitmiş koşular:', finishedBets.length);
            console.log('📊 Tüm koşular:', bets.length, 'Aktif:', activeBets.length, 'Bitmiş:', finishedBets.length);
            
            // Tab butonlarını göster/gizle
            // Her zaman tabler göster (aktif koşular varsa "Devam Eden", bitmiş koşular varsa "Tamamlanan")
            if (bestBetsTabs) {
                if (activeBets.length > 0 || finishedBets.length > 0) {
                    // En az bir tab var, tab'leri göster
                    bestBetsTabs.style.display = 'flex';
                    console.log('✅ Tabler gösteriliyor (aktif:', activeBets.length, 'bitmiş:', finishedBets.length, ')');
                    
                    // Eğer sadece bir tab varsa, diğer tab butonunu gizle
                    if (activeBets.length === 0) {
                        // Sadece bitmiş koşular var, "Devam Eden" tab'ini gizle
                        const activeTabButton = bestBetsTabs.querySelector('[data-tab="active"]');
                        if (activeTabButton) {
                            activeTabButton.style.display = 'none';
                        }
                        const finishedTabButton = bestBetsTabs.querySelector('[data-tab="finished"]');
                        if (finishedTabButton) {
                            finishedTabButton.style.display = 'block';
                            // Eğer targetList 'active' ise ama aktif koşu yoksa, 'finished' tab'ini aktif yap
                            if (targetList === 'active') {
                                finishedTabButton.classList.add('active');
                                const otherActive = bestBetsTabs.querySelector('[data-tab="active"].active');
                                if (otherActive) {
                                    otherActive.classList.remove('active');
                                }
                            }
                        }
                    } else if (finishedBets.length === 0) {
                        // Sadece aktif koşular var, "Tamamlanan" tab'ini gizle
                        const finishedTabButton = bestBetsTabs.querySelector('[data-tab="finished"]');
                        if (finishedTabButton) {
                            finishedTabButton.style.display = 'none';
                        }
                        const activeTabButton = bestBetsTabs.querySelector('[data-tab="active"]');
                        if (activeTabButton) {
                            // Eğer targetList 'finished' ise ama bitmiş koşu yoksa, 'active' tab'ini aktif yap
                            if (targetList === 'finished') {
                                activeTabButton.classList.add('active');
                                const otherActive = bestBetsTabs.querySelector('[data-tab="finished"].active');
                                if (otherActive) {
                                    otherActive.classList.remove('active');
                                }
                            }
                        }
                    } else {
                        // Her iki tab de var, her ikisini de göster
                        bestBetsTabs.querySelectorAll('.best-bet-tab-button').forEach(btn => {
                            btn.style.display = 'block';
                        });
                        // Aktif tab'ı set et
                        const activeTabButton = bestBetsTabs.querySelector(`[data-tab="${targetList}"]`);
                        const allTabButtons = bestBetsTabs.querySelectorAll('.best-bet-tab-button');
                        allTabButtons.forEach(btn => btn.classList.remove('active'));
                        if (activeTabButton) {
                            activeTabButton.classList.add('active');
                        }
                    }
                } else {
                    // Hiç koşu yok, tab'leri gizle
                    bestBetsTabs.style.display = 'none';
                    console.log('❌ Tabler gizleniyor (hiç koşu yok)');
                }
            }
            
            // Koşu bazında grupla
            function groupBetsByRace(betsArray) {
                const racesMap = {};
                betsArray.forEach((bet) => {
                    const raceKey = `${bet.kosu_no}_${bet.kosu_saat}`;
                    if (!racesMap[raceKey]) {
                        racesMap[raceKey] = {
                            kosu_no: bet.kosu_no,
                            kosu_saat: bet.kosu_saat,
                            kosu_sinif: bet.kosu_sinif,
                            kosu_mesafe: bet.kosu_mesafe,
                            pist_tur: bet.pist_tur,
                            is_soon: bet.is_soon,
                            is_finished: bet.is_finished || false,
                            race_winner: null,
                            horses: []
                        };
                    }
                    // Kazanan bilgisini al (race_winner'dan veya kazanan atın adından)
                    if (bet.is_finished && !racesMap[raceKey].race_winner) {
                        if (bet.race_winner) {
                            racesMap[raceKey].race_winner = bet.race_winner;
                        } else if (bet.is_winner) {
                            racesMap[raceKey].race_winner = bet.at_adi;
                        }
                    }
                    racesMap[raceKey].horses.push(bet);
                });
                
                // Her koşu altındaki atları olasılık skoruna göre sırala
                Object.values(racesMap).forEach(race => {
                    race.horses.sort((a, b) => {
                        const aScore = a.combined_score || 0;
                        const bScore = b.combined_score || 0;
                        return bScore - aScore; // Yüksekten düşüğe
                    });
                });
                
                // Koşuları sırala
                const races = Object.values(racesMap);
                races.sort((a, b) => a.kosu_no - b.kosu_no);
                return races;
            }
            
            // Aktif ve bitmiş koşuları ayrı ayrı render et
            const activeRaces = groupBetsByRace(activeBets);
            const finishedRaces = groupBetsByRace(finishedBets);
            
            // Render helper fonksiyonu
            function renderRaceHTML(races) {
                return races.map((race) => {
                const raceClass = race.is_finished ? 'race-group finished' : 'race-group';
                const raceHeaderClass = race.is_finished ? 'race-header finished' : 'race-header';
                
                // Kazanan bilgisi için header badge
                let headerBadge = '';
                if (race.is_finished && race.race_winner) {
                    headerBadge = `<span class="race-winner-badge">✓ Kazanan: ${race.race_winner}</span>`;
                } else if (race.is_soon && !race.is_finished) {
                    headerBadge = '<span class="soon-badge">🔥 Yakında</span>';
                }
                
                // Koşu bilgilerini badge'ler halinde oluştur (koşu kartlarındaki gibi)
                const raceInfoBadges = [];
                
                // Koşu numarası
                raceInfoBadges.push(`<span class="kosu-info-badge race-number">${race.kosu_no}. Koşu</span>`);
                
                // Saat
                if (race.kosu_saat) {
                    raceInfoBadges.push(`<span class="kosu-info-badge time">${race.kosu_saat}</span>`);
                }
                
                // Mesafe ve Pist türü birleşik (2100m Çim)
                if (race.kosu_mesafe || race.pist_tur) {
                    const mesafeStr = race.kosu_mesafe ? `${race.kosu_mesafe}m` : '';
                    const pistTurStr = race.pist_tur ? formatPistTur(race.pist_tur) : '';
                    const combinedStr = [mesafeStr, pistTurStr].filter(Boolean).join(' ');
                    if (combinedStr) {
                        // Pist türüne göre class ekle
                        let pistClass = 'distance';
                        if (race.pist_tur) {
                            const pistTurLower = race.pist_tur.toLowerCase();
                            if (pistTurLower.includes('çim') || pistTurLower.includes('cim')) {
                                pistClass = 'distance track-cim';
                            } else if (pistTurLower.includes('kum')) {
                                pistClass = 'distance track-kum';
                            } else if (pistTurLower.includes('sentetik')) {
                                pistClass = 'distance track-sentetik';
                            }
                        }
                        raceInfoBadges.push(`<span class="kosu-info-badge ${pistClass}">${combinedStr}</span>`);
                    }
                }
                
                // Sınıf (SATIŞ 3 gibi) - en sonda, tooltip yok
                const sinifText = race.kosu_sinif || '';
                if (sinifText) {
                    raceInfoBadges.push(`<span class="kosu-info-badge class">${sinifText}</span>`);
                }
                
                return `
                <div class="${raceClass}">
                    <div class="${raceHeaderClass}">
                        <div class="race-title">
                            <div class="kosu-title">
                                ${raceInfoBadges.join('')}
                            </div>
                        </div>
                        ${headerBadge}
                    </div>
                    <div class="race-horses">
                        ${race.horses.map((bet, index) => {
                            const isWinner = bet.is_winner || false;
                            const dereceSonuc = bet.derece_sonuc || null;
                            
                            // Sanalganyan URL oluştur
                            const sanalganyanUrl = getSanalganyanAtUrl(hipodrom, bet.kosu_no, bet.at_adi, data.tarih);
                            
                            // Sonuç bilgisi (bitmiş koşularda)
                            let resultInfo = '';
                            if (race.is_finished && isWinner) {
                                resultInfo = `<span class="winner-result-badge">✓ Kazanan - 1. Sıra</span>`;
                            } else if (race.is_finished && dereceSonuc !== null) {
                                resultInfo = `<span class="result-info">Sonuç: ${dereceSonuc}</span>`;
                            }
                            
                            return `
                            <a href="${sanalganyanUrl}" target="_blank" rel="noopener noreferrer" class="best-bet-card-link">
                                <div class="best-bet-card ${race.is_finished ? 'finished' : ''} ${isWinner ? 'winner' : ''}">
                                    <div class="best-bet-content">
                                        <div class="best-bet-info">
                                            <div class="best-bet-header-row">
                                                <div class="best-bet-number">${index + 1}</div>
                                                <div class="best-bet-name">${(bet.at_no !== null && bet.at_no !== undefined) ? `${bet.at_no} - ` : ''}${bet.at_adi}</div>
                                            </div>
                                            <div class="best-bet-details">
                                                ${bet.jokey_adi ? `Jokey: ${bet.jokey_adi}` : ''}
                                            </div>
                                            ${resultInfo}
                                        </div>
                                        <div class="best-bet-values">
                                            <div class="value-box">
                                                <div class="value-item">
                                                    <div class="value-label">Olasılık</div>
                                                    <div class="value-main">${formatOlasilik(bet.olasilik)}</div>
                                                    ${bet.olasilik_sira ? `<div class="value-sub">Sıra: ${bet.olasilik_sira}</div>` : ''}
                                                </div>
                                                ${bet.agf_value !== null && bet.agf_value !== undefined ? `
                                                <div class="value-item">
                                                    <div class="value-label">${bet.agf_type || 'AGF1'}</div>
                                                    ${bet.agf_value === 0 || bet.agf_value === 0.0 || bet.agf_value.toFixed(2) === '0.00' ? `
                                                    <div class="value-main agf1">YAKINDA</div>
                                                    ` : `
                                                    <div class="value-main agf1">${bet.agf_value.toFixed(2)}%</div>
                                                    ${bet.agf_type === 'AGF1' && bet.agf1_sira ? `<div class="value-sub">Sıra: ${bet.agf1_sira}</div>` : ''}
                                                    ${bet.agf_type === 'AGF2' && bet.agf2_sira ? `<div class="value-sub">Sıra: ${bet.agf2_sira}</div>` : ''}
                                                    `}
                                                </div>
                                                ` : ''}
                                                ${bet.ganyan !== null && bet.ganyan !== undefined ? `
                                                <div class="value-item">
                                                    <div class="value-label">Ganyan</div>
                                                    <div class="value-main ganyan">${bet.ganyan.toFixed(2)}</div>
                                                </div>
                                                ` : ''}
                                            </div>
                                            <div class="score-box">
                                                ${bet.combined_score !== null && bet.combined_score !== undefined ? `
                                                <div class="value-item">
                                                    <div class="value-label">Olasılık Skoru</div>
                                                    <div class="score-main">${(bet.combined_score * 100).toFixed(1)}%</div>
                                                </div>
                                                ` : ''}
                                                ${bet.profit_from_score !== null && bet.profit_from_score !== undefined ? `
                                                <div class="value-item">
                                                    <div class="value-label">Kazanç Skoru</div>
                                                    <div class="score-main profit">${bet.profit_from_score.toFixed(2)}</div>
                                                </div>
                                                ` : ''}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </a>
                            `;
                        }).join('')}
                    </div>
                </div>
                `;
                }).join('');
            }
            
            // Aktif ve bitmiş listeleri render et
            const bestBetsListFinished = document.getElementById('bestBetsListFinished');
            
            if (targetList === 'active') {
                if (activeRaces.length > 0) {
                    bestBetsList.innerHTML = renderRaceHTML(activeRaces);
                    bestBetsList.style.display = 'flex';
                    if (bestBetsListFinished) {
                        bestBetsListFinished.style.display = 'none';
                    }
                } else {
                    // Aktif yoksa otomatik olarak tamamlananları göster
                    bestBetsList.innerHTML = '';
                    bestBetsList.style.display = 'none';
                    if (finishedRaces.length > 0 && bestBetsListFinished) {
                        bestBetsListFinished.innerHTML = renderRaceHTML(finishedRaces);
                        bestBetsListFinished.style.display = 'flex';
                        // "Tamamlanan" tab'ini aktif yap
                        const finishedTabButton = bestBetsTabs ? bestBetsTabs.querySelector('[data-tab="finished"]') : null;
                        const activeTabButton = bestBetsTabs ? bestBetsTabs.querySelector('[data-tab="active"]') : null;
                        if (finishedTabButton && activeTabButton) {
                            activeTabButton.classList.remove('active');
                            finishedTabButton.classList.add('active');
                        }
                    }
                }
            } else {
                if (bestBetsListFinished) {
                    if (finishedRaces.length > 0) {
                        bestBetsListFinished.innerHTML = renderRaceHTML(finishedRaces);
                        bestBetsListFinished.style.display = 'flex';
                    } else {
                        bestBetsListFinished.innerHTML = '';
                        bestBetsListFinished.style.display = 'none';
                    }
                }
                bestBetsList.style.display = 'none';
            }
        }
        
        // Tab butonları için event listener
        if (bestBetsTabs) {
            bestBetsTabs.addEventListener('click', (e) => {
                if (e.target.classList.contains('best-bet-tab-button')) {
                    // Aktif tab'ı güncelle
                    bestBetsTabs.querySelectorAll('.best-bet-tab-button').forEach(btn => {
                        btn.classList.remove('active');
                    });
                    e.target.classList.add('active');
                    
                    // İlgili listeyi göster
                    const tab = e.target.getAttribute('data-tab');
                    // window.currentTahminlerData kullan (güncel veri için)
                    const currentData = window.currentTahminlerData || data;
                    if (currentData && currentData.best_bets && currentData.best_bets.length > 0) {
                        // Her zaman olasılık skoruna göre sırala
                        const sortedBets = sortBestBets(currentData.best_bets, 'probability');
                        renderBestBets(sortedBets, tab);
                    }
                }
            });
        }
        
        if (data.best_bets && data.best_bets.length > 0) {
            // Her zaman olasılık skoruna göre sırala
            const sortedBets = sortBestBets(data.best_bets, 'probability');
            
            // Aktif ve bitmiş koşuları kontrol et
            const activeBets = sortedBets.filter(bet => !bet.is_finished);
            const finishedBets = sortedBets.filter(bet => bet.is_finished);
            
            // Default tab: Eğer aktif koşular varsa 'active', yoksa 'finished'
            const defaultTab = activeBets.length > 0 ? 'active' : 'finished';
            console.log('📊 Default tab seçiliyor:', defaultTab, '(Aktif:', activeBets.length, 'Bitmiş:', finishedBets.length, ')');
            
            renderBestBets(sortedBets, defaultTab);
        } else {
            bestBetsList.innerHTML = `
                <div class="best-bet-card" style="text-align: center;">
                    <p style="color: var(--text-light);">Henüz ganyan oranları gelmediği için anlık yapay zeka tahminleri hesaplanamıyor.</p>
                    <p style="font-size: 0.875rem; color: var(--text-light); margin-top: 0.5rem;">Ganyan oranları geldiğinde bu bölüm otomatik olarak güncellenecektir.</p>
                </div>
            `;
        }
        
        // bestBetsSection sadece Tahminler tabı seçildiğinde gösterilecek (showTahminler fonksiyonunda)
        // Burada gösterme, ilk koşu gösterilecek
        
        // Son güncelleme zamanını göster
        const lastUpdate = document.getElementById('lastUpdate');
        if (lastUpdate) {
            lastUpdate.textContent = `Son güncelleme: ${new Date().toLocaleTimeString('tr-TR')}`;
        }
        
        // Loading spinner'ı sadece ilk yüklemede gizle
        if (!preserveScroll) {
            loading.style.display = 'none';
            if (content) {
            content.style.display = 'block';
            }
        }
        
        console.log('Tahminler başarıyla yüklendi');
        
        // Scroll pozisyonunu geri yükle (eğer preserveScroll true ise)
        if (preserveScroll && scrollPosition > 0) {
            // Kısa bir gecikme ile scroll pozisyonunu geri yükle (DOM güncellemesinin tamamlanması için)
            setTimeout(() => {
                window.scrollTo({
                    top: scrollPosition,
                    behavior: 'auto' // Smooth yerine auto kullan, daha hızlı
                });
                console.log('Scroll pozisyonu geri yüklendi:', scrollPosition);
            }, 100);
        }
        
    } catch (err) {
        console.error('❌ Tahminler yüklenirken hata:', err);
        console.error('❌ Hata detayı:', err.stack);
        
        // Loading'i her durumda temizle
        if (loading) {
        loading.style.display = 'none';
        }
        if (content) {
            content.style.display = 'block';
        }
        if (error) {
        error.style.display = 'block';
        error.innerHTML = `<p style="color: #991b1b; font-weight: 500;">Tahminler yüklenirken bir hata oluştu: ${err.message}</p><p style="font-size: 0.875rem; color: #dc2626; margin-top: 0.5rem;">Tarayıcı konsolunu (F12) kontrol edin.</p>`;
        }
    }
}

// Auto-refresh every 10 minutes
let autoRefreshInterval = null;

// Güncelleme zamanı kontrolü (CSV güncellemelerinde sayfayı yenile)
let updateCheckInterval = null;
let lastKnownUpdateTime = null;

async function refreshAllData() {
    // Mevcut durumu kaydet
    const currentHipodrom = window.currentHipodrom;
    const currentKosu = window.currentKosu;
    const scrollPosition = window.scrollY;
    
    // Mevcut aktif tab'ları kaydet
    const activeCityTab = document.querySelector('#tabsList .tab-button.active');
    const activeRaceTab = document.querySelector('#kosuTabsList .tab-button.active');
    const activeCityTabHipodrom = activeCityTab ? activeCityTab.dataset.hipodrom : null;
    const activeRaceTabKosuNo = activeRaceTab ? activeRaceTab.dataset.kosuNo : null;
    const activeRaceTabType = activeRaceTab ? activeRaceTab.dataset.tabType : null;
    
    // Mevcut içeriği kaydet (görsel kayma olmasın diye)
    const kosularSection = document.getElementById('kosularSection');
    const bestBetsSection = document.getElementById('bestBetsSection');
    const kosularSectionHTML = kosularSection ? kosularSection.innerHTML : null;
    const bestBetsSectionHTML = bestBetsSection ? bestBetsSection.innerHTML : null;
    
    console.log('🔄 Veriler arka planda güncelleniyor (sayfa yenilenmeden, görsel kayma yok)...');
    
    try {
        // Hipodromları yeniden yükle (ama aktif tab'ı koru)
        if (document.getElementById('tabsContainer')) {
            await loadHipodromlar(true); // skipAutoSelect = true (aktif tab'ı korumak için)
            
            // Aktif şehir tab'ını geri yükle
            if (activeCityTabHipodrom) {
                const cityTab = document.querySelector(`.tab-button[data-hipodrom="${activeCityTabHipodrom}"]`);
                if (cityTab) {
                    // Tüm tab'lardan active class'ını kaldır
                    document.querySelectorAll('#tabsList .tab-button').forEach(btn => btn.classList.remove('active'));
                    // Aktif tab'a geri ekle
                    cityTab.classList.add('active');
                }
            }
        }
        
        // Seçili hipodrom varsa tahminleri yeniden yükle (ama içeriği gizlemeden)
        if (currentHipodrom) {
            // Otomatik seçimi engelle (mevcut tab'ı korumak için)
            // Her güncellemede flag'leri yeniden set et (önceden temizlenmiş olabilir)
            window.autoSelectingRace = true;
            window.preservingTab = true; // Tab koruma modunda olduğumuzu işaretle
            
            // Verileri yükle (ama loading spinner gösterme, içeriği gizleme)
            await loadTahminler(currentHipodrom, true); // preserveScroll = true
            
            // Tab'lar oluştuktan sonra mevcut tab'ı geri yükle
            if (document.getElementById('kosuTabsContainer')) {
                // Daha uzun bekle ki tab'lar kesinlikle oluşsun
                setTimeout(() => {
                    // Flag'leri hala koru (tab seçilene kadar)
                    window.autoSelectingRace = true;
                    window.preservingTab = true;
                    
                    if (activeRaceTabType === 'tahminler') {
                        // Eğer "Tahminler" tab'ı seçiliyse, onu geri yükle
                        const tahminlerTab = document.querySelector(`#kosuTabsList .tab-button[data-tab-type="tahminler"]`);
                        if (tahminlerTab) {
                            // Tüm tab'lardan active class'ını kaldır
                            document.querySelectorAll('#kosuTabsList .tab-button').forEach(tab => tab.classList.remove('active'));
                            // "Tahminler" tab'ını aktif yap
                            tahminlerTab.classList.add('active');
                            
                            // Tab'a tıkla ki showTahminler fonksiyonu çağrılsın ve içerik güncellensin
                            tahminlerTab.click();
                        }
                    } else if (activeRaceTabKosuNo) {
                        // Eğer koşu tab'ı seçiliyse, onu geri yükle
                        const raceTab = document.querySelector(`#kosuTabsList .tab-button[data-kosu-no="${activeRaceTabKosuNo}"]`);
                        if (raceTab) {
                            // Tüm tab'lardan active class'ını kaldır
                            document.querySelectorAll('#kosuTabsList .tab-button').forEach(tab => tab.classList.remove('active'));
                            // Aktif tab'a geri ekle
                            raceTab.classList.add('active');
                            // Tab'a tıkla ki içerik yüklensin
                            raceTab.click();
                        }
                    } else {
                        // Eğer hiçbir tab seçili değilse, otomatik seçimi engelle
                        // (1. koşuya atmasın)
                    }
                    
                    // Tab seçildikten sonra flag'leri temizle (biraz daha bekle)
                    setTimeout(() => {
                        window.autoSelectingRace = false;
                        window.preservingTab = false;
                    }, 100);
                }, 300);
            } else {
                // Otomatik seçim flag'ini temizle
                setTimeout(() => {
                    window.autoSelectingRace = false;
                    window.preservingTab = false;
                }, 100);
            }
        }
        
        // Son kazanan tahminleri yeniden yükle (sessizce, görsel kayma olmadan)
        await loadCompletedRacesCarousel();
        
        // Scroll pozisyonunu geri yükle (smooth olmadan, anında)
        if (Math.abs(window.scrollY - scrollPosition) > 1) {
            window.scrollTo({
                top: scrollPosition,
                behavior: 'instant' // Smooth değil, anında
            });
        }
        
        console.log('✅ Veriler güncellendi (kullanıcı hiçbir şey fark etmedi)');
    } catch (error) {
        console.error('Veri güncelleme hatası:', error);
        // Hata durumunda mevcut içeriği geri yükle
        if (kosularSection && kosularSectionHTML) {
            kosularSection.innerHTML = kosularSectionHTML;
            kosularSection.style.opacity = '1';
        }
        if (bestBetsSection && bestBetsSectionHTML) {
            bestBetsSection.innerHTML = bestBetsSectionHTML;
        }
    }
}

function startUpdateCheck() {
    // Mevcut interval'i temizle
    if (updateCheckInterval) {
        clearInterval(updateCheckInterval);
    }
    
    // Her 10 saniyede bir güncelleme zamanını kontrol et
    updateCheckInterval = setInterval(async () => {
        try {
            const response = await fetch(`${API_BASE}/api/update-time`);
            const data = await response.json();
            
            if (data.last_update_time) {
                // İlk kontrol - zamanı kaydet
                if (lastKnownUpdateTime === null) {
                    lastKnownUpdateTime = data.last_update_time;
                    return;
                }
                
                // Zaman değişmişse verileri güncelle (sayfa yenilemeden)
                if (data.last_update_time !== lastKnownUpdateTime) {
                    console.log('🔄 CSV güncellemesi tespit edildi, veriler güncelleniyor...');
                    lastKnownUpdateTime = data.last_update_time;
                    await refreshAllData();
                }
            }
        } catch (error) {
            console.error('Güncelleme zamanı kontrolü hatası:', error);
        }
    }, 10000); // 10 saniyede bir kontrol et
}

function startAutoRefresh(hipodrom) {
    // Clear existing interval
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
    }
    
    // Refresh every 10 minutes (600000 ms)
    autoRefreshInterval = setInterval(() => {
        console.log('Otomatik yenileme: tahminler güncelleniyor... (scroll pozisyonu ve tab korunacak)');
        
        // Mevcut tab'ı kaydet
        const activeRaceTab = document.querySelector('#kosuTabsList .tab-button.active');
        const activeRaceTabKosuNo = activeRaceTab ? activeRaceTab.dataset.kosuNo : null;
        const activeRaceTabType = activeRaceTab ? activeRaceTab.dataset.tabType : null;
        
        // Tab koruma modunu aktif et
        window.autoSelectingRace = true;
        window.preservingTab = true;
        
        const refreshHipodrom = hipodrom || window.currentHipodrom;
        if (refreshHipodrom) {
            loadTahminler(refreshHipodrom, true).then(() => {
                // Tab'lar oluştuktan sonra mevcut tab'ı geri yükle
                if (document.getElementById('kosuTabsContainer')) {
                    setTimeout(() => {
                        // Flag'leri hala koru
                        window.autoSelectingRace = true;
                        window.preservingTab = true;
                        
                        if (activeRaceTabType === 'tahminler') {
                            const tahminlerTab = document.querySelector(`#kosuTabsList .tab-button[data-tab-type="tahminler"]`);
                            if (tahminlerTab) {
                                document.querySelectorAll('#kosuTabsList .tab-button').forEach(tab => tab.classList.remove('active'));
                                tahminlerTab.classList.add('active');
                                tahminlerTab.click();
                            }
                        } else if (activeRaceTabKosuNo) {
                            const raceTab = document.querySelector(`#kosuTabsList .tab-button[data-kosu-no="${activeRaceTabKosuNo}"]`);
                            if (raceTab) {
                                document.querySelectorAll('#kosuTabsList .tab-button').forEach(tab => tab.classList.remove('active'));
                                raceTab.classList.add('active');
                                raceTab.click();
                            }
                        }
                        
                        // Flag'leri temizle
                        setTimeout(() => {
                            window.autoSelectingRace = false;
                            window.preservingTab = false;
                        }, 100);
                    }, 300);
                } else {
                    setTimeout(() => {
                        window.autoSelectingRace = false;
                        window.preservingTab = false;
                    }, 100);
                }
            });
        }
    }, 600000); // 10 dakika
}

// Global error handler
window.addEventListener('error', (event) => {
    console.error('JavaScript hatası:', event.error);
    const errorDiv = document.getElementById('errorMessage');
    if (errorDiv) {
        errorDiv.style.display = 'block';
        errorDiv.innerHTML = `<p style="color: #991b1b; font-weight: 500;">JavaScript hatası: ${event.error ? event.error.message : event.message}</p>`;
    }
});

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM yüklendi');
    
    // Logo'ya tıklandığında sayfayı yenile
    const headerLogo = document.querySelector('header img[alt*="Logo"]');
    if (headerLogo) {
        headerLogo.style.cursor = 'pointer';
        headerLogo.addEventListener('click', () => {
            window.location.reload();
        });
    }
    
    // Footer logo'ya da tıklanabilirlik ekle
    const footerLogo = document.querySelector('footer img[alt*="Logo"]');
    if (footerLogo) {
        footerLogo.style.cursor = 'pointer';
        footerLogo.addEventListener('click', () => {
            window.location.reload();
        });
    }
    
    try {
        // Güncelleme kontrolünü başlat (tüm sayfalar için)
        startUpdateCheck();
        
        // Carousel widget'ı yükle
        loadCompletedRacesCarousel();
        
        // Ana sayfa (tab sistemi ile)
        if (document.getElementById('tabsContainer')) {
            console.log('Ana sayfa yükleniyor');
            loadHipodromlar();
            
            // Auto-refresh başlat (ilk hipodrom için)
            setTimeout(() => {
                if (window.currentHipodrom) {
                    startAutoRefresh(window.currentHipodrom);
                }
            }, 1000);
        }
        // Eski tahminler sayfası (backward compatibility)
        else if (window.hipodrom) {
            console.log('Tahminler sayfası yükleniyor');
            loadTahminler(window.hipodrom);
            startAutoRefresh(window.hipodrom);
        }
    } catch (error) {
        console.error('Başlatma hatası:', error);
    }
});
