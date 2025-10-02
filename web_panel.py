from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import os
import psycopg2
import psycopg2.extras
import json
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv
import hashlib
from functools import wraps
from bot import init_database


load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'mac-tahmin-super-secret-key-2024-render')

# Bu satırı ekleyin:
@app.context_processor
def inject_user():
    """Template'lere kullanıcı bilgilerini enjekte et"""
    return dict(current_user=get_current_user())

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
    """PostgreSQL bağlantısı"""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise Exception("DATABASE_URL environment variable is required!")
    return psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)

def hash_password(password):
    """Şifreyi hash'le"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, hash_value):
    """Şifreyi doğrula"""
    return hash_password(password) == hash_value

def login_required(f):
    """Giriş yapma zorunluluğu decorator'ı"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    """Mevcut kullanıcı bilgilerini getir"""
    if 'user_id' not in session:
        return None
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT id, kullanici_adi, tam_isim, yetki_seviyesi 
            FROM yoneticiler 
            WHERE id = %s AND aktif = true
        ''', (session['user_id'],))
        
        user = cursor.fetchone()
        return user
    except Exception as e:
        print_colored(f"❌ Kullanıcı bilgisi alınamadı: {e}", Colors.RED)
        return None
    finally:
        conn.close()

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Giriş yapma sayfası"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        kullanici_adi = request.form['kullanici_adi'].strip()
        sifre = request.form['sifre']
        
        if not kullanici_adi or not sifre:
            flash('❌ Kullanıcı adı ve şifre gereklidir!', 'error')
            return render_template('login.html')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT id, kullanici_adi, sifre_hash, tam_isim, yetki_seviyesi, aktif
                FROM yoneticiler 
                WHERE kullanici_adi = %s
            ''', (kullanici_adi,))
            
            user = cursor.fetchone()
            
            if user and user['aktif'] and verify_password(sifre, user['sifre_hash']):
                # Giriş başarılı
                session['user_id'] = user['id']
                session['kullanici_adi'] = user['kullanici_adi']
                session['tam_isim'] = user['tam_isim']
                session['yetki_seviyesi'] = user['yetki_seviyesi']
                
                # Son giriş tarihini güncelle
                cursor.execute('''
                    UPDATE yoneticiler 
                    SET son_giris = CURRENT_TIMESTAMP 
                    WHERE id = %s
                ''', (user['id'],))
                
                conn.commit()
                
                flash(f'✅ Hoş geldiniz, {user["tam_isim"] or user["kullanici_adi"]}!', 'success')
                print_colored(f"✅ Giriş yapıldı: {user['kullanici_adi']} ({user['tam_isim']})", Colors.GREEN)
                
                return redirect(url_for('dashboard'))
            else:
                flash('❌ Geçersiz kullanıcı adı veya şifre!', 'error')
                print_colored(f"🚫 Başarısız giriş denemesi: {kullanici_adi}", Colors.RED)
                
        except Exception as e:
            flash('❌ Giriş sırasında bir hata oluştu!', 'error')
            print_colored(f"❌ Giriş hatası: {e}", Colors.RED)
        finally:
            conn.close()
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Çıkış yapma"""
    kullanici_adi = session.get('kullanici_adi', 'Bilinmeyen')
    session.clear()
    flash('✅ Başarıyla çıkış yaptınız!', 'info')
    print_colored(f"👋 Çıkış yapıldı: {kullanici_adi}", Colors.YELLOW)
    return redirect(url_for('login'))

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Şifre değiştirme"""
    if request.method == 'POST':
        eski_sifre = request.form['eski_sifre']
        yeni_sifre = request.form['yeni_sifre']
        yeni_sifre_tekrar = request.form['yeni_sifre_tekrar']
        
        if not all([eski_sifre, yeni_sifre, yeni_sifre_tekrar]):
            flash('❌ Tüm alanları doldurun!', 'error')
            return render_template('change_password.html')
        
        if yeni_sifre != yeni_sifre_tekrar:
            flash('❌ Yeni şifreler eşleşmiyor!', 'error')
            return render_template('change_password.html')
        
        if len(yeni_sifre) < 6:
            flash('❌ Yeni şifre en az 6 karakter olmalıdır!', 'error')
            return render_template('change_password.html')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Mevcut şifreyi kontrol et
            cursor.execute('''
                SELECT sifre_hash FROM yoneticiler 
                WHERE id = %s
            ''', (session['user_id'],))
            
            user = cursor.fetchone()
            
            if not user or not verify_password(eski_sifre, user['sifre_hash']):
                flash('❌ Mevcut şifre yanlış!', 'error')
                return render_template('change_password.html')
            
            # Yeni şifreyi kaydet
            yeni_sifre_hash = hash_password(yeni_sifre)
            cursor.execute('''
                UPDATE yoneticiler 
                SET sifre_hash = %s 
                WHERE id = %s
            ''', (yeni_sifre_hash, session['user_id']))
            
            conn.commit()
            
            flash('✅ Şifreniz başarıyla değiştirildi!', 'success')
            print_colored(f"🔐 Şifre değiştirildi: {session['kullanici_adi']}", Colors.GREEN)
            
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            conn.rollback()
            flash('❌ Şifre değiştirme sırasında hata oluştu!', 'error')
            print_colored(f"❌ Şifre değiştirme hatası: {e}", Colors.RED)
        finally:
            conn.close()
    
    return render_template('change_password.html')


@app.route('/')
@login_required
def dashboard():
    """Ana dashboard"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # İstatistikler
    cursor.execute("SELECT COUNT(*) FROM maclar WHERE durum='aktif'")
    aktif_maclar = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) FROM tahminler")
    toplam_tahminler = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM tahminler")
    toplam_kullanicilar = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) FROM kazananlar")
    toplam_kazananlar = cursor.fetchone()['count']
    
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
@login_required
def maclar():
    """Maç listesi"""
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

@app.route('/mac_sil/<int:mac_id>')
@login_required
def mac_sil(mac_id):
    """Maç silme - İlişkili verileri de sil"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Maç bilgisini al
    cursor.execute('SELECT mac_adi FROM maclar WHERE id=%s', (mac_id,))
    mac_info = cursor.fetchone()
    
    if not mac_info:
        flash('❌ Maç bulunamadı!', 'error')
        return redirect(url_for('maclar'))
    
    mac_adi = mac_info['mac_adi']
    
    # İlişkili verileri say
    cursor.execute('''
        SELECT COUNT(*) FROM tahminler 
        WHERE mac_id = %s OR mac_adi = %s
    ''', (mac_id, mac_adi))
    tahmin_sayisi = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) FROM kazananlar WHERE mac_id = %s', (mac_id,))
    kazanan_sayisi = cursor.fetchone()['count']
    
    try:
        # İlişkili verileri sil
        cursor.execute('''
            DELETE FROM tahminler 
            WHERE mac_id = %s OR mac_adi = %s
        ''', (mac_id, mac_adi))
        
        cursor.execute('DELETE FROM kazananlar WHERE mac_id = %s', (mac_id,))
        cursor.execute('DELETE FROM maclar WHERE id = %s', (mac_id,))
        
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
@login_required
def mac_ekle():
    """Yeni maç ekleme"""
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
        ''', (mac_adi, takim1, takim2, mac_tarihi))
        
        conn.commit()
        conn.close()
        
        flash(f'✅ {mac_adi} maçı başarıyla eklendi!', 'success')
        print_colored(f"✅ Yeni maç eklendi: {mac_adi}", Colors.GREEN)
        
        return redirect(url_for('maclar'))
    
    return render_template('mac_ekle.html')

@app.route('/mac_duzenle/<int:mac_id>', methods=['GET', 'POST'])
@login_required
def mac_duzenle(mac_id):
    """Maç düzenleme - Gerçek skor girildiğinde otomatik kazanan belirleme"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        takim1 = request.form['takim1']
        takim2 = request.form['takim2']
        mac_tarihi = request.form['mac_tarihi']
        gercek_skor = request.form['gercek_skor']
        durum = request.form['durum']
        
        # ✅ BOŞ DEĞER KONTROLÜ
        mac_tarihi = mac_tarihi if mac_tarihi != '' else None
        gercek_skor = gercek_skor if gercek_skor != '' else None
        
        mac_adi = f"{takim1}-{takim2}"
        
        # Eski maç bilgisini al
        cursor.execute('SELECT gercek_skor, mac_adi FROM maclar WHERE id=%s', (mac_id,))
        eski_mac = cursor.fetchone()
        eski_gercek_skor = eski_mac['gercek_skor'] if eski_mac else None
        eski_mac_adi = eski_mac['mac_adi'] if eski_mac else None
        
        # Maçı güncelle
        cursor.execute('''
            UPDATE maclar 
            SET mac_adi=%s, takim1=%s, takim2=%s, mac_tarihi=%s, gercek_skor=%s, durum=%s
            WHERE id=%s
        ''', (mac_adi, takim1, takim2, mac_tarihi, gercek_skor, durum, mac_id))
        
        # Eğer gerçek skor yeni girildiyse veya değiştiyse, otomatik kazananları belirle
        if gercek_skor and gercek_skor != eski_gercek_skor:
            print_colored(f"🎯 Gerçek skor güncellendi: {mac_adi} - {gercek_skor}", Colors.YELLOW)
            
            # Bu maça tahmin yapan TÜM kullanıcıları bul
            cursor.execute('''
                SELECT DISTINCT user_id, username, skor_tahmini, mac_adi
                FROM tahminler
                WHERE (mac_id = %s OR mac_adi = %s OR mac_adi = %s) 
                AND skor_tahmini = %s
            ''', (mac_id, mac_adi, eski_mac_adi, gercek_skor))
            
            dogru_tahminler = cursor.fetchall()
            
            if dogru_tahminler:
                # Mevcut kazananları temizle
                cursor.execute('DELETE FROM kazananlar WHERE mac_id = %s', (mac_id,))
                
                # Yeni kazananları ekle
                kazanan_sayisi = 0
                for tahmin in dogru_tahminler:
                    user_id, username, skor_tahmini_user, tahmin_mac_adi = tahmin['user_id'], tahmin['username'], tahmin['skor_tahmini'], tahmin['mac_adi']
                    
                    # Aynı kullanıcının birden fazla kaydı varsa sadece bir kez ekle
                    cursor.execute('''
                        SELECT COUNT(*) as count FROM kazananlar 
                        WHERE mac_id = %s AND user_id = %s
                    ''', (mac_id, user_id))
                    
                    if cursor.fetchone()['count'] == 0:
                        cursor.execute('''
                            INSERT INTO kazananlar (mac_id, user_id, username, dogru_tahmin, cekilis_durumu)
                            VALUES (%s, %s, %s, %s, 'otomatik')
                        ''', (mac_id, user_id, username, skor_tahmini_user))
                        kazanan_sayisi += 1
                        print_colored(f"✅ Kazanan eklendi: @{username} - {skor_tahmini_user}", Colors.GREEN)
                
                # Tahminler tablosundaki mac_id'leri de güncelle
                cursor.execute('''
                    UPDATE tahminler 
                    SET mac_id = %s 
                    WHERE (mac_adi = %s OR mac_adi = %s) AND mac_id IS NULL
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
    
    # GET request için - Maç bilgilerini getir
    cursor.execute('SELECT * FROM maclar WHERE id=%s', (mac_id,))
    mac = cursor.fetchone()
    
    if not mac:
        conn.close()
        flash('❌ Maç bulunamadı!', 'error')
        return redirect(url_for('maclar'))
    
    # ✅ TARİH FORMATINI HAZIRLA
    tarih_formatted = ''
    tarih_okunabilir = ''
    
    if mac['mac_tarihi']:
        try:
            # PostgreSQL'den gelen datetime objesi
            if hasattr(mac['mac_tarihi'], 'strftime'):
                # Datetime objesi ise direkt format et
                tarih_formatted = mac['mac_tarihi'].strftime('%Y-%m-%dT%H:%M')
                tarih_okunabilir = mac['mac_tarihi'].strftime('%d.%m.%Y %H:%M')
            elif isinstance(mac['mac_tarihi'], str):
                # String formatında gelen tarihi işle
                if 'T' in mac['mac_tarihi']:
                    # ISO format: 2024-01-15T14:30
                    dt = datetime.fromisoformat(mac['mac_tarihi'].replace('T', ' ').replace('Z', ''))
                elif ' ' in mac['mac_tarihi']:
                    # Normal format: 2024-01-15 14:30:00
                    dt = datetime.strptime(mac['mac_tarihi'], '%Y-%m-%d %H:%M:%S')
                else:
                    # Sadece tarih: 2024-01-15
                    dt = datetime.strptime(mac['mac_tarihi'], '%Y-%m-%d')
                
                tarih_formatted = dt.strftime('%Y-%m-%dT%H:%M')
                tarih_okunabilir = dt.strftime('%d.%m.%Y %H:%M')
                
        except Exception as e:
            print_colored(f"⚠️ Tarih formatı hatası: {e}", Colors.RED)
            tarih_formatted = ''
            tarih_okunabilir = 'Geçersiz tarih formatı'
    
    conn.close()
    
    return render_template('mac_duzenle.html', 
                         mac=mac, 
                         tarih_formatted=tarih_formatted,
                         tarih_okunabilir=tarih_okunabilir)


@app.route('/tahminler')
@login_required
def tahminler():
    """Geliştirilmiş tahminler sayfası - Site kullanıcı adı ile"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Sayfa parametresi
    page = request.args.get('page', 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page
    
    # Filtreleme parametreleri
    mac_filter = request.args.get('mac', '')
    kullanici_filter = request.args.get('kullanici', '')
    durum_filter = request.args.get('durum', '')
    
    # Base query - Site kullanıcı adı ile birleştir
    query = '''
        SELECT t.id, t.username, t.mac_adi, t.skor_tahmini, t.tarih, 
               m.gercek_skor, m.durum,
               k.site_username,
               CASE 
                   WHEN m.gercek_skor IS NULL THEN 'beklemede'
                   WHEN t.skor_tahmini = m.gercek_skor THEN 'dogru'
                   ELSE 'yanlis'
               END as tahmin_durumu
        FROM tahminler t 
        LEFT JOIN maclar m ON (t.mac_id = m.id OR t.mac_adi = m.mac_adi)
        LEFT JOIN kullanicilar k ON t.user_id = k.user_id
        WHERE 1=1
    '''
    
    params = []
    
    # Filtreleri ekle
    if mac_filter:
        query += ' AND t.mac_adi ILIKE %s'
        params.append(f'%{mac_filter}%')
    
    if kullanici_filter:
        query += ' AND (t.username ILIKE %s OR k.site_username ILIKE %s)'
        params.append(f'%{kullanici_filter}%')
        params.append(f'%{kullanici_filter}%')
    
    if durum_filter:
        if durum_filter == 'dogru':
            query += ' AND t.skor_tahmini = m.gercek_skor AND m.gercek_skor IS NOT NULL'
        elif durum_filter == 'yanlis':
            query += ' AND t.skor_tahmini != m.gercek_skor AND m.gercek_skor IS NOT NULL'
        elif durum_filter == 'beklemede':
            query += ' AND m.gercek_skor IS NULL'
    
    # Toplam sayıyı al (count query'yi de güncelle)
    count_query = '''
        SELECT COUNT(*)
        FROM tahminler t 
        LEFT JOIN maclar m ON (t.mac_id = m.id OR t.mac_adi = m.mac_adi)
        LEFT JOIN kullanicilar k ON t.user_id = k.user_id
        WHERE 1=1
    '''
    
    count_params = []
    if mac_filter:
        count_query += ' AND t.mac_adi ILIKE %s'
        count_params.append(f'%{mac_filter}%')
    
    if kullanici_filter:
        count_query += ' AND (t.username ILIKE %s OR k.site_username ILIKE %s)'
        count_params.append(f'%{kullanici_filter}%')
        count_params.append(f'%{kullanici_filter}%')
    
    if durum_filter:
        if durum_filter == 'dogru':
            count_query += ' AND t.skor_tahmini = m.gercek_skor AND m.gercek_skor IS NOT NULL'
        elif durum_filter == 'yanlis':
            count_query += ' AND t.skor_tahmini != m.gercek_skor AND m.gercek_skor IS NOT NULL'
        elif durum_filter == 'beklemede':
            count_query += ' AND m.gercek_skor IS NULL'
    
    cursor.execute(count_query, count_params)
    total = cursor.fetchone()['count']
    
    # Sayfalama ekle
    query += ' ORDER BY t.tarih DESC LIMIT %s OFFSET %s'
    params.extend([per_page, offset])
    
    cursor.execute(query, params)
    tahminler_listesi = cursor.fetchall()
    
    # İstatistikler (değişmedi)
    stats_query = '''
        SELECT 
            COUNT(*) as toplam,
            COUNT(CASE WHEN t.skor_tahmini = m.gercek_skor THEN 1 END) as dogru,
            COUNT(CASE WHEN t.skor_tahmini != m.gercek_skor AND m.gercek_skor IS NOT NULL THEN 1 END) as yanlis,
            COUNT(CASE WHEN m.gercek_skor IS NULL THEN 1 END) as beklemede
        FROM tahminler t 
        LEFT JOIN maclar m ON (t.mac_id = m.id OR t.mac_adi = m.mac_adi)
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
@login_required
def mac_tahminleri(mac_id):
    """Belirli bir maçın tahminleri"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Maç bilgisi
    cursor.execute('SELECT * FROM maclar WHERE id=%s', (mac_id,))
    mac = cursor.fetchone()
    
    # Tahminler
    cursor.execute('''
        SELECT t.id, t.user_id, t.username, t.skor_tahmini, t.tarih
        FROM tahminler t
        WHERE t.mac_id = %s OR t.mac_adi = %s
        ORDER BY t.tarih ASC
    ''', (mac_id, mac['mac_adi'] if mac else ''))
    
    tahminler_listesi = cursor.fetchall()
    
    # Doğru tahminler
    dogru_tahminler = []
    if mac and mac['gercek_skor']:
        gercek_skor = mac['gercek_skor']
        dogru_tahminler = [t for t in tahminler_listesi if t['skor_tahmini'] == gercek_skor]
    
    conn.close()
    
    return render_template('mac_tahminleri.html', 
                         mac=mac, 
                         tahminler=tahminler_listesi,
                         dogru_tahminler=dogru_tahminler)

@app.route('/kazananlari_belirle/<int:mac_id>')
@login_required
def kazananlari_belirle(mac_id):
    """Kazananları otomatik belirle"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Maç bilgisi
    cursor.execute('SELECT * FROM maclar WHERE id=%s', (mac_id,))
    mac = cursor.fetchone()
    
    if not mac or not mac['gercek_skor']:
        flash('❌ Önce maçın gerçek skorunu girin!', 'error')
        return redirect(url_for('mac_tahminleri', mac_id=mac_id))
    
    gercek_skor = mac['gercek_skor']
    
    # Doğru tahmin yapanları bul
    cursor.execute('''
        SELECT user_id, username, skor_tahmini
        FROM tahminler
        WHERE (mac_id = %s OR mac_adi = %s) AND skor_tahmini = %s
    ''', (mac_id, mac['mac_adi'], gercek_skor))
    
    dogru_tahminler = cursor.fetchall()
    
    # Kazananlar tablosunu temizle
    cursor.execute('DELETE FROM kazananlar WHERE mac_id = %s', (mac_id,))
    
    # Kazananları ekle
    for tahmin in dogru_tahminler:
        cursor.execute('''
            INSERT INTO kazananlar (mac_id, user_id, username, dogru_tahmin)
            VALUES (%s, %s, %s, %s)
        ''', (mac_id, tahmin['user_id'], tahmin['username'], tahmin['skor_tahmini']))
    
    conn.commit()
    conn.close()
    
    flash(f'✅ {len(dogru_tahminler)} kazanan belirlendi!', 'success')
    print_colored(f"✅ {mac['mac_adi']} maçı için {len(dogru_tahminler)} kazanan belirlendi", Colors.GREEN)
    
    return redirect(url_for('kazananlar', mac_id=mac_id))

@app.route('/kazananlar')
@login_required
def kazananlar():
    """Kazananlar sayfası - Site kullanıcı adı ile"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Kazananları getir - site kullanıcı adı ile birleştir
    cursor.execute('''
        SELECT 
            t.id,
            t.username,
            COALESCE(k.site_username, '') as site_username,
            t.mac_adi,
            t.skor_tahmini as dogru_tahmin,
            m.gercek_skor,
            t.tarih as tahmin_tarihi,
            m.mac_tarihi
        FROM tahminler t
        LEFT JOIN maclar m ON t.mac_adi = m.mac_adi
        LEFT JOIN kullanicilar k ON t.user_id = k.user_id
        WHERE m.gercek_skor IS NOT NULL 
        AND t.skor_tahmini = m.gercek_skor
        ORDER BY t.tarih DESC
    ''')
    
    kazananlar_list = cursor.fetchall()
    
    # Toplam kazanan sayısı
    toplam_kazanan = len(kazananlar_list)
    
    conn.close()
    
    return render_template('kazananlar.html', 
                         kazananlar=kazananlar_list, 
                         toplam_kazanan=toplam_kazanan)






@app.route('/cekilis_yap_genel', methods=['POST'])
@login_required
def cekilis_yap_genel():
    """Genel çekiliş"""
    kazanan_sayisi = int(request.form['kazanan_sayisi'])
    
    conn = get_db_connection()
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
            'username': k['username'],
            'mac_adi': k['mac_adi'],
            'tahmin': k['dogru_tahmin'],
            'gercek_skor': k['gercek_skor']
        } for k in secilen_kazananlar
    ]
    
    conn.close()
    
    # Başarı mesajı
    kazanan_isimleri = [k['username'] for k in secilen_kazananlar]
    flash(f'🎉 Çekiliş tamamlandı! {kazanan_sayisi} kazanan seçildi: {", ".join(["@" + isim for isim in kazanan_isimleri])}', 'success')
    
    # Konsol logu
    print_colored(f"🎉 Genel çekiliş tamamlandı!", Colors.GREEN + Colors.BOLD)
    print_colored(f"📊 Toplam Kazanan: {len(tum_kazananlar)}", Colors.CYAN)
    print_colored(f"🏆 Seçilen Sayı: {kazanan_sayisi}", Colors.YELLOW)
    print_colored("🎯 Seçilen Kazananlar:", Colors.GREEN)
    for i, kazanan in enumerate(secilen_kazananlar, 1):
        print_colored(f"   {i}. @{kazanan['username']} - {kazanan['mac_adi']}", Colors.GREEN)
    
    return redirect(url_for('kazananlar'))

@app.route('/cekilis_yap/<int:mac_id>', methods=['GET', 'POST'])
@login_required
def cekilis_yap(mac_id):
    """Geliştirilmiş çekiliş yapma"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Maç bilgisi
    cursor.execute('SELECT mac_adi FROM maclar WHERE id=%s', (mac_id,))
    mac_info = cursor.fetchone()
    mac_adi = mac_info['mac_adi'] if mac_info else 'Bilinmeyen Maç'
    
    if request.method == 'POST':
        kazanan_sayisi = int(request.form['kazanan_sayisi'])
        
        # Çekiliş için uygun kazananları getir
        cursor.execute('''
            SELECT id, username, user_id FROM kazananlar 
            WHERE mac_id = %s AND cekilis_durumu IN ('otomatik', 'beklemede')
            ORDER BY kazanma_tarihi ASC
        ''', (mac_id,))
        
        uygun_kazananlar = cursor.fetchall()
        
        if len(uygun_kazananlar) < kazanan_sayisi:
            flash(f'❌ Çekiliş için yeterli kazanan yok! Mevcut: {len(uygun_kazananlar)}, İstenen: {kazanan_sayisi}', 'error')
            conn.close()
            return redirect(url_for('cekilis_yap', mac_id=mac_id))
        
        # Rastgele kazananları seç
        secilen_kazananlar = random.sample(uygun_kazananlar, kazanan_sayisi)
        secilen_ids = [k['id'] for k in secilen_kazananlar]
        
        # Çekiliş sonuçlarını güncelle
        cursor.execute('''
            UPDATE kazananlar 
            SET cekilis_durumu = 'kaybetti'
            WHERE mac_id = %s AND cekilis_durumu IN ('otomatik', 'beklemede')
        ''', (mac_id,))

                # Seçilenleri kazandı yap
        if secilen_ids:
            cursor.execute('''
                UPDATE kazananlar 
                SET cekilis_durumu = 'kazandi'
                WHERE id = ANY(%s)
            ''', (secilen_ids,))
        
        conn.commit()
        conn.close()
        
        # Başarı mesajı
        kazanan_isimleri = [k['username'] for k in secilen_kazananlar]
        flash(f'🎉 Çekiliş tamamlandı! {kazanan_sayisi} kazanan seçildi: {", ".join(["@" + isim for isim in kazanan_isimleri])}', 'success')
        
        return redirect(url_for('kazananlar'))
    
    # GET isteği - Çekiliş sayfasını göster
    cursor.execute('''
        SELECT COUNT(*) FROM kazananlar 
        WHERE mac_id = %s AND cekilis_durumu IN ('otomatik', 'beklemede')
    ''', (mac_id,))
    
    uygun_kazanan_sayisi = cursor.fetchone()['count']
    
    # Mevcut kazananları göster
    cursor.execute('''
        SELECT username, cekilis_durumu, kazanma_tarihi FROM kazananlar 
        WHERE mac_id = %s 
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

@app.route('/kazanan_ekle_manuel', methods=['GET', 'POST'])
@login_required
def kazanan_ekle_manuel():
    """Manuel kazanan ekleme sayfası"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        username = request.form['username'].strip()
        site_username = request.form.get('site_username', '').strip()
        mac_id = int(request.form['mac_id'])
        dogru_tahmin = request.form['dogru_tahmin'].strip()
        gercek_skor = request.form.get('gercek_skor', '').strip()
        tahmin_tarihi = request.form.get('tahmin_tarihi', '')
        user_id = request.form.get('user_id', '')
        cekilis_durumu = request.form.get('cekilis_durumu', 'manuel')
        aciklama = request.form.get('aciklama', '').strip()
        
        # Değer kontrolü
        user_id = int(user_id) if user_id else None
        gercek_skor = gercek_skor if gercek_skor else None
        site_username = site_username if site_username else None
        tahmin_tarihi = tahmin_tarihi if tahmin_tarihi else datetime.now()
        
        try:
            # Maç bilgisini al
            cursor.execute('SELECT mac_adi, gercek_skor FROM maclar WHERE id=%s', (mac_id,))
            mac_info = cursor.fetchone()
            
            if not mac_info:
                flash('❌ Seçilen maç bulunamadı!', 'error')
                return redirect(url_for('kazanan_ekle_manuel'))
            
            mac_adi = mac_info['mac_adi']
            mac_gercek_skor = gercek_skor or mac_info['gercek_skor']
            
            # User ID yoksa rastgele bir ID oluştur
            if not user_id:
                import time
                user_id = int(time.time() * 1000) % 1000000000
            
            # Önce tahminler tablosuna ekle
            cursor.execute('''
                INSERT INTO tahminler (user_id, username, mac_id, mac_adi, skor_tahmini, tarih)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (user_id, username, mac_id, mac_adi, dogru_tahmin, tahmin_tarihi))
            
            tahmin_id = cursor.fetchone()['id']
            
            # Site kullanıcı adını kullanicilar tablosuna ekle/güncelle
            if site_username:
                cursor.execute('''
                    INSERT INTO kullanicilar (user_id, telegram_username, site_username, kayit_tarihi)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id) 
                    DO UPDATE SET 
                        site_username = EXCLUDED.site_username,
                        telegram_username = EXCLUDED.telegram_username,
                        kayit_tarihi = EXCLUDED.kayit_tarihi
                ''', (user_id, username, site_username, datetime.now()))
                
                print_colored(f"✅ Site kullanıcı adı kaydedildi: {site_username}", Colors.GREEN)
            
            conn.commit()
            
            flash(f'✅ @{username} başarıyla kazanan olarak eklendi! ({mac_adi})', 'success')
            print_colored(f"✅ Manuel kazanan eklendi: @{username} - {mac_adi} - {dogru_tahmin}", Colors.GREEN)
            
            return redirect(url_for('kazananlar'))
            
        except Exception as e:
            conn.rollback()
            flash(f'❌ Kazanan eklenirken hata oluştu: {str(e)}', 'error')
            print_colored(f"❌ Manuel kazanan ekleme hatası: {str(e)}", Colors.RED)
    
    # GET request - Form sayfasını göster
    cursor.execute('SELECT id, mac_adi, takim1, takim2, gercek_skor FROM maclar ORDER BY olusturma_tarihi DESC')
    maclar_listesi = cursor.fetchall()
    
    conn.close()
    
    return render_template('kazanan_ekle.html', maclar=maclar_listesi, datetime=datetime)



@app.route('/kazanan_sil_genel/<int:kazanan_id>')
@login_required
def kazanan_sil_genel(kazanan_id):
    """Genel kazanan silme - tahminler tablosundan da sil"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Kazanan bilgisini al
        cursor.execute('''
            SELECT t.id as tahmin_id, t.username, t.mac_adi, t.user_id
            FROM tahminler t
            WHERE t.id = %s
        ''', (kazanan_id,))
        
        kazanan_info = cursor.fetchone()
        
        if kazanan_info:
            username = kazanan_info['username']
            mac_adi = kazanan_info['mac_adi']
            
            # Tahminler tablosundan sil
            cursor.execute('DELETE FROM tahminler WHERE id = %s', (kazanan_id,))
            
            # Kazananlar tablosundan da sil (eğer varsa)
            cursor.execute('DELETE FROM kazananlar WHERE user_id = %s AND username = %s', 
                         (kazanan_info['user_id'], username))
            
            conn.commit()
            flash(f'✅ @{username} kazanan listesinden çıkarıldı! ({mac_adi})', 'success')
            print_colored(f"🗑️ Kazanan silindi: @{username} - {mac_adi}", Colors.RED)
        else:
            flash('❌ Kazanan bulunamadı!', 'error')
            
    except Exception as e:
        conn.rollback()
        flash(f'❌ Kazanan silinirken hata oluştu: {str(e)}', 'error')
        print_colored(f"❌ Kazanan silme hatası: {str(e)}", Colors.RED)
    
    finally:
        conn.close()
    
    return redirect(url_for('kazananlar'))


@app.route('/api/stats')
@login_required
def api_stats():
    """API - İstatistikler"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM maclar WHERE durum='aktif'")
    aktif_maclar = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) FROM tahminler")
    toplam_tahminler = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM tahminler")
    toplam_kullanicilar = cursor.fetchone()['count']
    
    conn.close()
    
    return jsonify({
        'aktif_maclar': aktif_maclar,
        'toplam_tahminler': toplam_tahminler,
        'toplam_kullanicilar': toplam_kullanicilar
    })

# Production için main fonksiyonu
if __name__ == '__main__':
    print_colored("🌐 PostgreSQL Web Yönetim Paneli Başlatılıyor...", Colors.CYAN + Colors.BOLD)
    print_colored("="*50, Colors.CYAN)
    
    init_database()

    # Production için port ayarı
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    
    if debug_mode:
        print_colored("🚀 Flask sunucusu başlatılıyor...", Colors.YELLOW)
        print_colored("📱 Panel Adresi: http://localhost:5000", Colors.GREEN + Colors.BOLD)
        print_colored("🔧 Geliştirici Modu: Aktif", Colors.BLUE)
        print_colored("="*50, Colors.CYAN)
    
    app.run(debug=debug_mode, host='0.0.0.0', port=port)
