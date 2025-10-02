import logging
import os
import psycopg2
import psycopg2.extras
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from dotenv import load_dotenv

load_dotenv()

# Logging ayarları
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(levelname)s', level=logging.INFO)

# İzin verilen grup ID'si ve Log kanalı
ALLOWED_GROUP_ID = -4820404006
LOG_CHANNEL_ID = -4814745228

def check_group_permission(func):
    """Sadece belirli grupta çalışmasını sağlayan decorator"""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        chat_type = update.effective_chat.type
        
        if chat_type == 'private':
            await update.message.reply_text(
                "❌ **Bu bot sadece belirli gruplarda çalışır!**\n\n"
                "Lütfen yetkili grupta deneyin.",
                parse_mode='Markdown'
            )
            await send_log(context, f"🚫 **PRIVATE MESAJ GİRİŞİMİ**\n👤 Kullanıcı: @{update.effective_user.username or update.effective_user.first_name}\n🆔 ID: {update.effective_user.id}")
            return
        
        if chat_id != ALLOWED_GROUP_ID:
            await update.message.reply_text(
                "❌ **Bu bot bu grupta çalışma yetkisine sahip değil!**",
                parse_mode='Markdown'
            )
            await send_log(context, f"🚫 **YETKİSİZ GRUP GİRİŞİMİ**\n🏠 Grup: {update.effective_chat.title}\n🆔 Grup ID: {chat_id}\n👤 Kullanıcı: @{update.effective_user.username or update.effective_user.first_name}")
            return
        
        return await func(update, context)
    
    return wrapper

async def send_log(context: ContextTypes.DEFAULT_TYPE, message: str):
    """Log kanalına mesaj gönder"""
    try:
        log_message = f"🤖 **BOT LOG**\n\n{message}\n\n⏰ {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        await context.bot.send_message(
            chat_id=LOG_CHANNEL_ID,
            text=log_message,
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.error(f"Log gönderilemedi: {e}")

def get_db_connection():
    """PostgreSQL bağlantısı"""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise Exception("DATABASE_URL environment variable is required!")
    return psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)

def init_database():
    """Veritabanını başlat ve constraint'leri düzelt"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Maçlar tablosu
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS maclar (
                id SERIAL PRIMARY KEY,
                mac_adi VARCHAR(200) NOT NULL UNIQUE,
                takim1 VARCHAR(100) NOT NULL,
                takim2 VARCHAR(100) NOT NULL,
                mac_tarihi TIMESTAMP,
                durum VARCHAR(20) DEFAULT 'aktif',
                gercek_skor VARCHAR(20),
                olusturma_tarihi TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Kullanıcılar tablosu
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS kullanicilar (
                user_id BIGINT PRIMARY KEY,
                telegram_username VARCHAR(100),
                site_username VARCHAR(50) NOT NULL,
                kayit_tarihi TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tahminler tablosu
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tahminler (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                username VARCHAR(100),
                mac_id INTEGER REFERENCES maclar(id),
                mac_adi VARCHAR(200),
                skor_tahmini VARCHAR(20),
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
                cekilis_durumu VARCHAR(20) DEFAULT 'otomatik',
                kazanma_tarihi TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # YÖNETİCİLER TABLOSU
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS yoneticiler (
                id SERIAL PRIMARY KEY,
                kullanici_adi VARCHAR(50) UNIQUE NOT NULL,
                sifre_hash VARCHAR(255) NOT NULL,
                tam_isim VARCHAR(100),
                yetki_seviyesi VARCHAR(20) DEFAULT 'admin',
                son_giris TIMESTAMP,
                olusturma_tarihi TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                aktif BOOLEAN DEFAULT true
            )
        ''')
        
        # Varsayılan admin kullanıcısı oluştur
        cursor.execute('''
            SELECT COUNT(*) as count FROM yoneticiler WHERE kullanici_adi = 'admin'
        ''')
        
        result = cursor.fetchone()
        if result and result['count'] == 0:
            # hash_password fonksiyonu yoksa basit bir hash yapalım
            import hashlib
            varsayilan_sifre = "admin123"
            sifre_hash = hashlib.sha256(varsayilan_sifre.encode()).hexdigest()
            
            cursor.execute('''
                INSERT INTO yoneticiler (kullanici_adi, sifre_hash, tam_isim, yetki_seviyesi)
                VALUES (%s, %s, %s, %s)
            ''', ('admin', sifre_hash, 'Sistem Yöneticisi', 'super_admin'))
            
            print("✅ Varsayılan admin kullanıcısı oluşturuldu (Kullanıcı: admin, Şifre: admin123)")
        
        # Mevcut unique constraint'i kontrol et - GÜVENLİ YÖNTEM
        cursor.execute('''
            SELECT COUNT(*) as count
            FROM information_schema.table_constraints 
            WHERE table_name = 'tahminler' 
            AND constraint_type = 'UNIQUE'
            AND constraint_name = 'tahminler_user_mac_unique'
        ''')
        
        constraint_result = cursor.fetchone()
        constraint_exists = constraint_result and constraint_result['count'] > 0
        
        # Eğer constraint yoksa ekle
        if not constraint_exists:
            try:
                cursor.execute('''
                    ALTER TABLE tahminler 
                    ADD CONSTRAINT tahminler_user_mac_unique 
                    UNIQUE (user_id, mac_id)
                ''')
                print("✅ UNIQUE constraint eklendi")
            except psycopg2.errors.DuplicateObject:
                # Constraint zaten varsa geç
                print("ℹ️ UNIQUE constraint zaten mevcut")
            except Exception as constraint_error:
                print(f"⚠️ Constraint ekleme hatası (göz ardı edildi): {constraint_error}")
        else:
            print("ℹ️ UNIQUE constraint zaten mevcut")
        
        conn.commit()
        print("✅ Veritabanı başarıyla güncellendi")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Veritabanı hatası: {e}")
        raise e
    finally:
        conn.close()


def kullanici_kayitli_mi(user_id):
    """Kullanıcının site kullanıcı adı kayıtlı mı kontrol et"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT site_username FROM kullanicilar WHERE user_id = %s', (user_id,))
        result = cursor.fetchone()
        return result is not None
    except Exception as e:
        logging.error(f"Kullanıcı kontrol hatası: {e}")
        return False
    finally:
        conn.close()

def kullanici_kaydet(user_id, telegram_username, site_username):
    """Yeni kullanıcıyı kaydet"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO kullanicilar (user_id, telegram_username, site_username)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
            telegram_username = EXCLUDED.telegram_username,
            site_username = EXCLUDED.site_username
        ''', (user_id, telegram_username, site_username))
        conn.commit()
    except Exception as e:
        conn.rollback()
        logging.error(f"Kullanıcı kaydetme hatası: {e}")
        raise e
    finally:
        conn.close()

def get_site_username(user_id):
    """Kullanıcının site kullanıcı adını getir"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT site_username FROM kullanicilar WHERE user_id = %s', (user_id,))
        result = cursor.fetchone()
        return result['site_username'] if result else None
    except Exception as e:
        logging.error(f"Site kullanıcı adı getirme hatası: {e}")
        return None
    finally:
        conn.close()

def get_active_matches():
    """Aktif maçları getir"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, mac_adi, takim1, takim2, mac_tarihi 
        FROM maclar 
        WHERE durum = 'aktif' 
        ORDER BY mac_tarihi ASC, olusturma_tarihi ASC
    ''')
    
    matches = cursor.fetchall()
    conn.close()
    return matches

def check_user_prediction_exists(user_id, mac_id):
    """Kullanıcının bu maça daha önce tahmin yapıp yapmadığını kontrol et"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT id, skor_tahmini FROM tahminler 
            WHERE user_id = %s AND mac_id = %s
        ''', (user_id, mac_id))
        
        existing = cursor.fetchone()
        return existing
        
    except Exception as e:
        logging.error(f"Tahmin kontrol hatası: {e}")
        return None
    finally:
        conn.close()

def save_prediction(user_id, username, mac_id, mac_adi, skor_tahmini):
    """Tahmini veritabanına kaydet - TEK TAHMİN KURALI"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Önce mevcut tahmini kontrol et
        cursor.execute('''
            SELECT id, skor_tahmini FROM tahminler 
            WHERE user_id = %s AND mac_id = %s
        ''', (user_id, mac_id))
        
        existing = cursor.fetchone()
        
        if existing:
            # ❌ ZATEN TAHMİN VAR - GÜNCELLEMEYİ ENGELLE
            return "zaten_var", existing['skor_tahmini']
        else:
            # ✅ YENİ TAHMİN EKLEYEBİLİR
            cursor.execute('''
                INSERT INTO tahminler (user_id, username, mac_id, mac_adi, skor_tahmini)
                VALUES (%s, %s, %s, %s, %s)
            ''', (user_id, username, mac_id, mac_adi, skor_tahmini))
            
            conn.commit()
            return "kaydedildi", None
        
    except Exception as e:
        conn.rollback()
        logging.error(f"Tahmin kaydetme hatası: {e}")
        raise e
    finally:
        conn.close()

def get_user_predictions(user_id):
    """Kullanıcının tahminlerini getir"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT t.mac_adi, t.skor_tahmini, t.tarih, m.gercek_skor, m.durum
        FROM tahminler t 
        LEFT JOIN maclar m ON t.mac_id = m.id
        WHERE t.user_id = %s 
        ORDER BY t.tarih DESC 
        LIMIT 10
    ''', (user_id,))
    
    results = cursor.fetchall()
    conn.close()
    return results

async def handle_site_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Site kullanıcı adını işle"""
    if not context.user_data.get('waiting_for_site_username'):
        return
    
    user_id = update.effective_user.id
    telegram_username = update.effective_user.username or update.effective_user.first_name
    site_username = update.message.text.strip()
    
    # Site kullanıcı adı validasyonu
    if len(site_username) < 3:
        await update.message.reply_text(
            "❌ **Hata!**\n\n"
            "Site kullanıcı adı en az **3 karakter** olmalıdır.\n\n"
            "📝 **Lütfen tekrar yazın:**",
            parse_mode='Markdown'
        )
        return
    
    if len(site_username) > 20:
        await update.message.reply_text(
            "❌ **Hata!**\n\n"
            "Site kullanıcı adı en fazla **20 karakter** olabilir.\n\n"
            "📝 **Lütfen tekrar yazın:**",
            parse_mode='Markdown'
        )
        return
    
    # Özel karakterleri kontrol et
    if not site_username.replace('_', '').replace('-', '').isalnum():
        await update.message.reply_text(
            "❌ **Hata!**\n\n"
            "Site kullanıcı adı sadece **harf, rakam, _ ve -** içerebilir.\n\n"
            "📝 **Lütfen tekrar yazın:**",
            parse_mode='Markdown'
        )
        return
    
    try:
        # Kullanıcıyı kaydet
        kullanici_kaydet(user_id, telegram_username, site_username)
        context.user_data['waiting_for_site_username'] = False
        
        await update.message.reply_text(
            f"✅ **Kayıt Başarılı!**\n\n"
            f"🎯 **Site Kullanıcı Adınız:** `{site_username}`\n\n"
            f"Artık tahmin yapabilirsiniz!\n\n"
            f"🚀 **Tahmin yapmak için:** /tahmin",
            parse_mode='Markdown'
        )
        
        await send_log(context, f"✅ **KULLANICI KAYDI**\n👤 Telegram: @{telegram_username}\n🎯 Site: {site_username}")
        
    except Exception as e:
        await update.message.reply_text(
            "❌ **Kayıt sırasında bir hata oluştu!**\n\n"
            "Lütfen tekrar deneyin veya yönetici ile iletişime geçin.",
            parse_mode='Markdown'
        )
        await send_log(context, f"🚨 **KULLANICI KAYIT HATASI**\n👤 Telegram: @{telegram_username}\n❌ Hata: {str(e)}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tüm mesajları işle"""
    # Site kullanıcı adı bekleniyor mu?
    if context.user_data.get('waiting_for_site_username'):
        await handle_site_username(update, context)
        return

@check_group_permission
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start komutu handler'ı"""
    welcome_text = """
🤖 **Skor Tahmin Botu'na Hoş Geldiniz!** ⚽

📋 **Hızlı Sistem - Tek Tıkla Tahmin:**
/tahmin - Aktif maçları görüntüle ve hızlıca tahmin yap
/tahminlerim - Geçmiş tahminlerinizi görün
/yardim - Kullanım kılavuzu

✅ **Nasıl Çalışır:**
1️⃣ /tahmin yazın
2️⃣ Maçı seçin
3️⃣ Skoru seçin - Hepsi bu kadar!

⚠️ **ÖNEMLİ:** Her maç için sadece **BİR KEZ** tahmin yapabilirsiniz!

🚀 **Hızlı ve Pratik!** Soru-cevap yok, direkt tahmin!
    """
    
    await update.message.reply_text(welcome_text, parse_mode='Markdown')
    await send_log(context, f"🚀 **START KOMUTU KULLANILDI**\n👤 Kullanıcı: @{update.effective_user.username or update.effective_user.first_name}\n🆔 ID: {update.effective_user.id}")

@check_group_permission
async def tahmin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tahmin menüsü - İlk önce kullanıcı kaydını kontrol et"""
    user_id = update.effective_user.id
    telegram_username = update.effective_user.username or update.effective_user.first_name
    
    # Kullanıcı kayıtlı mı kontrol et
    if not kullanici_kayitli_mi(user_id):
        await update.message.reply_text(
            "🎯 **Hoş Geldiniz!**\n\n"
            "İlk tahminizi yapmadan önce **site kullanıcı adınızı** kaydetmeniz gerekiyor.\n\n"
            "📝 **Site kullanıcı adınızı yazın:**\n"
            "*(Örnek: ahmet123, mehmet_futbol, vs.)*\n\n"
            "⚠️ **Not:** Bu bilgi sadece bir kez istenir ve değiştirilemez!",
            parse_mode='Markdown'
        )
        
        # Kullanıcıdan site kullanıcı adını bekle
        context.user_data['waiting_for_site_username'] = True
        await send_log(context, f"🆕 **YENİ KULLANICI**\n👤 Telegram: @{telegram_username}\n📝 Site kullanıcı adı bekleniyor...")
        return
    
    # Normal tahmin menüsüne devam et
    matches = get_active_matches()
    
    if not matches:
        await update.message.reply_text(
            "⚠️ **Şu anda aktif maç bulunmuyor!**\n\n"
            "Yönetici henüz maç eklememiş. Lütfen daha sonra tekrar deneyin.\n"
            "📢 Duyurular için kanalı takip edin!",
            parse_mode='Markdown'
        )
        await send_log(context, f"⚠️ **AKTİF MAÇ YOK**\n👤 Kullanıcı: @{update.effective_user.username or update.effective_user.first_name}")
        return
    
    # Kullanıcının tahmin yaptığı maçları kontrol et
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT mac_id FROM tahminler 
        WHERE user_id = %s
    ''', (user_id,))
    
    tahmin_yapilan_maclar = [row['mac_id'] for row in cursor.fetchall()]
    conn.close()
    
    # Inline keyboard oluştur
    keyboard = []
    tahmin_yapilabilir_mac_sayisi = 0
    
    for match in matches:
        mac_id = match['id']
        mac_adi = match['mac_adi']
        
        # Tarih bilgisi varsa ekle
        tarih_text = ""
        if match['mac_tarihi']:
            try:
                if isinstance(match['mac_tarihi'], str):
                    tarih_obj = datetime.fromisoformat(match['mac_tarihi'].replace('Z', '+00:00'))
                else:
                    tarih_obj = match['mac_tarihi']
                tarih_text = f" ({tarih_obj.strftime('%d.%m %H:%M')})"
            except:
                pass
        
        # Tahmin durumunu kontrol et
        if mac_id in tahmin_yapilan_maclar:
            # Zaten tahmin yapılmış
            button_text = f"✅ {mac_adi}{tarih_text} (Tahmin Yapıldı)"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"already_{mac_id}")])
        else:
            # Tahmin yapılabilir
            button_text = f"⚽ {mac_adi}{tarih_text}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"match_{mac_id}")])
            tahmin_yapilabilir_mac_sayisi += 1
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = f"""
🎯 **Aktif Maçlar** ({len(matches)} adet)

⚽ **Tahmin yapılabilir:** {tahmin_yapilabilir_mac_sayisi} maç
✅ **Tahmin yapıldı:** {len(matches) - tahmin_yapilabilir_mac_sayisi} maç

⚠️ **KURAL:** Her maç için sadece **BİR KEZ** tahmin yapabilirsiniz!

Tahmin yapmak istediğiniz maçı seçin:
    """
    
    await update.message.reply_text(
        message_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

@check_group_permission
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline button handler'ı - Tek tahmin kuralı ile"""
    query = update.callback_query
    
    # Query answer'ı güvenli hale getir
    try:
        await query.answer()
    except Exception as e:
        logging.warning(f"Query answer hatası (göz ardı edildi): {e}")
    
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    if query.data.startswith("already_"):
        # Zaten tahmin yapılmış maça tıklandı
        mac_id = int(query.data.split("_")[1])
        
        # Mevcut tahmini göster
        existing = check_user_prediction_exists(user_id, mac_id)
        
        if existing:
            try:
                await query.answer(
                    f"⚠️ Bu maça zaten tahmin yaptınız: {existing['skor_tahmini']}\n"
                    f"Her maç için sadece BİR tahmin yapabilirsiniz!", 
                    show_alert=True
                )
            except Exception as e:
                logging.warning(f"Alert gösterme hatası: {e}")
                # Alternatif olarak mesaj gönder
                try:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=f"⚠️ Bu maça zaten tahmin yaptınız: {existing['skor_tahmini']}\nHer maç için sadece BİR tahmin yapabilirsiniz!",
                        parse_mode='Markdown'
                    )
                except:
                    pass
        else:
            try:
                await query.answer("❌ Tahmin bulunamadı!", show_alert=True)
            except:
                pass
        
        return
    
    elif query.data.startswith("match_"):
        # Maç seçildi - Skor seçeneklerini göster
        mac_id = int(query.data.split("_")[1])
        
        # Önce kullanıcının bu maça tahmin yapıp yapmadığını kontrol et
        existing = check_user_prediction_exists(user_id, mac_id)
        
        if existing:
            try:
                await query.answer(
                    f"⚠️ Bu maça zaten tahmin yaptınız: {existing['skor_tahmini']}\n"
                    f"Her maç için sadece BİR tahmin yapabilirsiniz!", 
                    show_alert=True
                )
            except Exception as e:
                logging.warning(f"Alert gösterme hatası: {e}")
                # Alternatif mesaj
                try:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=f"⚠️ Bu maça zaten tahmin yaptınız: {existing['skor_tahmini']}\nHer maç için sadece BİR tahmin yapabilirsiniz!",
                        parse_mode='Markdown'
                    )
                except:
                    pass
            return
        
        # Maç bilgisini getir
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM maclar WHERE id = %s AND durum = %s', (mac_id, 'aktif'))
        match = cursor.fetchone()
        conn.close()
        
        if not match:
            try:
                await query.edit_message_text("❌ Maç bulunamadı veya artık aktif değil!")
            except Exception as e:
                logging.warning(f"Mesaj düzenleme hatası: {e}")
            return
        
        # Popüler skor seçenekleri
        score_options = [
            ["0-0", "1-0", "0-1"],
            ["1-1", "2-0", "0-2"],
            ["2-1", "1-2", "2-2"],
            ["3-0", "0-3", "3-1"],
            ["1-3", "3-2", "2-3"],
            ["4-0", "0-4", "4-1"],
            ["1-4", "3-3", "4-2"]
        ]
        
        # Keyboard oluştur
        keyboard = []
        for row in score_options:
            keyboard_row = []
            for score in row:
                keyboard_row.append(InlineKeyboardButton(
                    f"⚽ {score}", 
                    callback_data=f"score_{mac_id}_{score}"
                ))
            keyboard.append(keyboard_row)
        
        # Özel skor girme seçeneği
        keyboard.append([InlineKeyboardButton("✏️ Özel Skor Gir", callback_data=f"custom_{mac_id}")])
        keyboard.append([InlineKeyboardButton("🔙 Geri Dön", callback_data="back_to_matches")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = f"""
🏆 **Seçilen Maç:** {match['mac_adi']}

⚽ **Skor tahminizi seçin:**

⚠️ **DİKKAT:** Bu maç için sadece **BİR KEZ** tahmin yapabilirsiniz!
Seçiminizi dikkatli yapın, değiştiremezsiniz.

💡 **Hızlı Seçim:** Aşağıdaki butonlardan birini seçin
        """
        
        try:
            await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logging.warning(f"Mesaj düzenleme hatası: {e}")
            # Alternatif olarak yeni mesaj gönder
            try:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=message_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            except:
                pass
    
    elif query.data.startswith("score_"):
        # Skor seçildi - Tek tahmin kuralı ile kaydet
        parts = query.data.split("_")
        mac_id = int(parts[1])
        skor_tahmini = parts[2]
        
        # Maç bilgisini getir
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT mac_adi, durum FROM maclar WHERE id = %s', (mac_id,))
        match = cursor.fetchone()
        conn.close()
        
        if not match or match['durum'] != 'aktif':
            try:
                await query.edit_message_text("❌ Maç bulunamadı veya artık aktif değil!")
            except:
                pass
            return
        
        try:
            # Tahmini kaydet - Tek tahmin kuralı
            action, existing_prediction = save_prediction(user_id, username, mac_id, match['mac_adi'], skor_tahmini)
            
            if action == "zaten_var":
                # Zaten tahmin var
                try:
                    await query.answer(
                        f"⚠️ Bu maça zaten tahmin yaptınız: {existing_prediction}\n"
                        f"Her maç için sadece BİR tahmin yapabilirsiniz!", 
                        show_alert=True
                    )
                except Exception as e:
                    logging.warning(f"Alert gösterme hatası: {e}")
                    # Alternatif mesaj
                    try:
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=f"⚠️ Bu maça zaten tahmin yaptınız: {existing_prediction}\nHer maç için sadece BİR tahmin yapabilirsiniz!",
                            parse_mode='Markdown'
                        )
                    except:
                        pass
                
                # Mesajı sil
                try:
                    await query.delete_message()
                except:
                    pass
                
                await send_log(context, f"🚫 **TEKRAR TAHMİN GİRİŞİMİ**\n👤 Kullanıcı: @{username}\n🏆 Maç: {match['mac_adi']}\n⚽ Mevcut Tahmin: {existing_prediction}\n❌ Denenen: {skor_tahmini}")
                
            elif action == "kaydedildi":
                # Başarıyla kaydedildi
                try:
                    await query.answer(f"✅ Tahmin kaydedildi! {match['mac_adi']}: {skor_tahmini}", show_alert=True)
                except Exception as e:
                    logging.warning(f"Alert gösterme hatası: {e}")
                    # Alternatif mesaj
                    try:
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=f"✅ Tahmin kaydedildi! {match['mac_adi']}: {skor_tahmini}",
                            parse_mode='Markdown'
                        )
                    except:
                        pass
                
                # Mesajı sil (grupta görünmesin)
                try:
                    await query.delete_message()
                except:
                    pass
                
                # Başarılı tahmin logla
                await send_log(context, f"✅ **YENİ TAHMİN KAYDEDİLDİ**\n👤 Kullanıcı: @{username}\n🏆 Maç: {match['mac_adi']}\n⚽ Tahmin: {skor_tahmini}")
            
        except Exception as e:
            try:
                await query.answer("❌ Bir hata oluştu! Tekrar deneyin.", show_alert=True)
            except:
                # Alternatif mesaj
                try:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="❌ Bir hata oluştu! Tekrar deneyin.",
                        parse_mode='Markdown'
                    )
                except:
                    pass
            await send_log(context, f"🚨 **TAHMİN KAYDETME HATASI**\n👤 Kullanıcı: @{username}\n🏆 Maç: {match['mac_adi']}\n❌ Hata: {str(e)}")
    
    elif query.data.startswith("custom_"):
        # Özel skor girme
        mac_id = int(query.data.split("_")[1])
        
        # Önce kullanıcının bu maça tahmin yapıp yapmadığını kontrol et
        existing = check_user_prediction_exists(user_id, mac_id)
        
        if existing:
            try:
                await query.answer(
                    f"⚠️ Bu maça zaten tahmin yaptınız: {existing['skor_tahmini']}\n"
                    f"Her maç için sadece BİR tahmin yapabilirsiniz!", 
                    show_alert=True
                )
            except:
                pass
            return
        
        # Maç bilgisini getir
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT mac_adi FROM maclar WHERE id = %s AND durum = %s', (mac_id, 'aktif'))
        match = cursor.fetchone()
        conn.close()
        
        if not match:
            try:
                await query.edit_message_text("❌ Maç bulunamadı veya artık aktif değil!")
            except:
                pass
            return
        
        # Özel skor seçenekleri (daha fazla)
        custom_scores = [
            ["5-0", "0-5", "5-1"],
            ["1-5", "4-3", "3-4"],
            ["5-2", "2-5", "4-4"],
            ["6-0", "0-6", "5-3"],
            ["3-5", "6-1", "1-6"],
            ["5-4", "4-5", "5-5"]
        ]
        
        keyboard = []
        for row in custom_scores:
            keyboard_row = []
            for score in row:
                keyboard_row.append(InlineKeyboardButton(
                    f"⚽ {score}", 
                    callback_data=f"score_{mac_id}_{score}"
                ))
            keyboard.append(keyboard_row)
        
        keyboard.append([InlineKeyboardButton("🔙 Geri Dön", callback_data=f"match_{mac_id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = f"""
🏆 **Maç:** {match['mac_adi']}

⚽ **Özel Skor Seçenekleri:**

⚠️ **DİKKAT:** Bu maç için sadece **BİR KEZ** tahmin yapabilirsiniz!

💡 **Yüksek skorlu maçlar için:**
        """
        
        try:
            await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logging.warning(f"Mesaj düzenleme hatası: {e}")
    
    elif query.data == "back_to_matches":
        # Ana menüye dön - Aynı şekilde try-except ile koruma
        user_id = update.effective_user.id
        matches = get_active_matches()
        
        if not matches:
            try:
                await query.edit_message_text(
                    "⚠️ **Şu anda aktif maç bulunmuyor!**\n\n"
                    "Yönetici henüz maç eklememiş. Lütfen daha sonra tekrar deneyin.",
                    parse_mode='Markdown'
                )
            except:
                pass
            return
        
        # Kullanıcının tahmin yaptığı maçları kontrol et
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT mac_id FROM tahminler 
            WHERE user_id = %s
        ''', (user_id,))
        
        tahmin_yapilan_maclar = [row['mac_id'] for row in cursor.fetchall()]
        conn.close()
        
        # Inline keyboard oluştur
        keyboard = []
        tahmin_yapilabilir_mac_sayisi = 0
        
        for match in matches:
            mac_id = match['id']
            mac_adi = match['mac_adi']
            
            # Tarih bilgisi varsa ekle
            tarih_text = ""
            if match['mac_tarihi']:
                try:
                    if isinstance(match['mac_tarihi'], str):
                        tarih_obj = datetime.fromisoformat(match['mac_tarihi'].replace('Z', '+00:00'))
                    else:
                        tarih_obj = match['mac_tarihi']
                    tarih_text = f" ({tarih_obj.strftime('%d.%m %H:%M')})"
                except:
                    pass
            
            # Tahmin durumunu kontrol et
            if mac_id in tahmin_yapilan_maclar:
                # Zaten tahmin yapılmış
                button_text = f"✅ {mac_adi}{tarih_text} (Tahmin Yapıldı)"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"already_{mac_id}")])
            else:
                # Tahmin yapılabilir
                button_text = f"⚽ {mac_adi}{tarih_text}"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"match_{mac_id}")])
                tahmin_yapilabilir_mac_sayisi += 1
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = f"""
🎯 **Aktif Maçlar** ({len(matches)} adet)

⚽ **Tahmin yapılabilir:** {tahmin_yapilabilir_mac_sayisi} maç
✅ **Tahmin yapıldı:** {len(matches) - tahmin_yapilabilir_mac_sayisi} maç

⚠️ **KURAL:** Her maç için sadece **BİR KEZ** tahmin yapabilirsiniz!

Tahmin yapmak istediğiniz maçı seçin:
        """
        
        try:
            await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logging.warning(f"Mesaj düzenleme hatası: {e}")


@check_group_permission
async def tahminlerim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kullanıcının tahminlerini göster"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    predictions = get_user_predictions(user_id)
    
    if not predictions:
        await update.message.reply_text(
            "📝 **Henüz tahmin yapmamışsınız!**\n\n"
            "İlk tahminizi yapmak için:\n"
            "/tahmin komutunu kullanın\n\n"
            "⚠️ **Hatırlatma:** Her maç için sadece **BİR KEZ** tahmin yapabilirsiniz!\n"
            "🚀 **Hızlı ve kolay!** Sadece butona tıklayın!",
            parse_mode='Markdown'
        )
        await send_log(context, f"📝 **TAHMİN SORGUSU**\n👤 Kullanıcı: @{username}\n📊 Sonuç: Tahmin yok")
        return
    
    # Site kullanıcı adını getir
    site_username = get_site_username(user_id)
    site_info = f" ({site_username})" if site_username else ""
    
    message = f"📊 **@{username}{site_info} - Son Tahminleriniz:**\n\n"
    
    for i, prediction in enumerate(predictions, 1):
        mac_adi = prediction['mac_adi']
        skor_tahmini = prediction['skor_tahmini']
        tarih = prediction['tarih']
        gercek_skor = prediction['gercek_skor']
        durum = prediction['durum']
        
        # Tarihi formatla
        if isinstance(tarih, str):
            date_obj = datetime.strptime(tarih, '%Y-%m-%d %H:%M:%S')
        else:
            date_obj = tarih
        formatted_date = date_obj.strftime('%d.%m.%Y %H:%M')
        
        # Tahmin durumu
        durum_icon = "⏳"
        durum_text = "Beklemede"
        
        if gercek_skor:
            if skor_tahmini == gercek_skor:
                durum_icon = "✅"
                durum_text = "DOĞRU!"
            else:
                durum_icon = "❌"
                durum_text = f"Yanlış (Gerçek: {gercek_skor})"
        
        message += f"**{i}.** {mac_adi}\n"
        message += f"⚽ **Tahmin:** {skor_tahmini}\n"
        message += f"{durum_icon} **Durum:** {durum_text}\n"
        message += f"📅 {formatted_date}\n\n"
    
    # Döngü bittikten SONRA toplam bilgileri ekle
    message += f"🎯 **Toplam Tahmin:** {len(predictions)}\n"
    message += f"⚠️ **Kural:** Her maç için sadece BİR tahmin hakkınız var!\n"
    message += f"🚀 **Yeni tahmin için:** /tahmin"
    
    # Döngü bittikten SONRA mesajı gönder
    await update.message.reply_text(message, parse_mode='Markdown')
    await send_log(context, f"📊 **TAHMİN LİSTESİ GÖRÜNTÜLENDI**\n👤 Kullanıcı: @{username}\n🎯 Site: {site_username}\n📈 Toplam Tahmin: {len(predictions)}")

@check_group_permission
async def yardim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yardım komutu"""
    help_text = """
📚 **Hızlı Skor Tahmin Sistemi**

🚀 **Süper Hızlı Kullanım:**
• `/tahmin` - Maçları gör ve hızlıca tahmin yap
• `/tahminlerim` - Geçmiş tahminleri görüntüle
• `/yardim` - Bu yardım menüsü

⚽ **3 Adımda Tahmin:**
1️⃣ `/tahmin` yazın
2️⃣ Maçı seçin (butona tıklayın)
3️⃣ Skoru seçin (butona tıklayın)

**Hepsi bu kadar! Soru-cevap yok!**

⚠️ **ÖNEMLİ KURAL:**
• Her maç için sadece **BİR KEZ** tahmin yapabilirsiniz!
• Tahmin yaptıktan sonra değiştiremezsiniz!
• Dikkatli seçim yapın!

✅ **Özellikler:**
• 🚀 **Hızlı:** Sadece butonlara tıklayın
• 🎯 **Kolay:** Popüler skorlar hazır
• 🔒 **Güvenli:** Sadece onaylı maçlar
• ✏️ **Esnek:** Özel skor seçenekleri
• 📊 **Takip:** Tüm tahminleriniz kaydedilir
• 🛡️ **Adil:** Her maç için tek tahmin hakkı

🏆 **Popüler Skorlar:**
0-0, 1-0, 1-1, 2-1, 2-0, 3-1, vs.

✏️ **Özel Skorlar:**
Yüksek skorlu maçlar için özel seçenekler

🎮 **Grup Dostu:**
100lerce kişi aynı anda kullanabilir!
Karışıklık yok, herkes kendi tahminini yapar.

🤖 **Bot Yönetimi:** Yönetici Paneli
    """
    
    await update.message.reply_text(help_text, parse_mode='Markdown')
    await send_log(context, f"❓ **YARDIM KOMUTU**\n👤 Kullanıcı: @{update.effective_user.username or update.effective_user.first_name}")

def main():
    """Ana fonksiyon"""
    init_database()
    
    TOKEN = os.environ.get('BOT_TOKEN', "8230185811:AAHJI59TpDIw1q4xKrvZyxhnjr5ZTCxkhJI")
    
    app = Application.builder().token(TOKEN).build()
    
    # Handler'ları ekle
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tahmin", tahmin_menu))
    app.add_handler(CommandHandler("tahminlerim", tahminlerim))
    app.add_handler(CommandHandler("yardim", yardim))
    
    # Callback query handler (butonlar için)
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Message handler (site kullanıcı adı için) - YENİ!
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app.run_polling()

if __name__ == '__main__':
    main()

