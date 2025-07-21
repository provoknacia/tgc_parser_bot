import logging
import sqlite3
from datetime import datetime
import matplotlib.pyplot as plt
import pandas as pd
from telethon.sync import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import asyncio
import io
import os

API_ID = ВАШ API ID
API_HASH = 'API HASH ВАШ'
BOT_TOKEN = 'ВАШ ТОКЕН БОТА'
DB_NAME = 'telegram_stats.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS channels (
        channel_id INTEGER PRIMARY KEY,
        username TEXT UNIQUE,
        title TEXT,
        description TEXT,
        participants INTEGER,
        creation_date TEXT,
        last_updated TEXT
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS stats_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id INTEGER,
        date TEXT,
        participants INTEGER,
        FOREIGN KEY (channel_id) REFERENCES channels (channel_id)
    )
    ''')
    
    conn.commit()
    conn.close()

def save_channel_stats(stats):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute('''
    INSERT OR REPLACE INTO channels 
    (channel_id, username, title, description, participants, creation_date, last_updated)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        stats['channel_id'],
        stats['username'],
        stats['title'],
        stats['description'],
        stats['participants'],
        stats['creation_date'].strftime('%Y-%m-%d %H:%M:%S'),
        now
    ))

    cursor.execute('''
    INSERT INTO stats_history 
    (channel_id, date, participants)
    VALUES (?, ?, ?)
    ''', (
        stats['channel_id'],
        now,
        stats['participants']
    ))
    
    conn.commit()
    conn.close()

def get_channel_history(channel_id, limit=30):
    conn = sqlite3.connect(DB_NAME)
    query = '''
    SELECT date, participants 
    FROM stats_history 
    WHERE channel_id = ? 
    ORDER BY date DESC
    LIMIT ?
    '''
    df = pd.read_sql(query, conn, params=(channel_id, limit))
    conn.close()
    return df

def generate_subscribers_plot(channel_id, channel_name):
    df = get_channel_history(channel_id)
    
    if df.empty:
        return None
    
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    
    plt.figure(figsize=(12, 6))
    plt.plot(df['date'], df['participants'], marker='o', linestyle='-', color='b')
    plt.title(f'Динамика подписчиков канала {channel_name}')
    plt.ylabel('Количество подписчиков')
    plt.xlabel('Дата')
    plt.grid(True)
    plt.gca().yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: '{:,}'.format(int(x)).replace(',', ' ')))
    plt.gcf().autofmt_xdate()
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close()
    
    return buf

async def get_channel_stats(channel_username):
    async with TelegramClient('session_name', API_ID, API_HASH) as client:
        channel = await client.get_entity(channel_username)
        full_info = await client(GetFullChannelRequest(channel=channel))
        
        stats = {
            'channel_id': channel.id,
            'title': channel.title,
            'username': channel.username,
            'participants': full_info.full_chat.participants_count,
            'description': full_info.full_chat.about,
            'creation_date': channel.date,
        }
        
        save_channel_stats(stats)
        return stats

def format_number(num):
    return "{:,}".format(num).replace(",", " ")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 Бот для анализа Telegram каналов\n\n"
        "Отправьте мне @username канала (например, @durov_russia) и я пришлю:\n"
        "• График динамики подписчиков\n"
        "• Текущую статистику канала"
    )

async def handle_channel_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel_username = update.message.text.strip()
    
    if not channel_username.startswith('@'):
        await update.message.reply_text("❌ Пожалуйста, укажите username канала, начиная с @ (например, @durov_russia)")
        return
    
    try:
        await update.message.reply_text("⏳ Запрашиваю данные...")
        
        stats = await get_channel_stats(channel_username)
        
        plot_buffer = generate_subscribers_plot(stats['channel_id'], stats['username'])
        
        if plot_buffer is None:
            await update.message.reply_text("⚠️ Недостаточно данных для построения графика")
            return
        
        report = (
            f"📊 <b>Статистика канала {stats['title']}</b> (@{stats['username']})\n\n"
            f"👥 <b>Подписчиков:</b> {format_number(stats['participants'])}\n"
            f"📅 <b>Создан:</b> {stats['creation_date'].strftime('%Y-%m-%d')}\n"
            f"📝 <b>Описание:</b> {stats['description'][:300]}{'...' if len(stats['description']) > 300 else ''}"
        )
        
        await update.message.reply_photo(
            photo=InputFile(plot_buffer, filename='subscribers_plot.png'),
            caption=report,
            parse_mode='HTML'
        )
        
    except ValueError as e:
        await update.message.reply_text(f"❌ Канал {channel_username} не найден")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Произошла ошибка: {str(e)}")
        logging.error(f"Error processing {channel_username}: {str(e)}")

def main():
    init_db()
    
    if not os.path.exists('session'):
        os.makedirs('session')
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_channel_request))
    
    application.run_polling()

if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    main()
