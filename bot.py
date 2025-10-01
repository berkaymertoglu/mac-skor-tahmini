import logging
import os
import psycopg2
import psycopg2.extras
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from dotenv import load_dotenv

load_dotenv()

# Logging ayarları
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

def get_db_connection():
    """PostgreSQL bağlantısı"""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise Exception("DATABASE_URL environment variable is required!")
    return psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)

# Veritabanı kurulumu
def init_database():
    """Veritabanını başlat"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
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
    
    conn.commit()
    conn.close()

def save_prediction(user_id, username, mac_adi, skor_tahmini):
    """Tahmini veritabanına kaydet"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO tahminler (user_id, username, mac_adi, skor_tahmini)
        VALUES (%s, %s, %s, %s)
    ''', (user_id, username, mac_adi, skor_tahmini))
    
    conn.commit()
    conn.close()

def get_user_predictions(user_id):
    """Kullanıcının tahminlerini getir"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT mac_adi, skor_tahmini, tarih 
        FROM tahminler 
        WHERE user_id = %s 
        ORDER BY tarih DESC 
        LIMIT 10
    ''', (user_id,))
    
    results = cursor.fetchall()
    conn.close()
    return results

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

Tahminlerinizi kaydetmeye başlayın! 🎯
    """
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hello komutu handler'ı"""
    await update.message.reply_text('⚽ Selam! Skor tahminlerinizi kaydetmek için /skortahmin komutunu kullanın!')

async def skor_tahmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Skor tahmin komutu handler'ı"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    # Komut argümanlarını kontrol et
    if not context.args:
        await update.message.reply_text(
            "❌ **Hatalı kullanım!**\n\n"
            "✅ **Doğru format:**\n"
            "/skortahmin Takım1-Takım2 Skor\n\n"
            "📝 **Örnekler:**\n"
            "• /skortahmin Galatasaray-Fenerbahçe 2-1\n"
            "• /skortahmin Barcelona-Real Madrid 3-0\n"
            "• /skortahmin Türkiye-İtalya 1-1",
            parse_mode='Markdown'
        )
        return
    
    try:
        # Argümanları birleştir ve parse et
        full_text = " ".join(context.args)
        
        # Son boşluktan sonrasını skor olarak al
        parts = full_text.rsplit(" ", 1)
        if len(parts) != 2:
            raise ValueError("Format hatası")
            
        mac_adi = parts[0]
        skor_tahmini = parts[1]
        
        # Skor formatını kontrol et (X-Y formatında olmalı)
        if "-" not in skor_tahmini or len(skor_tahmini.split("-")) != 2:
            raise ValueError("Skor format hatası")
        
        # Skorun sayısal olduğunu kontrol et
        skor_parts = skor_tahmini.split("-")
        int(skor_parts[0])
        int(skor_parts[1])
        
        # Veritabanına kaydet
        save_prediction(user_id, username, mac_adi, skor_tahmini)
        
        # Başarı mesajı
        success_message = f"""
✅ **Tahmin Kaydedildi!**

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
            "📝 **Örnekler:**\n"
            "• /skortahmin Galatasaray-Fenerbahçe 2-1\n"
            "• /skortahmin Manchester City-Liverpool 3-2\n\n"
            "⚠️ Skor formatı: sayı-sayı (örn: 2-1, 0-0, 4-3)",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(
            "❌ **Bir hata oluştu!**\n\n"
            "Lütfen tekrar deneyin veya format kontrolü yapın.\n"
            "/yardim komutunu kullanarak detaylı bilgi alabilirsiniz."
        )

async def tahminlerim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kullanıcının tahminlerini göster"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    predictions = get_user_predictions(user_id)
    
    if not predictions:
        await update.message.reply_text(
            "📝 **Henüz tahmin yapmamışsınız!**\n\n"
            "İlk tahminizi yapmak için:\n"
            "/skortahmin Takım1-Takım2 X-Y\n\n"
            "Örnek: /skortahmin Barcelona-Real Madrid 2-1"
        )
        return
    
    message = f"📊 **@{username} - Son Tahminleriniz:**\n\n"
    
    for i, prediction in enumerate(predictions, 1):
        mac_adi = prediction['mac_adi']
        skor_tahmini = prediction['skor_tahmini']
        tarih = prediction['tarih']
        
        # Tarihi formatla
        if isinstance(tarih, str):
            date_obj = datetime.strptime(tarih, '%Y-%m-%d %H:%M:%S')
        else:
            date_obj = tarih
        formatted_date = date_obj.strftime('%d.%m.%Y %H:%M')
        
        message += f"**{i}.** {mac_adi}\n"
        message += f"⚽ **Tahmin:** {skor_tahmini}\n"
        message += f"📅 {formatted_date}\n\n"
    
    message += f"🎯 **Toplam Tahmin:** {len(predictions)}"
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def yardim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yardım komutu"""
    help_text = """
📚 **Detaylı Kullanım Kılavuzu**

🎯 **Ana Komutlar:**
• `/skortahmin` - Yeni tahmin ekle
• `/tahminlerim` - Geçmiş tahminleri görüntüle
• `/yardim` - Bu yardım menüsü

⚽ **Skor Tahmin Formatı:**
`/skortahmin Takım1-Takım2 X-Y`

📝 **Doğru Örnekler:**
• `/skortahmin Galatasaray-Fenerbahçe 2-1`
• `/skortahmin Barcelona-Real Madrid 3-0`
• `/skortahmin Türkiye-Almanya 1-1`
• `/skortahmin Manchester United-Liverpool 2-2`

❌ **Hatalı Örnekler:**
• `/skortahmin Galatasaray Fenerbahçe 2-1` (tire eksik)
• `/skortahmin Galatasaray-Fenerbahçe 2:1` (iki nokta yerine tire)
• `/skortahmin Galatasaray-Fenerbahçe 2 1` (tire eksik)

💡 **İpuçları:**
• Takım adları arasında tire (-) kullanın
• Skor için tire (-) kullanın
• Sadece sayı kullanın (2-1, 0-0, 4-3 gibi)
• Türkçe karakter kullanabilirsiniz

📊 **Özellikler:**
• Tüm tahminleriniz kaydedilir
• Son 10 tahminizi görebilirsiniz  
• Tarih ve saat otomatik eklenir
• Kullanıcı adınız kaydedilir

🤖 **Bot Geliştirici:** @YourUsername
    """
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

def main():
    """Ana fonksiyon"""
    # Veritabanını başlat
    init_database()
    
    # Bot token'ını environment variable'dan al
    TOKEN = os.environ.get('BOT_TOKEN', "8230185811:AAHJI59TpDIw1q4xKrvZyxhnjr5ZTCxkhJI")
    
    # Application oluştur
    app = Application.builder().token(TOKEN).build()
    
    # Handler'ları ekle
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("hello", hello))
    app.add_handler(CommandHandler("skortahmin", skor_tahmin))
    app.add_handler(CommandHandler("tahminlerim", tahminlerim))
    app.add_handler(CommandHandler("yardim", yardim))
    
    # Bot'u çalıştır
    app.run_polling()

if __name__ == '__main__':
    main()
