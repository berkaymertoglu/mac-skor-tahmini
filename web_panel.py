from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import os
import psycopg2
import psycopg2.extras
import sqlite3
import json
import random
from datetime import datetime, timedelta

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

def get_db_connection():
    """PostgreSQL veya SQLite bağlantısı"""
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        # Production: PostgreSQL
        return psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        # Development: SQLite
        return sqlite3.connect('tahminler.db')

def init_web_database():
    """PostgreSQL için veritabanı tablolarını oluştur"""
    print_colored("🗄️ PostgreSQL veritabanı başlatılıyor...", Colors.YELLOW)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    is_postgres = os.environ.get('DATABASE_URL') is not None
    
    if is_postgres:
        # PostgreSQL syntax
        # Maçlar tablosu
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS maclar (
                id SERIAL PRIMARY KEY,
                mac_adi VARCHAR(200) NOT NULL,
                takim1 VARCHAR(100) NOT NULL,
                takim2 VARCHAR(100) NOT NULL,
                mac_tarihi TIMESTAMP,
                gercek_skor VARCHAR(20),
                durum VARCHAR(20) DEFAULT 'aktif',
                olusturma_tarihi TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tahminler tablosu
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tahminler (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                username VARCHAR(100),
                mac_adi VARCHAR(200),
                skor_tahmini VARCHAR(20),
                mac_id INTEGER REFERENCES maclar(id),
                tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Kazananlar tablosu
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS kazananlar (
                id SERIAL PRIMARY KEY,
                mac_id INTEGER REFERENCES maclar(id),
                user_id BIGINT,
                username VARCHAR(100),
                dogru_tahmin VARCHAR(20),
                kazanma_tarihi TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                cekilis_durumu VARCHAR(20) DEFAULT 'beklemede'
            )
        ''')
        
        print_colored("✅ PostgreSQL tabloları oluşturuldu!", Colors.GREEN)
        
    else:
        # SQLite syntax (local development)
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
    print_colored("✅ Veritabanı hazır!", Colors.GREEN)

@app.route('/')
def dashboard():
    """Ana dashboard - PostgreSQL uyumlu"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # İstatistikler
    cursor.execute("SELECT COUNT(*) FROM maclar WHERE durum='aktif'")
    aktif_maclar = cursor.fetchone()[0] if not os.environ.get('DATABASE_URL') else cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) FROM tahminler")
    toplam_tahminler = cursor.fetchone()[0] if not os.environ.get('DATABASE_URL') else cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM tahminler")
    toplam_kullanicilar = cursor.fetchone()[0] if not os.environ.get('DATABASE_URL') else cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) FROM kazananlar")
    toplam_kazananlar = cursor.fetchone()[0] if not os.environ.get('DATABASE_URL') else cursor.fetchone()['count']
    
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
    """Maç listesi - PostgreSQL uyumlu"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT m.id, m.mac_adi, m.takim1, m.takim2, m.mac_tarihi, 
               m.gercek_skor, m.durum, COUNT(t.id) as tahmin_sayisi
        FROM maclar m
        LEFT JOIN tahminler t ON m.id = t.mac_id
        GROUP BY m.id, m.mac_adi, m.takim1, m.takim2, m.mac_tarihi, m.gercek_skor, m.durum
        ORDER BY m.olusturma_tarihi DESC
    ''')
    
    maclar_listesi = cursor.fetchall()
    conn.close()
    
    return render_template('maclar.html', maclar=maclar_listesi)

@app.route('/mac_ekle', methods=['GET', 'POST'])
def mac_ekle():
    """Yeni maç ekleme - PostgreSQL uyumlu"""
    if request.method == 'POST':
        takim1 = request.form['takim1']
        takim2 = request.form['takim2']
        mac_tarihi = request.form['mac_tarihi']
        
        mac_adi = f"{takim1}-{takim2}"
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO maclar (mac_adi, takim1, takim2, mac_tarihi)
            VALUES (%s, %s, %s, %s)
        ''' if os.environ.get('DATABASE_URL') else '''
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
    """Maç düzenleme - PostgreSQL uyumlu"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        takim1 = request.form['takim1']
        takim2 = request.form['takim2']
        mac_tarihi = request.form['mac_tarihi']
        gercek_skor = request.form['gercek_skor']
        durum = request.form['durum']
        
        mac_adi = f"{takim1}-{takim2}"
        
        # Eski maç bilgisini al
        cursor.execute('SELECT gercek_skor, mac_adi FROM maclar WHERE id=%s' if os.environ.get('DATABASE_URL') else 'SELECT gercek_skor, mac_adi FROM maclar WHERE id=?', (mac_id,))
        eski_mac = cursor.fetchone()
        eski_gercek_skor = eski_mac['gercek_skor'] if os.environ.get('DATABASE_URL') else eski_mac[0] if eski_mac else None
        eski_mac_adi = eski_mac['mac_adi'] if os.environ.get('DATABASE_URL') else eski_mac[1] if eski_mac else None
        
        # Maçı güncelle
        cursor.execute('''
            UPDATE maclar 
            SET mac_adi=%s, takim1=%s, takim2=%s, mac_tarihi=%s, gercek_skor=%s, durum=%s
            WHERE id=%s
        ''' if os.environ.get('DATABASE_URL') else '''
            UPDATE maclar 
            SET mac_adi=?, takim1=?, takim2=?, mac_tarihi=?, gercek_skor=?, durum=?
            WHERE id=?
        ''', (mac_adi, takim1, takim2, mac_tarihi, gercek_skor, durum, mac_id))
        
        # Eğer gerçek skor yeni girildiyse, otomatik kazananları belirle
        if gercek_skor and gercek_skor != eski_gercek_skor:
            print_colored(f"🎯 Gerçek skor güncellendi: {mac_adi} - {gercek_skor}", Colors.YELLOW)
            
            # Doğru tahmin yapanları bul
            cursor.execute('''
                SELECT DISTINCT user_id, username, skor_tahmini, mac_adi
                FROM tahminler
                WHERE (mac_id = %s OR mac_adi = %s OR mac_adi = %s) 
                AND skor_tahmini = %s
            ''' if os.environ.get('DATABASE_URL') else '''
                SELECT DISTINCT user_id, username, skor_tahmini, mac_adi
                FROM tahminler
                WHERE (mac_id = ? OR mac_adi = ? OR mac_adi = ?) 
                AND skor_tahmini = ?
            ''', (mac_id, mac_adi, eski_mac_adi, gercek_skor))
            
            dogru_tahminler = cursor.fetchall()
            
            if dogru_tahminler:
                # Mevcut kazananları temizle
                cursor.execute('DELETE FROM kazananlar WHERE mac_id = %s' if os.environ.get('DATABASE_URL') else 'DELETE FROM kazananlar WHERE mac_id = ?', (mac_id,))
                
                # Yeni kazananları ekle
                kazanan_sayisi = 0
                for tahmin in dogru_tahminler:
                    if os.environ.get('DATABASE_URL'):
                        user_id, username, skor_tahmini_user, tahmin_mac_adi = tahmin['user_id'], tahmin['username'], tahmin['skor_tahmini'], tahmin['mac_adi']
                    else:
                        user_id, username, skor_tahmini_user, tahmin_mac_adi = tahmin
                    
                    cursor.execute('''
                        SELECT COUNT(*) FROM kazananlar 
                        WHERE mac_id = %s AND user_id = %s
                    ''' if os.environ.get('DATABASE_URL') else '''
                        SELECT COUNT(*) FROM kazananlar 
                        WHERE mac_id = ? AND user_id = ?
                    ''', (mac_id, user_id))
                    
                    count_result = cursor.fetchone()
                    count = count_result['count'] if os.environ.get('DATABASE_URL') else count_result[0]
                    
                    if count == 0:
                        cursor.execute('''
                            INSERT INTO kazananlar (mac_id, user_id, username, dogru_tahmin, cekilis_durumu)
                            VALUES (%s, %s, %s, %s, 'otomatik')
                        ''' if os.environ.get('DATABASE_URL') else '''
                            INSERT INTO kazananlar (mac_id, user_id, username, dogru_tahmin, cekilis_durumu)
                            VALUES (?, ?, ?, ?, 'otomatik')
                        ''', (mac_id, user_id, username, skor_tahmini_user))
                        kazanan_sayisi += 1
                        print_colored(f"✅ Kazanan eklendi: @{username} - {skor_tahmini_user}", Colors.GREEN)
                
                flash(f'✅ {mac_adi} maçı güncellendi! {kazanan_sayisi} kazanan otomatik belirlendi!', 'success')
            else:
                flash(f'✅ {mac_adi} maçı güncellendi! (Doğru tahmin yapan bulunamadı)', 'info')
        else:
            flash(f'✅ {mac_adi} maçı güncellendi!', 'success')
        
        conn.commit()
        conn.close()
        
        return redirect(url_for('maclar'))
    
    # Maç bilgilerini getir
    cursor.execute('SELECT * FROM maclar WHERE id=%s' if os.environ.get('DATABASE_URL') else 'SELECT * FROM maclar WHERE id=?', (mac_id,))
    mac = cursor.fetchone()
    conn.close()
    
    if not mac:
        flash('❌ Maç bulunamadı!', 'error')
        return redirect(url_for('maclar'))
    
    return render_template('mac_duzenle.html', mac=mac)

# Diğer route'lar da benzer şekilde güncellenecek...

if __name__ == '__main__':
    print_colored("🌐 PostgreSQL Web Yönetim Paneli Başlatılıyor...", Colors.CYAN + Colors.BOLD)
    
    # Veritabanını başlat
    init_web_database()
    
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    
    app.run(debug=debug_mode, host='0.0.0.0', port=port)
