from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import sqlite3
import json
import random
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'mac-tahmin-super-secret-key-2024-render')

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_colored(message, color=Colors.CYAN):
    """Production'da konsol çıktısı için"""
    print(f"{color}{message}{Colors.END}")

def init_web_database():
    """Web panel için veritabanı tablolarını oluştur"""
    print_colored("🗄️ Web panel veritabanı başlatılıyor...", Colors.YELLOW)
    
    conn = sqlite3.connect('tahminler.db')
    cursor = conn.cursor()
    
    # Maçlar tablosu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS maclar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mac_adi TEXT NOT NULL,
            takim1 TEXT NOT NULL,
            takim2 TEXT NOT NULL,
            mac_tarihi DATETIME,
            gercek_skor TEXT,
            durum TEXT DEFAULT 'aktif',
            olusturma_tarihi TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Mevcut tahminler tablosunu kontrol et ve güncelle
    cursor.execute("PRAGMA table_info(tahminler)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'mac_id' not in columns:
        print_colored("⚠️ mac_id kolonu eksik, ekleniyor...", Colors.YELLOW)
        cursor.execute('ALTER TABLE tahminler ADD COLUMN mac_id INTEGER')
        
        # Mevcut tahminleri güncelle - mac_adi'na göre mac_id'leri eşleştir
        cursor.execute('''
            UPDATE tahminler 
            SET mac_id = (
                SELECT m.id 
                FROM maclar m 
                WHERE m.mac_adi = tahminler.mac_adi
            )
            WHERE mac_id IS NULL
        ''')
        print_colored("✅ mac_id kolonu eklendi ve veriler güncellendi!", Colors.GREEN)
    
    # Tahminler tablosu (güncellenmiş)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tahminler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            mac_adi TEXT,
            skor_tahmini TEXT,
            mac_id INTEGER,
            tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (mac_id) REFERENCES maclar (id)
        )
    ''')
    
    # Kazananlar tablosu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS kazananlar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mac_id INTEGER,
            user_id INTEGER,
            username TEXT,
            dogru_tahmin TEXT,
            kazanma_tarihi TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            cekilis_durumu TEXT DEFAULT 'beklemede',
            FOREIGN KEY (mac_id) REFERENCES maclar (id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print_colored("✅ Web panel veritabanı hazır!", Colors.GREEN)

@app.route('/')
def dashboard():
    """Ana dashboard"""
    conn = sqlite3.connect('tahminler.db')
    cursor = conn.cursor()
    
    # İstatistikler
    cursor.execute("SELECT COUNT(*) FROM maclar WHERE durum='aktif'")
    aktif_maclar = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM tahminler")
    toplam_tahminler = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM tahminler")
    toplam_kullanicilar = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM kazananlar")
    toplam_kazananlar = cursor.fetchone()[0]
    
    # Son maçlar
    cursor.execute('''
        SELECT id, mac_adi, takim1, takim2, mac_tarihi, gercek_skor, durum
        FROM maclar 
        ORDER BY olusturma_tarihi DESC 
        LIMIT 5
    ''')
    son_maclar = cursor.fetchall()
    
    conn.close()
    
    stats = {
        'aktif_maclar': aktif_maclar,
        'toplam_tahminler': toplam_tahminler,
        'toplam_kullanicilar': toplam_kullanicilar,
        'toplam_kazananlar': toplam_kazananlar
    }
    
    return render_template('dashboard.html', stats=stats, son_maclar=son_maclar)

@app.route('/maclar')
def maclar():
    """Maç listesi"""
    conn = sqlite3.connect('tahminler.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT m.id, m.mac_adi, m.takim1, m.takim2, m.mac_tarihi, 
               m.gercek_skor, m.durum, COUNT(t.id) as tahmin_sayisi
        FROM maclar m
        LEFT JOIN tahminler t ON m.id = t.mac_id
        GROUP BY m.id
        ORDER BY m.olusturma_tarihi DESC
    ''')
    
    maclar_listesi = cursor.fetchall()
    conn.close()
    
    return render_template('maclar.html', maclar=maclar_listesi)

@app.route('/mac_sil/<int:mac_id>')
def mac_sil(mac_id):
    """Maç silme - İlişkili verileri de sil"""
    conn = sqlite3.connect('tahminler.db')
    cursor = conn.cursor()
    
    # Maç bilgisini al
    cursor.execute('SELECT mac_adi FROM maclar WHERE id=?', (mac_id,))
    mac_info = cursor.fetchone()
    
    if not mac_info:
        flash('❌ Maç bulunamadı!', 'error')
        return redirect(url_for('maclar'))
    
    mac_adi = mac_info[0]
    
    # İlişkili verileri say
    cursor.execute('''
        SELECT COUNT(*) FROM tahminler 
        WHERE mac_id = ? OR mac_adi = ?
    ''', (mac_id, mac_adi))
    tahmin_sayisi = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM kazananlar WHERE mac_id = ?', (mac_id,))
    kazanan_sayisi = cursor.fetchone()[0]
    
    try:
        # İlişkili verileri sil
        cursor.execute('''
            DELETE FROM tahminler 
            WHERE mac_id = ? OR mac_adi = ?
        ''', (mac_id, mac_adi))
        
        cursor.execute('DELETE FROM kazananlar WHERE mac_id = ?', (mac_id,))
        cursor.execute('DELETE FROM maclar WHERE id = ?', (mac_id,))
        
        conn.commit()
        
        flash(f'✅ {mac_adi} maçı silindi! ({tahmin_sayisi} tahmin, {kazanan_sayisi} kazanan)', 'success')
        print_colored(f"🗑️ Maç silindi: {mac_adi} (Tahmin: {tahmin_sayisi}, Kazanan: {kazanan_sayisi})", Colors.RED)
        
    except Exception as e:
        conn.rollback()
        flash(f'❌ Maç silinirken hata oluştu: {str(e)}', 'error')
        print_colored(f"❌ Maç silme hatası: {str(e)}", Colors.RED)
    
    finally:
        conn.close()
    
    return redirect(url_for('maclar'))

@app.route('/mac_ekle', methods=['GET', 'POST'])
def mac_ekle():
    """Yeni maç ekleme"""
    if request.method == 'POST':
        takim1 = request.form['takim1']
        takim2 = request.form['takim2']
        mac_tarihi = request.form['mac_tarihi']
        
        mac_adi = f"{takim1}-{takim2}"
        
        conn = sqlite3.connect('tahminler.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO maclar (mac_adi, takim1, takim2, mac_tarihi)
            VALUES (?, ?, ?, ?)
        ''', (mac_adi, takim1, takim2, mac_tarihi))
        
        conn.commit()
        conn.close()
        
        flash(f'✅ {mac_adi} maçı başarıyla eklendi!', 'success')
        print_colored(f"✅ Yeni maç eklendi: {mac_adi}", Colors.GREEN)
        
        return redirect(url_for('maclar'))
    
    return render_template('mac_ekle.html')

@app.route('/mac_duzenle/<int:mac_id>', methods=['GET', 'POST'])
def mac_duzenle(mac_id):
    """Maç düzenleme - Gerçek skor girildiğinde otomatik kazanan belirleme"""
    conn = sqlite3.connect('tahminler.db')
    cursor = conn.cursor()
    
    if request.method == 'POST':
        takim1 = request.form['takim1']
        takim2 = request.form['takim2']
        mac_tarihi = request.form['mac_tarihi']
        gercek_skor = request.form['gercek_skor']
        durum = request.form['durum']
        
        mac_adi = f"{takim1}-{takim2}"
        
        # Eski maç bilgisini al
        cursor.execute('SELECT gercek_skor, mac_adi FROM maclar WHERE id=?', (mac_id,))
        eski_mac = cursor.fetchone()
        eski_gercek_skor = eski_mac[0] if eski_mac else None
        eski_mac_adi = eski_mac[1] if eski_mac else None
        
        # Maçı güncelle
        cursor.execute('''
            UPDATE maclar 
            SET mac_adi=?, takim1=?, takim2=?, mac_tarihi=?, gercek_skor=?, durum=?
            WHERE id=?
        ''', (mac_adi, takim1, takim2, mac_tarihi, gercek_skor, durum, mac_id))
        
        # Eğer gerçek skor yeni girildiyse veya değiştiyse, otomatik kazananları belirle
        if gercek_skor and gercek_skor != eski_gercek_skor:
            print_colored(f"🎯 Gerçek skor güncellendi: {mac_adi} - {gercek_skor}", Colors.YELLOW)
            
            # Bu maça tahmin yapan TÜM kullanıcıları bul
            cursor.execute('''
                SELECT DISTINCT user_id, username, skor_tahmini, mac_adi
                FROM tahminler
                WHERE (mac_id = ? OR mac_adi = ? OR mac_adi = ?) 
                AND skor_tahmini = ?
            ''', (mac_id, mac_adi, eski_mac_adi, gercek_skor))
            
            dogru_tahminler = cursor.fetchall()
            
            if dogru_tahminler:
                # Mevcut kazananları temizle
                cursor.execute('DELETE FROM kazananlar WHERE mac_id = ?', (mac_id,))
                
                # Yeni kazananları ekle
                kazanan_sayisi = 0
                for tahmin in dogru_tahminler:
                    user_id, username, skor_tahmini_user, tahmin_mac_adi = tahmin
                    
                    # Aynı kullanıcının birden fazla kaydı varsa sadece bir kez ekle
                    cursor.execute('''
                        SELECT COUNT(*) FROM kazananlar 
                        WHERE mac_id = ? AND user_id = ?
                    ''', (mac_id, user_id))
                    
                    if cursor.fetchone()[0] == 0:
                        cursor.execute('''
                            INSERT INTO kazananlar (mac_id, user_id, username, dogru_tahmin, cekilis_durumu)
                            VALUES (?, ?, ?, ?, 'otomatik')
                        ''', (mac_id, user_id, username, skor_tahmini_user))
                        kazanan_sayisi += 1
                        print_colored(f"✅ Kazanan eklendi: @{username} - {skor_tahmini_user}", Colors.GREEN)
                
                # Tahminler tablosundaki mac_id'leri de güncelle
                cursor.execute('''
                    UPDATE tahminler 
                    SET mac_id = ? 
                    WHERE (mac_adi = ? OR mac_adi = ?) AND mac_id IS NULL
                ''', (mac_id, mac_adi, eski_mac_adi))
                
                flash(f'✅ {mac_adi} maçı güncellendi! {kazanan_sayisi} kazanan otomatik belirlendi!', 'success')
                print_colored(f"🎉 {kazanan_sayisi} kazanan otomatik belirlendi: {mac_adi} - {gercek_skor}", Colors.GREEN)
            else:
                flash(f'✅ {mac_adi} maçı güncellendi! (Doğru tahmin yapan bulunamadı)', 'info')
                print_colored(f"ℹ️ Doğru tahmin yapan bulunamadı: {mac_adi} - {gercek_skor}", Colors.YELLOW)
        else:
            flash(f'✅ {mac_adi} maçı güncellendi!', 'success')
        
        conn.commit()
        conn.close()
        
        return redirect(url_for('maclar'))
    
    # Maç bilgilerini getir
    cursor.execute('SELECT * FROM maclar WHERE id=?', (mac_id,))
    mac = cursor.fetchone()
    conn.close()
    
    if not mac:
        flash('❌ Maç bulunamadı!', 'error')
        return redirect(url_for('maclar'))
    
    return render_template('mac_duzenle.html', mac=mac)

@app.route('/tahminler')
def tahminler():
    """Geliştirilmiş tahminler sayfası"""
    conn = sqlite3.connect('tahminler.db')
    cursor = conn.cursor()
    
    # Sayfa parametresi
    page = request.args.get('page', 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page
    
    # Filtreleme parametreleri
    mac_filter = request.args.get('mac', '')
    kullanici_filter = request.args.get('kullanici', '')
    durum_filter = request.args.get('durum', '')
    
    # Önce mac_id kolonunun varlığını kontrol et
    cursor.execute("PRAGMA table_info(tahminler)")
    columns = [column[1] for column in cursor.fetchall()]
    has_mac_id = 'mac_id' in columns
    
    # Base query
    if has_mac_id:
        query = '''
            SELECT t.id, t.username, t.mac_adi, t.skor_tahmini, t.tarih, 
                   m.gercek_skor, m.durum,
                   CASE 
                       WHEN m.gercek_skor IS NULL THEN 'beklemede'
                       WHEN t.skor_tahmini = m.gercek_skor THEN 'dogru'
                       ELSE 'yanlis'
                   END as tahmin_durumu
            FROM tahminler t 
            LEFT JOIN maclar m ON (t.mac_id = m.id OR t.mac_adi = m.mac_adi)
            WHERE 1=1
        '''
    else:
        query = '''
            SELECT t.id, t.username, t.mac_adi, t.skor_tahmini, t.tarih, 
                   m.gercek_skor, m.durum,
                   CASE 
                       WHEN m.gercek_skor IS NULL THEN 'beklemede'
                       WHEN t.skor_tahmini = m.gercek_skor THEN 'dogru'
                       ELSE 'yanlis'
                   END as tahmin_durumu
            FROM tahminler t 
            LEFT JOIN maclar m ON t.mac_adi = m.mac_adi
            WHERE 1=1
        '''
    
    params = []
    
    # Filtreleri ekle
    if mac_filter:
        query += ' AND t.mac_adi LIKE ?'
        params.append(f'%{mac_filter}%')
    
    if kullanici_filter:
        query += ' AND t.username LIKE ?'
        params.append(f'%{kullanici_filter}%')
    
    if durum_filter:
        if durum_filter == 'dogru':
            query += ' AND t.skor_tahmini = m.gercek_skor AND m.gercek_skor IS NOT NULL'
        elif durum_filter == 'yanlis':
            query += ' AND t.skor_tahmini != m.gercek_skor AND m.gercek_skor IS NOT NULL'
        elif durum_filter == 'beklemede':
            query += ' AND m.gercek_skor IS NULL'
    
    # Toplam sayıyı al
    if has_mac_id:
        count_query = '''
            SELECT COUNT(*)
            FROM tahminler t 
            LEFT JOIN maclar m ON (t.mac_id = m.id OR t.mac_adi = m.mac_adi)
            WHERE 1=1
        '''
    else:
        count_query = '''
            SELECT COUNT(*)
            FROM tahminler t 
            LEFT JOIN maclar m ON t.mac_adi = m.mac_adi
            WHERE 1=1
        '''
    
    count_params = []
    if mac_filter:
        count_query += ' AND t.mac_adi LIKE ?'
        count_params.append(f'%{mac_filter}%')
    
    if kullanici_filter:
        count_query += ' AND t.username LIKE ?'
        count_params.append(f'%{kullanici_filter}%')
    
    if durum_filter:
        if durum_filter == 'dogru':
            count_query += ' AND t.skor_tahmini = m.gercek_skor AND m.gercek_skor IS NOT NULL'
        elif durum_filter == 'yanlis':
            count_query += ' AND t.skor_tahmini != m.gercek_skor AND m.gercek_skor IS NOT NULL'
        elif durum_filter == 'beklemede':
            count_query += ' AND m.gercek_skor IS NULL'
    
    cursor.execute(count_query, count_params)
    total = cursor.fetchone()[0]
    
    # Sayfalama ekle
    query += ' ORDER BY t.tarih DESC LIMIT ? OFFSET ?'
    params.extend([per_page, offset])
    
    cursor.execute(query, params)
    tahminler_listesi = cursor.fetchall()
    
    # İstatistikler
    if has_mac_id:
        stats_query = '''
            SELECT 
                COUNT(*) as toplam,
                COUNT(CASE WHEN t.skor_tahmini = m.gercek_skor THEN 1 END) as dogru,
                COUNT(CASE WHEN t.skor_tahmini != m.gercek_skor AND m.gercek_skor IS NOT NULL THEN 1 END) as yanlis,
                COUNT(CASE WHEN m.gercek_skor IS NULL THEN 1 END) as beklemede
            FROM tahminler t 
            LEFT JOIN maclar m ON (t.mac_id = m.id OR t.mac_adi = m.mac_adi)
        '''
    else:
        stats_query = '''
            SELECT 
                COUNT(*) as toplam,
                COUNT(CASE WHEN t.skor_tahmini = m.gercek_skor THEN 1 END) as dogru,
                COUNT(CASE WHEN t.skor_tahmini != m.gercek_skor AND m.gercek_skor IS NOT NULL THEN 1 END) as yanlis,
                COUNT(CASE WHEN m.gercek_skor IS NULL THEN 1 END) as beklemede
            FROM tahminler t 
            LEFT JOIN maclar m ON t.mac_adi = m.mac_adi
        '''
    
    cursor.execute(stats_query)
    istatistikler = cursor.fetchone()
    
    # Tüm maçları al
    cursor.execute('SELECT DISTINCT mac_adi FROM maclar ORDER BY mac_adi')
    maclar_listesi = cursor.fetchall()
    
    conn.close()
    
    # Sayfa bilgileri
    has_prev = page > 1
    has_next = offset + per_page < total
    prev_num = page - 1 if has_prev else None
    next_num = page + 1 if has_next else None
    
    return render_template('tahminler.html', 
                         tahminler=tahminler_listesi,
                         istatistikler=istatistikler,
                         maclar=maclar_listesi,
                         page=page,
                         has_prev=has_prev,
                         has_next=has_next,
                         prev_num=prev_num,
                         next_num=next_num,
                         total=total,
                         filters={
                             'mac': mac_filter,
                             'kullanici': kullanici_filter,
                             'durum': durum_filter
                         })

@app.route('/mac_tahminleri/<int:mac_id>')
def mac_tahminleri(mac_id):
    """Belirli bir maçın tahminleri"""
    conn = sqlite3.connect('tahminler.db')
    cursor = conn.cursor()
    
    # Maç bilgisi
    cursor.execute('SELECT * FROM maclar WHERE id=?', (mac_id,))
    mac = cursor.fetchone()
    
    # Tahminler
    cursor.execute('''
        SELECT t.id, t.user_id, t.username, t.skor_tahmini, t.tarih
        FROM tahminler t
        WHERE t.mac_id = ? OR t.mac_adi = ?
        ORDER BY t.tarih ASC
    ''', (mac_id, mac[1] if mac else ''))
    
    tahminler_listesi = cursor.fetchall()
    
    # Doğru tahminler
    dogru_tahminler = []
    if mac and mac[5]:  # gercek_skor varsa
        gercek_skor = mac[5]
        dogru_tahminler = [t for t in tahminler_listesi if t[3] == gercek_skor]
    
    conn.close()
    
    return render_template('mac_tahminleri.html', 
                         mac=mac, 
                         tahminler=tahminler_listesi,
                         dogru_tahminler=dogru_tahminler)

@app.route('/kazananlari_belirle/<int:mac_id>')
def kazananlari_belirle(mac_id):
    """Kazananları otomatik belirle"""
    conn = sqlite3.connect('tahminler.db')
    cursor = conn.cursor()
    
    # Maç bilgisi
    cursor.execute('SELECT * FROM maclar WHERE id=?', (mac_id,))
    mac = cursor.fetchone()
    
    if not mac or not mac[5]:  # Gerçek skor yoksa
        flash('❌ Önce maçın gerçek skorunu girin!', 'error')
        return redirect(url_for('mac_tahminleri', mac_id=mac_id))
    
    gercek_skor = mac[5]
    
    # Doğru tahmin yapanları bul
    cursor.execute('''
        SELECT user_id, username, skor_tahmini
        FROM tahminler
        WHERE (mac_id = ? OR mac_adi = ?) AND skor_tahmini = ?
    ''', (mac_id, mac[1], gercek_skor))
    
    dogru_tahminler = cursor.fetchall()
    
    # Kazananlar tablosunu temizle
    cursor.execute('DELETE FROM kazananlar WHERE mac_id = ?', (mac_id,))
    
    # Kazananları ekle
    for tahmin in dogru_tahminler:
        cursor.execute('''
            INSERT INTO kazananlar (mac_id, user_id, username, dogru_tahmin)
            VALUES (?, ?, ?, ?)
        ''', (mac_id, tahmin[0], tahmin[1], tahmin[2]))
    
    conn.commit()
    conn.close()
    
    flash(f'✅ {len(dogru_tahminler)} kazanan belirlendi!', 'success')
    print_colored(f"✅ {mac[1]} maçı için {len(dogru_tahminler)} kazanan belirlendi", Colors.GREEN)
    
    return redirect(url_for('kazananlar', mac_id=mac_id))

@app.route('/kazananlar')
def kazananlar():
    """Kazananlar sayfası"""
    conn = sqlite3.connect('tahminler.db')
    cursor = conn.cursor()
    
    # Toplam kazanan sayısı
    cursor.execute('SELECT COUNT(*) FROM kazananlar')
    toplam_kazanan = cursor.fetchone()[0]
    
    # Tüm kazananları getir
    cursor.execute('''
        SELECT k.id, k.username, m.mac_adi, k.dogru_tahmin, m.gercek_skor, k.kazanma_tarihi
        FROM kazananlar k
        JOIN maclar m ON k.mac_id = m.id
        ORDER BY k.kazanma_tarihi DESC
    ''')
    kazananlar_listesi = cursor.fetchall()
    
    conn.close()
    
    # Çekiliş sonucunu session'dan al
    cekilis_sonucu = session.pop('cekilis_sonucu', None)
    
    return render_template('kazananlar.html',
                         toplam_kazanan=toplam_kazanan,
                         kazananlar=kazananlar_listesi,
                         cekilis_sonucu=cekilis_sonucu)

@app.route('/cekilis_yap_genel', methods=['POST'])
def cekilis_yap_genel():
    """Genel çekiliş"""
    kazanan_sayisi = int(request.form['kazanan_sayisi'])
    
    conn = sqlite3.connect('tahminler.db')
    cursor = conn.cursor()
    
    # Tüm kazananları getir
    cursor.execute('''
        SELECT k.id, k.username, m.mac_adi, k.dogru_tahmin, m.gercek_skor
        FROM kazananlar k
        JOIN maclar m ON k.mac_id = m.id
        ORDER BY k.kazanma_tarihi ASC
    ''')
    
    tum_kazananlar = cursor.fetchall()
    
    if len(tum_kazananlar) < kazanan_sayisi:
        flash(f'❌ Yeterli kazanan yok! Mevcut: {len(tum_kazananlar)}, İstenen: {kazanan_sayisi}', 'error')
        conn.close()
        return redirect(url_for('kazananlar'))
    
    # Rastgele seç
    secilen_kazananlar = random.sample(tum_kazananlar, kazanan_sayisi)
    
    # Session'a kaydet
    session['cekilis_sonucu'] = [
        {
            'username': k[1],
            'mac_adi': k[2],
            'tahmin': k[3],
            'gercek_skor': k[4]
        } for k in secilen_kazananlar
    ]
    
    conn.close()
    
    # Başarı mesajı
    kazanan_isimleri = [k[1] for k in secilen_kazananlar]
    flash(f'🎉 Çekiliş tamamlandı! {kazanan_sayisi} kazanan seçildi: {", ".join(["@" + isim for isim in kazanan_isimleri])}', 'success')
    
    # Konsol logu
    print_colored(f"🎉 Genel çekiliş tamamlandı!", Colors.GREEN + Colors.BOLD)
    print_colored(f"📊 Toplam Kazanan: {len(tum_kazananlar)}", Colors.CYAN)
    print_colored(f"🏆 Seçilen Sayı: {kazanan_sayisi}", Colors.YELLOW)
    print_colored("🎯 Seçilen Kazananlar:", Colors.GREEN)
    for i, kazanan in enumerate(secilen_kazananlar, 1):
        print_colored(f"   {i}. @{kazanan[1]} - {kazanan[2]}", Colors.GREEN)
    
    return redirect(url_for('kazananlar'))

@app.route('/cekilis_yap/<int:mac_id>', methods=['GET', 'POST'])
def cekilis_yap(mac_id):
    """Geliştirilmiş çekiliş yapma"""
    conn = sqlite3.connect('tahminler.db')
    cursor = conn.cursor()
    
    # Maç bilgisi
    cursor.execute('SELECT mac_adi FROM maclar WHERE id=?', (mac_id,))
    mac_info = cursor.fetchone()
    mac_adi = mac_info[0] if mac_info else 'Bilinmeyen Maç'
    
    if request.method == 'POST':
        kazanan_sayisi = int(request.form['kazanan_sayisi'])
        
        # Çekiliş için uygun kazananları getir
        cursor.execute('''
            SELECT id, username, user_id FROM kazananlar 
            WHERE mac_id = ? AND cekilis_durumu IN ('otomatik', 'beklemede')
            ORDER BY kazanma_tarihi ASC
        ''', (mac_id,))
        
        uygun_kazananlar = cursor.fetchall()
        
        if len(uygun_kazananlar) < kazanan_sayisi:
            flash(f'❌ Çekiliş için yeterli kazanan yok! Mevcut: {len(uygun_kazananlar)}, İstenen: {kazanan_sayisi}', 'error')
            conn.close()
            return redirect(url_for('cekilis_yap', mac_id=mac_id))
        
        # Rastgele kazananları seç
        secilen_kazananlar = random.sample(uygun_kazananlar, kazanan_sayisi)
        secilen_ids = [k[0] for k in secilen_kazananlar]
        
        # Çekiliş sonuçlarını güncelle
        cursor.execute('''
            UPDATE kazananlar 
            SET cekilis_durumu = 'kaybetti'
            WHERE mac_id = ? AND cekilis_durumu IN ('otomatik', 'beklemede')
        ''', (mac_id,))
        
        # Seçilenleri kazandı yap
        if secilen_ids:
            placeholders = ','.join(['?' for _ in secilen_ids])
            cursor.execute(f'''
                UPDATE kazananlar 
                SET cekilis_durumu = 'kazandi'
                WHERE id IN ({placeholders})
            ''', secilen_ids)
        
        conn.commit()
        conn.close()
        
        # Başarı mesajı
        kazanan_isimleri = [k[1] for k in secilen_kazananlar]
        flash(f'🎉 Çekiliş tamamlandı! {kazanan_sayisi} kazanan seçildi: {", ".join(["@" + isim for isim in kazanan_isimleri])}', 'success')
        
        return redirect(url_for('kazananlar'))
    
    # GET isteği - Çekiliş sayfasını göster
    cursor.execute('''
        SELECT COUNT(*) FROM kazananlar 
        WHERE mac_id = ? AND cekilis_durumu IN ('otomatik', 'beklemede')
    ''', (mac_id,))
    
    uygun_kazanan_sayisi = cursor.fetchone()[0]
    
    # Mevcut kazananları göster
    cursor.execute('''
        SELECT username, cekilis_durumu, kazanma_tarihi FROM kazananlar 
        WHERE mac_id = ? 
        ORDER BY 
            CASE cekilis_durumu 
                WHEN 'kazandi' THEN 1 
                WHEN 'otomatik' THEN 2 
                WHEN 'beklemede' THEN 3 
                ELSE 4 
            END,
            kazanma_tarihi ASC
    ''', (mac_id,))
    
    tum_kazananlar = cursor.fetchall()
    conn.close()
    
    return render_template('cekilis.html', 
                         mac_id=mac_id,
                         mac_adi=mac_adi,
                         uygun_kazanan_sayisi=uygun_kazanan_sayisi,
                         tum_kazananlar=tum_kazananlar)

@app.route('/kazanan_ekle/<int:mac_id>', methods=['POST'])
def kazanan_ekle(mac_id):
    """Manuel kazanan ekleme"""
    username = request.form['username']
    user_id = request.form.get('user_id', 0)
    
    conn = sqlite3.connect('tahminler.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO kazananlar (mac_id, user_id, username, dogru_tahmin, cekilis_durumu)
        VALUES (?, ?, ?, 'Manuel Eklendi', 'manuel')
    ''', (mac_id, user_id, username))
    
    conn.commit()
    conn.close()
    
    flash(f'✅ @{username} manuel olarak kazanan listesine eklendi!', 'success')
    return redirect(url_for('kazananlar'))

@app.route('/kazanan_sil/<int:kazanan_id>')
def kazanan_sil(kazanan_id):
    """Kazanan silme"""
    conn = sqlite3.connect('tahminler.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT mac_id, username FROM kazananlar WHERE id=?', (kazanan_id,))
    kazanan_info = cursor.fetchone()
    
    cursor.execute('DELETE FROM kazananlar WHERE id=?', (kazanan_id,))
    conn.commit()
    conn.close()
    
    if kazanan_info:
        flash(f'✅ @{kazanan_info[1]} kazanan listesinden çıkarıldı!', 'success')
        return redirect(url_for('kazananlar'))
    
    return redirect(url_for('kazananlar'))

@app.route('/api/stats')
def api_stats():
    """API - İstatistikler"""
    conn = sqlite3.connect('tahminler.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM maclar WHERE durum='aktif'")
    aktif_maclar = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM tahminler")
    toplam_tahminler = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM tahminler")
    toplam_kullanicilar = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'aktif_maclar': aktif_maclar,
        'toplam_tahminler': toplam_tahminler,
        'toplam_kullanicilar': toplam_kullanicilar
    })

# Production için main fonksiyonu
if __name__ == '__main__':
    print_colored("🌐 Web Yönetim Paneli Başlatılıyor...", Colors.CYAN + Colors.BOLD)
    print_colored("="*50, Colors.CYAN)
    
    # Veritabanını başlat
    init_web_database()
    
    # Production için port ayarı
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    
    if debug_mode:
        print_colored("🚀 Flask sunucusu başlatılıyor...", Colors.YELLOW)
        print_colored("📱 Panel Adresi: http://localhost:5000", Colors.GREEN + Colors.BOLD)
        print_colored("🔧 Geliştirici Modu: Aktif", Colors.BLUE)
        print_colored("="*50, Colors.CYAN)
    
    app.run(debug=debug_mode, host='0.0.0.0', port=port)

