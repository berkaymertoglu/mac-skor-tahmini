import logging
import os
import psycopg2
import psycopg2.extras
import sqlite3
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

def get_db_connection():
    """PostgreSQL veya SQLite bağlantısı"""
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        return psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        return sqlite3.connect('tahminler.db')

def init_database():
    """PostgreSQL için veritabanını başlat"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    is_postgres = os.environ.get('DATABASE_URL') is not None
    
    if is_postgres:
        # PostgreSQL syntax
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tahminler (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                username VARCHAR(100),
                mac_adi VARCHAR(200),
                skor_tahmini VARCHAR(20),
                tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    else:
        # SQLite syntax
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tahminler (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                mac_adi TEXT,
                skor_tahmini TEXT,
                tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    
    conn.commit()
    conn.close()

def save_prediction(user_id, username, mac_adi, skor_tahmini):
    """PostgreSQL uyumlu tahmin kaydetme"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    is_postgres = os.environ.get('DATABASE_URL') is not None
    
    if is_postgres:
        cursor.execute('''
            INSERT INTO tahminler (user_id, username, mac_adi, skor_tahmini)
            VALUES (%s, %s, %s, %s)
        ''', (user_id, username, mac_adi, skor_tahmini))
    else:
        cursor.execute('''
            INSERT INTO tahminler (user_id, username, mac_adi, skor_tahmini)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, mac_adi, skor_tahmini))
    
    conn.commit()
    conn.close()

def get_user_predictions(user_id):
    """PostgreSQL uyumlu kullanıcı tahminleri"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    is_postgres = os.environ.get('DATABASE_URL') is not None
    
    if is_postgres:
        cursor.execute('''
            SELECT mac_adi, skor_tahmini, tarih 
            FROM tahminler 
            WHERE user_id = %s 
            ORDER BY tarih DESC 
            LIMIT 10
        ''', (user_id,))
    else:
        cursor.execute('''
            SELECT mac_adi, skor_tahmini, tarih 
            FROM tahminler 
            WHERE user_id = ? 
            ORDER BY tarih DESC 
            LIMIT 10
        ''', (user_id,))
    
    results = cursor.fetchall()
    conn.close()
    
    # PostgreSQL RealDictCursor sonuçlarını handle et
    if is_postgres and results:
        return [(row['mac_adi'], row['skor_tahmini'], row['tarih']) for row in results]
    
    return results

# Diğer fonksiyonlar aynı kalır...

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start komutu handler'ı"""
    welcome_text = """
🤖 **Skor Tahmin Botu'na Hoş Geldiniz!** ⚽

📋 **Kullanım:**
/skortahmin Galatasaray-Fenerbahçe 2-1
/tahminlerim - Geçmiş tahminlerinizi görün
/yardim - Detaylı kullanım kılavuzu

✅ **Örnek Kullanım:**
• /skortahmin Barcelona-Real Madrid 3-1
• /skortahmin Türkiye-Almanya 2-0
• /skortahmin Liverpool-Chelsea 1-1

🗄️ **Veritabanı:** PostgreSQL (Supabase)
Tahminlerinizi kaydetmeye başlayın! 🎯
    """
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def skor_tahmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """PostgreSQL uyumlu skor tahmin komutu"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    if not context.args:
        await update.message.reply_text(
            "❌ **Hatalı kullanım!**\n\n"
            "✅ **Doğru format:**\n"
            "/skortahmin Takım1-Takım2 Skor\n\n"
            "📝 **Örnekler:**\n"
            "• /skortahmin Galatasaray-Fenerbahçe 2-1\n"
            "• /skortahmin Barcelona-Real Madrid 3-0",
            parse_mode='Markdown'
        )
        return
    
    try:
        full_text = " ".join(context.args)
        parts = full_text.rsplit(" ", 1)
        
        if len(parts) != 2:
            raise ValueError("Format hatası")
            
        mac_adi = parts[0]
        skor_tahmini = parts[1]
        
        if "-" not in skor_tahmini or len(skor_tahmini.split("-")) != 2:
            raise ValueError("Skor format hatası")
        
        skor_parts = skor_tahmini.split("-")
        int(skor_parts[0])
        int(skor_parts[1])
        
        # PostgreSQL'e kaydet
        save_prediction(user_id, username, mac_adi, skor_tahmini)
        
        success_message = f"""
✅ **Tahmin Kaydedildi! (PostgreSQL)**

🏆 **Maç:** {mac_adi}
⚽ **Tahmin:** {skor_tahmini}
👤 **Kullanıcı:** @{username}
📅 **Tarih:** {datetime.now().strftime('%d.%m.%Y %H:%M')}

🎯 Tahminlerinizi görmek için /tahminlerim komutunu kullanın!
        """
        
        await update.message.reply_text(success_message, parse_mode='Markdown')
        
    except ValueError:
        await update.message.reply_text(
            "❌ **Hatalı format!**\n\n"
            "✅ **Doğru kullanım:**\n"
            "/skortahmin Takım1-Takım2 X-Y\n\n"
            "⚠️ Skor formatı: sayı-sayı (örn: 2-1, 0-0, 4-3)",
            parse_mode='Markdown'
        )

def main():
    """Ana fonksiyon"""
    init_database()
    
    TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', "8230185811:AAHJI59TpDIw1q4xKrvZyxhnjr5ZTCxkhJI")
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("skortahmin", skor_tahmin))
    app.add_handler(CommandHandler("tahminlerim", tahminlerim))
    app.add_handler(CommandHandler("yardim", yardim))
    
    print("🤖 PostgreSQL Telegram Bot başlatılıyor...")
    app.run_polling()

if __name__ == '__main__':
    main()
