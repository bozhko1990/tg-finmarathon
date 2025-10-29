import os
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from datetime import datetime, timedelta
import pytz

# === НАСТРОЙКИ ===
TZ = pytz.timezone("Europe/Kyiv")
MORNING_HOUR = 9
EVENING_HOUR = 21
USERNAME = "Артур"
CURRENCY = "$"
REPORT_XLSX = "Финансовый_марафон_300.xlsx"
REPORT_PNG = "График_Финансовый_марафон_300.png"

# === СОЗДАНИЕ БАЗЫ ===
def init_db():
    conn = sqlite3.connect("tracker.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS params (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_balance REAL,
            start_date TEXT,
            percent REAL,
            duration INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS balances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day INTEGER,
            date TEXT,
            balance REAL,
            plan REAL,
            diff REAL
        )
    ''')
    conn.commit()
    conn.close()

# === КОМАНДЫ ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect("tracker.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM params")
    params = cursor.fetchone()
    conn.close()

    if params:
        await update.message.reply_text(
            f"Привет, {USERNAME}! 👋\n"
            f"Финансовый марафон уже запущен.\n"
            f"Ты можешь использовать команды:\n"
            f"/add – добавить баланс вручную\n"
            f"/stats – статистика за неделю\n"
            f"/report – общий отчёт\n"
            f"/export – Excel отчёт\n"
            f"/reset – сбросить данные\n"
        )
    else:
        await update.message.reply_text(
            f"Привет, {USERNAME}! 👋\n"
            f"Давай начнём твой финансовый марафон 💰\n\n"
            f"Введите стартовый баланс ($):"
        )
        return 1  # Следующий шаг – ввод баланса
    return ConversationHandler.END

async def set_start_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        balance = float(update.message.text)
        context.user_data["start_balance"] = balance
        await update.message.reply_text("Введите дату начала марафона (в формате ГГГГ-ММ-ДД):")
        return 2
    except ValueError:
        await update.message.reply_text("Введите число, например: 300")
        return 1

async def set_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        start_date = datetime.strptime(update.message.text, "%Y-%m-%d")
        context.user_data["start_date"] = start_date.strftime("%Y-%m-%d")
        await update.message.reply_text("Введите целевой процент в день (%):")
        return 3
    except ValueError:
        await update.message.reply_text("Формат неверный, попробуй так: 2025-10-29")
        return 2

async def set_percent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        percent = float(update.message.text)
        context.user_data["percent"] = percent
        await update.message.reply_text("На сколько дней рассчитан марафон?")
        return 4
    except ValueError:
        await update.message.reply_text("Введите число, например: 2")
        return 3

async def set_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        duration = int(update.message.text)
        context.user_data["duration"] = duration

        conn = sqlite3.connect("tracker.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM params")
        cursor.execute(
            "INSERT INTO params (start_balance, start_date, percent, duration) VALUES (?, ?, ?, ?)",
            (
                context.user_data["start_balance"],
                context.user_data["start_date"],
                context.user_data["percent"],
                context.user_data["duration"],
            ),
        )
        conn.commit()
        conn.close()

        await update.message.reply_text(
            f"✅ Отлично, {USERNAME}!\n"
            f"Баланс: {context.user_data['start_balance']}{CURRENCY}\n"
            f"Дата старта: {context.user_data['start_date']}\n"
            f"Процент: {context.user_data['percent']}%\n"
            f"Длительность: {context.user_data['duration']} дней\n\n"
            f"Теперь бот будет напоминать тебе утром и вечером вводить баланс.\n"
            f"Можешь также использовать /add или /stats для анализа."
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Введите число, например: 90")
        return 4
# === ДОБАВЛЕНИЕ БАЛАНСА ===

# === ДОБАВЛЕНИЕ БАЛАНСА (АВТОВЫЧИСЛЕНИЕ ДНЯ) ===

async def add_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect("tracker.db")
    cursor = conn.cursor()
    cursor.execute("SELECT start_balance, percent, start_date FROM params")
    row = cursor.fetchone()
    conn.close()

    if not row:
        await update.message.reply_text("Сначала запусти марафон через /start")
        return ConversationHandler.END

    start_balance, percent, start_date = row
    today = datetime.now(TZ).date()
    start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
    current_day = (today - start_date_obj).days + 1
    if current_day < 1:
        current_day = 1

    context.user_data["day"] = current_day
    context.user_data["date"] = str(today)
    context.user_data["start_balance"] = start_balance
    context.user_data["percent"] = percent

    await update.message.reply_text(
        f"📅 День {current_day} марафона ({today})\n"
        f"Введи свой текущий баланс 💵"
    )
    return 6


async def save_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        balance = float(update.message.text)
        conn = sqlite3.connect("tracker.db")
        cursor = conn.cursor()

        start_balance = context.user_data["start_balance"]
        percent = context.user_data["percent"]
        day = context.user_data["day"]
        date = context.user_data["date"]

        # расчёт планового баланса
        plan_balance = start_balance * ((1 + percent / 100) ** day)
        diff = balance - plan_balance

        cursor.execute(
            "INSERT OR REPLACE INTO balances (day, date, balance, plan, diff) VALUES (?, ?, ?, ?, ?)",
            (day, date, balance, plan_balance, diff),
        )
        conn.commit()
        conn.close()

        # сообщение пользователю
        if diff >= 0:
            msg = (f"✅ День {day} выполнен!\n"
                   f"План: {plan_balance:.2f}{CURRENCY}\n"
                   f"Факт: {balance:.2f}{CURRENCY}\n"
                   f"Перевыполнение: +{diff:.2f}{CURRENCY}")
        else:
            msg = (f"⚠️ День {day}: недовыполнение плана\n"
                   f"План: {plan_balance:.2f}{CURRENCY}\n"
                   f"Факт: {balance:.2f}{CURRENCY}\n"
                   f"Отклонение: {diff:.2f}{CURRENCY}")

        await update.message.reply_text(msg + "\n\n" + motivation(diff))
        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("Введите число, например: 342.5")
        return 6

# === АВТОМАТИЧЕСКИЕ НАПОМИНАНИЯ ===

async def ask_morning(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"Доброе утро, {USERNAME} ☀️\nКакой у тебя баланс на утро?"
    )

async def ask_evening(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"Добрый вечер, {USERNAME} 🌙\nКакой итоговый баланс на сегодня?"
    )

def schedule_jobs(application, chat_id):
    # Удаляем старые напоминания
    for job in application.job_queue.get_jobs_by_name(str(chat_id)):
        job.schedule_removal()

    # Добавляем утренний и вечерний запрос
    kyiv_now = datetime.now(TZ)
    application.job_queue.run_daily(
        ask_morning,
        time=datetime.time(hour=MORNING_HOUR, minute=0, tzinfo=TZ),
        days=(0, 1, 2, 3, 4, 5, 6),
        name=str(chat_id),
        chat_id=chat_id,
    )
    application.job_queue.run_daily(
        ask_evening,
        time=datetime.time(hour=EVENING_HOUR, minute=0, tzinfo=TZ),
        days=(0, 1, 2, 3, 4, 5, 6),
        name=str(chat_id),
        chat_id=chat_id,
    )

# === НЕДЕЛЬНАЯ СТАТИСТИКА ===

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect("tracker.db")
    df = pd.read_sql_query("SELECT * FROM balances", conn)
    conn.close()

    if df.empty:
        await update.message.reply_text("Данных пока нет. Добавь баланс через /add")
        return

    df["date"] = pd.to_datetime(df["date"])
    last_day = df["date"].max()
    first_day = last_day - timedelta(days=6)
    week_data = df[(df["date"] >= first_day) & (df["date"] <= last_day)]

    msg = f"📊 Статистика за неделю ({first_day.date()} - {last_day.date()}):\n\n"
    avg_diff = 0
    for _, row in week_data.iterrows():
        day_diff = row["balance"] - row["plan"]
        perc = (day_diff / row["plan"]) * 100
        avg_diff += perc
        msg += (f"День {int(row['day'])}: План {row['plan']:.2f}{CURRENCY} | "
                f"Факт {row['balance']:.2f}{CURRENCY} | "
                f"{'+' if perc >= 0 else ''}{perc:.2f}%\n")

    avg_diff /= len(week_data)
    msg += f"\n📈 Среднее отклонение за неделю: {avg_diff:+.2f}%"
    await update.message.reply_text(msg)

# === ОТЧЁТ И ГРАФИК ===
import matplotlib
matplotlib.use('Agg')

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect("tracker.db")
    df = pd.read_sql_query("SELECT * FROM balances", conn)
    conn.close()

    if df.empty:
        await update.message.reply_text("Пока нет данных для отчёта 📄")
        return

    # Построение графика
    plt.figure(figsize=(10,5))
    plt.plot(df["day"], df["plan"], label="План", linestyle="--", color="blue")
    plt.plot(df["day"], df["balance"], label="Факт", marker="o", color="green")
    plt.xlabel("День")
    plt.ylabel(f"Баланс ({CURRENCY})")
    plt.title(f"Финансовый марафон — {USERNAME}")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(REPORT_PNG)
    plt.close()

    await update.message.reply_photo(photo=open(REPORT_PNG, "rb"), caption="📈 График твоего марафона")

    # Экспорт Excel
    writer = pd.ExcelWriter(REPORT_XLSX, engine="openpyxl")
    df.to_excel(writer, index=False, sheet_name="Марафон")
    writer.close()

    await update.message.reply_document(document=open(REPORT_XLSX, "rb"), caption="📄 Отчёт Excel готов!")

# === СБРОС ДАННЫХ ===
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect("tracker.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM params")
    cursor.execute("DELETE FROM balances")
    conn.commit()
    conn.close()
    await update.message.reply_text("🔁 Все данные очищены. Чтобы начать заново — введи /start")

# === МОТИВАЦИЯ ===
def motivation(diff):
    if diff > 0:
        return "🔥 Отличный результат! Так держать!"
    elif diff > -1:
        return "⚡ Почти в плане, продолжай!"
    else:
        return "💪 Главное — стабильность. Завтра будет лучше!"

# === ОСНОВНОЙ ЗАПУСК ===
import asyncio

async def main():
    init_db()
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("❌ Укажи токен перед запуском: $env:BOT_TOKEN='...'")
        return

    app = ApplicationBuilder().token(token).build()

    conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        1: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_start_balance)],
        2: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_start_date)],
        3: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_percent)],
        4: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_duration)],
        6: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_balance)],
    },
    fallbacks=[],
)

    app.add_handler(conv_handler)

# отдельный мини-диалог для добавления баланса
    add_conv = ConversationHandler(
    entry_points=[CommandHandler("add", add_balance)],
    states={
        6: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_balance)],
    },
    fallbacks=[],
)

    app.add_handler(add_conv)    
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("export", report))
    app.add_handler(CommandHandler("reset", reset))

    print("✅ Бот запущен. Напиши ему /start в Telegram.")

    # Новый способ запуска совместимый с Python 3.14
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await asyncio.Event().wait()  # держим цикл открытым

if __name__ == "__main__":
    asyncio.run(main())
