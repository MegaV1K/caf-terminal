import sys
from pathlib import Path

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from src.notifications.telegram import notify

def main():
    print("=" * 60)
    print("Проверка подключения Telegram...")
    print("=" * 60)

    if not TELEGRAM_BOT_TOKEN:
        print("[!] ОШИБКА: TELEGRAM_BOT_TOKEN не найден в .env файле.")
        return

    if not TELEGRAM_CHAT_ID:
        print("[!] ОШИБКА: TELEGRAM_CHAT_ID не найден в .env файле.")
        return

    masked_token = TELEGRAM_BOT_TOKEN[:10] + "..." + TELEGRAM_BOT_TOKEN[-5:] if len(TELEGRAM_BOT_TOKEN) > 15 else "***"
    print(f"• Токен бота: {masked_token}")
    print(f"• Chat ID:    {TELEGRAM_CHAT_ID}")
    print("\nОтправка тестового сообщения...")

    success = notify("🚀 <b>CAF-Terminal</b> успешно подключен к твоему Telegram!")
    if success:
        print("[OK] УСПЕХ! Сообщение успешно доставлено в Telegram.")
    else:
        print("[FAIL] Ошибка отправки. Проверь правильность данных или нажал ли ты /start боту.")

if __name__ == "__main__":
    main()
