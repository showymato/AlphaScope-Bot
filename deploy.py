#!/usr/bin/env python3
"""
Quick deployment script for AlphaScope Bot
"""

import os
import sys

def main():
    print("🤖 AlphaScope Bot - Quick Deploy")
    print("=" * 35)

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("\n❌ TELEGRAM_BOT_TOKEN not found!")
        print("\n📝 Setup steps:")
        print("1. Message @BotFather on Telegram")
        print("2. Send: /newbot")
        print("3. Copy your bot token")
        print("4. Set: export TELEGRAM_BOT_TOKEN='your_token'")
        print("5. Run: python bot.py")
        return

    print(f"✅ Bot token found: {token[:10]}...")
    print("\n🚀 Ready to deploy!")
    print("\nLocal: python bot.py")
    print("Render: Push to GitHub & connect")
    print("\n💡 Bot works in any chat - no setup needed!")

if __name__ == "__main__":
    main()
