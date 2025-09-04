#!/usr/bin/env python3
"""
AlphaScope Bot - Universal Crypto Intelligence Bot
Works in any chat/channel/group - no chat ID configuration needed
"""

import os
import sys
import json
import requests
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import traceback

from telegram import Bot, Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    ContextTypes,
    CallbackQueryHandler,
    filters
)
from telegram.constants import ParseMode

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Configuration - Only bot token needed!
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Bot info
BOT_VERSION = "3.1.1"
BOT_NAME = "AlphaScope Bot"

class CryptoDataFetcher:
    """Handles all cryptocurrency data fetching operations"""
    
    def __init__(self):
        self.coingecko_base = "https://api.coingecko.com/api/v3"
        self.defillama_base = "https://api.llama.fi"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': f'{BOT_NAME}/{BOT_VERSION}'
        })
    
    def _make_request(self, url: str, params: Optional[Dict] = None, timeout: int = 15) -> Optional[Dict]:
        """Make HTTP request with error handling"""
        try:
            response = self.session.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            logger.error(f"Timeout requesting {url}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error for {url}: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for {url}: {e}")
            return None
    
    def get_market_overview(self) -> Dict[str, Any]:
        """Get overall market statistics"""
        url = f"{self.coingecko_base}/global"
        data = self._make_request(url)
        
        if not data or 'data' not in data:
            return {}
            
        global_data = data['data']
        return {
            'total_market_cap_usd': global_data.get('total_market_cap', {}).get('usd', 0),
            'total_volume_usd': global_data.get('total_volume', {}).get('usd', 0),
            'market_cap_change_24h': global_data.get('market_cap_change_percentage_24h_usd', 0),
            'active_cryptocurrencies': global_data.get('active_cryptocurrencies', 0),
            'btc_dominance': global_data.get('market_cap_percentage', {}).get('btc', 0)
        }
    
    def get_top_movers(self, limit: int = 50) -> tuple[Optional[Dict], Optional[Dict]]:
        """Fetch top gainers and losers from CoinGecko"""
        url = f"{self.coingecko_base}/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": limit,
            "page": 1,
            "sparkline": False,
            "locale": "en"
        }
        
        data = self._make_request(url, params)
        if not data:
            return None, None
        
        # Filter coins with valid price changes
        valid_coins = [
            coin for coin in data 
            if (coin.get("price_change_percentage_24h") is not None and 
                coin.get("market_cap") is not None and
                coin.get("market_cap") > 1000000)  # Min 1M market cap
        ]
        
        if not valid_coins:
            return None, None
        
        # Sort by price change to get actual top movers
        sorted_coins = sorted(valid_coins, key=lambda x: x["price_change_percentage_24h"])
        
        top_gainer = sorted_coins[-1] if sorted_coins else None
        top_loser = sorted_coins[0] if sorted_coins else None
        
        return top_gainer, top_loser
    
    def get_trending_coins(self) -> List[Dict]:
        """Get trending coins from CoinGecko"""
        url = f"{self.coingecko_base}/search/trending"
        data = self._make_request(url)
        
        if not data or 'coins' not in data:
            return []
        
        trending = []
        for item in data['coins'][:5]:  # Top 5 trending
            coin = item.get('item', {})
            trending.append({
                'name': coin.get('name', 'Unknown'),
                'symbol': coin.get('symbol', ''),
                'market_cap_rank': coin.get('market_cap_rank'),
                'price_btc': coin.get('price_btc', 0)
            })
        
        return trending
    
    def get_hot_defi_projects(self) -> List[Dict]:
        """Fetch trending DeFi projects from DefiLlama"""
        url = f"{self.defillama_base}/protocols"
        data = self._make_request(url)
        
        if not data:
            return []
        
        # Filter and sort projects with positive TVL change
        valid_projects = [
            project for project in data 
            if (project.get("change_1d") is not None and 
                project.get("tvl") is not None and
                project.get("tvl") > 1000000)  # Min 1M TVL
        ]
        
        # Sort by 24h change and get top performers
        hot_projects = sorted(
            valid_projects, 
            key=lambda x: x.get("change_1d", 0), 
            reverse=True
        )[:5]
        
        return hot_projects
    
    def get_fear_greed_index(self) -> Optional[Dict]:
        """Get Fear & Greed Index"""
        url = "https://api.alternative.me/fng/?limit=1"
        data = self._make_request(url)
        
        if not data or 'data' not in data or not data['data']:
            return None
        
        index_data = data['data'][0]
        return {
            'value': int(index_data.get('value', 0)),
            'classification': index_data.get('value_classification', 'Unknown'),
            'timestamp': index_data.get('timestamp', '')
        }
    
    def get_bitcoin_price(self) -> Optional[Dict]:
        """Get Bitcoin price data"""
        url = f"{self.coingecko_base}/simple/price"
        params = {
            "ids": "bitcoin",
            "vs_currencies": "usd",
            "include_24hr_change": "true",
            "include_market_cap": "true"
        }
        
        data = self._make_request(url, params)
        if not data or 'bitcoin' not in data:
            return None
            
        btc_data = data['bitcoin']
        return {
            'price': btc_data.get('usd', 0),
            'change_24h': btc_data.get('usd_24h_change', 0),
            'market_cap': btc_data.get('usd_market_cap', 0)
        }

class MessageFormatter:
    """Handles message formatting and styling"""
    
    @staticmethod
    def format_number(num: float, decimals: int = 2) -> str:
        """Format large numbers with appropriate suffixes"""
        if num is None:
            return "N/A"
        
        abs_num = abs(num)
        if abs_num >= 1e12:
            return f"${num/1e12:.{decimals}f}T"
        elif abs_num >= 1e9:
            return f"${num/1e9:.{decimals}f}B"
        elif abs_num >= 1e6:
            return f"${num/1e6:.{decimals}f}M"
        elif abs_num >= 1e3:
            return f"${num/1e3:.{decimals}f}K"
        else:
            return f"${num:.{decimals}f}"
    
    @staticmethod
    def format_percentage(pct: float) -> str:
        """Format percentage with appropriate emoji"""
        if pct is None:
            return "N/A"
        
        if pct > 0:
            return f"📈 +{pct:.2f}%"
        else:
            return f"📉 {pct:.2f}%"
    
    @staticmethod
    def get_fear_greed_emoji(value: int) -> str:
        """Get emoji for fear & greed index"""
        if value >= 75:
            return "🤑"  # Extreme Greed
        elif value >= 55:
            return "😊"  # Greed
        elif value >= 45:
            return "😐"  # Neutral
        elif value >= 25:
            return "😨"  # Fear
        else:
            return "😱"  # Extreme Fear

class AlphaScopeBot:
    """Main bot class handling all operations"""
    
    def __init__(self):
        self.fetcher = CryptoDataFetcher()
        self.formatter = MessageFormatter()
        self.start_time = datetime.now(timezone.utc)
    
    async def create_market_summary(self) -> str:
        """Create comprehensive market summary"""
        try:
            # Fetch all data
            market_overview = self.fetcher.get_market_overview()
            gainer, loser = self.fetcher.get_top_movers()
            trending = self.fetcher.get_trending_coins()
            hot_defi = self.fetcher.get_hot_defi_projects()
            fear_greed = self.fetcher.get_fear_greed_index()
            btc_data = self.fetcher.get_bitcoin_price()
            
            # Create message
            current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            
            message_parts = [
                "🚀 *CRYPTO MARKET ALPHA* 🚀",
                f"📅 {current_time}",
                ""
            ]
            
            # Bitcoin price (always show)
            if btc_data:
                btc_price = f"${btc_data['price']:,.0f}"
                btc_change = self.formatter.format_percentage(btc_data.get('change_24h', 0))
                message_parts.extend([
                    f"₿ *Bitcoin*: {btc_price} {btc_change}",
                    ""
                ])
            
            # Market overview
            if market_overview:
                total_mcap = self.formatter.format_number(market_overview.get('total_market_cap_usd', 0))
                mcap_change = self.formatter.format_percentage(market_overview.get('market_cap_change_24h', 0))
                btc_dom = market_overview.get('btc_dominance', 0)
                
                message_parts.extend([
                    "📊 *MARKET OVERVIEW*",
                    f"💎 Total Cap: {total_mcap}",
                    f"📊 24h Change: {mcap_change}",
                    f"₿ BTC Dom: {btc_dom:.1f}%",
                    ""
                ])
            
            # Fear & Greed
            if fear_greed:
                fg_emoji = self.formatter.get_fear_greed_emoji(fear_greed['value'])
                message_parts.extend([
                    "🎭 *SENTIMENT*",
                    f"{fg_emoji} Fear & Greed: {fear_greed['value']}/100",
                    f"📝 {fear_greed['classification']}",
                    ""
                ])
            
            # Top movers
            if gainer or loser:
                message_parts.append("📈 *TOP MOVERS*")
                
                if gainer:
                    name = gainer.get('name', 'Unknown')[:15]
                    symbol = gainer.get('symbol', '').upper()
                    change = self.formatter.format_percentage(gainer.get('price_change_percentage_24h', 0))
                    message_parts.append(f"🥇 {name} ({symbol}) {change}")
                
                if loser:
                    name = loser.get('name', 'Unknown')[:15]
                    symbol = loser.get('symbol', '').upper()
                    change = self.formatter.format_percentage(loser.get('price_change_percentage_24h', 0))
                    message_parts.append(f"🥉 {name} ({symbol}) {change}")
                
                message_parts.append("")
            
            # Trending
            if trending:
                message_parts.extend(["🔥 *TRENDING*"])
                for i, coin in enumerate(trending[:3], 1):
                    name = coin.get('name', 'Unknown')[:12]
                    symbol = coin.get('symbol', '').upper()
                    rank = coin.get('market_cap_rank')
                    rank_text = f"#{rank}" if rank else ""
                    message_parts.append(f"{i}. {name} ({symbol}) {rank_text}")
                message_parts.append("")
            
            # DeFi top performer
            if hot_defi:
                top_defi = hot_defi[0]
                tvl = self.formatter.format_number(top_defi.get('tvl', 0))
                change = self.formatter.format_percentage(top_defi.get('change_1d', 0))
                category = top_defi.get('category', 'DeFi')[:8]
                
                message_parts.extend([
                    "🏗️ *TOP DEFI*",
                    f"⭐ {top_defi.get('name', 'Unknown')[:15]}",
                    f"💎 TVL: {tvl} {change}",
                    f"🏗️ {category}",
                    ""
                ])
            
            # Footer
            message_parts.extend([
                "━━━━━━━━━━━━━━━━━━━━",
                f"🤖 *{BOT_NAME}* v{BOT_VERSION}",
                "💡 Use /menu for more options"
            ])
            
            return "\n".join(message_parts)
            
        except Exception as e:
            logger.error(f"Error creating market summary: {e}")
            return self._create_error_message(str(e))
    
    def _create_error_message(self, error: str) -> str:
        """Create error message when data fetching fails"""
        return (
            "⚠️ *MARKET DATA ERROR* ⚠️\n\n"
            f"❌ Unable to fetch data\n"
            f"🔍 Error: {error[:50]}...\n\n"
            "🔄 Try again in a few moments\n"
            f"🤖 *{BOT_NAME}* v{BOT_VERSION}"
        )

# Global bot instance
bot_instance = AlphaScopeBot()

# Command handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_name = update.effective_user.first_name
    
    welcome_message = (
        f"👋 *Welcome {user_name}!*\n\n"
        f"🤖 I'm *{BOT_NAME}* - your crypto intelligence assistant!\n\n"
        "*🚀 What I can do:*\n"
        "• Real-time market analysis\n"
        "• Bitcoin & altcoin tracking\n"
        "• Market sentiment analysis\n"
        "• DeFi protocol insights\n"
        "• Trending cryptocurrency alerts\n\n"
        "*📱 Quick Commands:*\n"
        "/alpha - Market summary\n"
        "/btc - Bitcoin price\n"
        "/trending - Hot coins\n"
        "/defi - Top DeFi projects\n"
        "/menu - All options\n\n"
        "💡 *Add me to groups/channels for shared updates!*"
    )
    
    # Create inline keyboard
    keyboard = [
        [
            InlineKeyboardButton("📊 Market Alpha", callback_data="get_alpha"),
            InlineKeyboardButton("₿ Bitcoin", callback_data="get_btc")
        ],
        [
            InlineKeyboardButton("🔥 Trending", callback_data="get_trending"),
            InlineKeyboardButton("🏗️ DeFi", callback_data="get_defi")
        ],
        [
            InlineKeyboardButton("📋 Menu", callback_data="show_menu"),
            InlineKeyboardButton("ℹ️ Help", callback_data="show_help")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )

async def alpha_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /alpha command"""
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )
    
    message = await bot_instance.create_market_summary()
    await update.message.reply_text(
        message,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )

async def btc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /btc command"""
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )
    
    btc_data = bot_instance.fetcher.get_bitcoin_price()
    if btc_data:
        price = f"${btc_data['price']:,.2f}"
        change = bot_instance.formatter.format_percentage(btc_data.get('change_24h', 0))
        mcap = bot_instance.formatter.format_number(btc_data.get('market_cap', 0))
        
        message = (
            f"₿ *BITCOIN PRICE*\n\n"
            f"💰 *Price:* {price}\n"
            f"📊 *24h Change:* {change}\n"
            f"🏦 *Market Cap:* {mcap}\n\n"
            f"⏰ {datetime.now(timezone.utc).strftime('%H:%M UTC')}"
        )
    else:
        message = "❌ Unable to fetch Bitcoin price data"
    
    await update.message.reply_text(
        message,
        parse_mode=ParseMode.MARKDOWN
    )

async def trending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /trending command"""
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )
    
    trending = bot_instance.fetcher.get_trending_coins()
    if trending:
        message_parts = ["🔥 *TRENDING CRYPTOCURRENCIES*\n"]
        
        for i, coin in enumerate(trending, 1):
            name = coin.get('name', 'Unknown')
            symbol = coin.get('symbol', '').upper()
            rank = coin.get('market_cap_rank')
            rank_text = f"#{rank}" if rank else "Unranked"
            
            message_parts.append(
                f"{i}. *{name}* ({symbol})\n"
                f"    📊 Rank: {rank_text}\n"
            )
        
        message_parts.append(f"\n⏰ {datetime.now(timezone.utc).strftime('%H:%M UTC')}")
        message = "\n".join(message_parts)
    else:
        message = "❌ Unable to fetch trending data"
    
    await update.message.reply_text(
        message,
        parse_mode=ParseMode.MARKDOWN
    )

async def defi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /defi command"""
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )
    
    defi_projects = bot_instance.fetcher.get_hot_defi_projects()
    if defi_projects:
        message_parts = ["🏗️ *TOP DEFI PROTOCOLS*\n"]
        
        for i, project in enumerate(defi_projects[:5], 1):
            name = project.get('name', 'Unknown')
            tvl = bot_instance.formatter.format_number(project.get('tvl', 0))
            change = bot_instance.formatter.format_percentage(project.get('change_1d', 0))
            category = project.get('category', 'DeFi')
            
            message_parts.append(
                f"{i}. *{name}*\n"
                f"    💎 TVL: {tvl}\n"
                f"    📊 24h: {change}\n"
                f"    🏗️ {category}\n"
            )
        
        message_parts.append(f"\n⏰ {datetime.now(timezone.utc).strftime('%H:%M UTC')}")
        message = "\n".join(message_parts)
    else:
        message = "❌ Unable to fetch DeFi data"
    
    await update.message.reply_text(
        message,
        parse_mode=ParseMode.MARKDOWN
    )

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /menu command"""
    menu_message = (
        "📋 *ALPHASCOPE BOT MENU*\n\n"
        "*📊 Market Data:*\n"
        "/alpha - Complete market summary\n"
        "/btc - Bitcoin price & stats\n"
        "/trending - Trending cryptocurrencies\n"
        "/defi - Top DeFi protocols\n\n"
        "*🛠️ Bot Functions:*\n"
        "/menu - Show this menu\n"
        "/help - Detailed help guide\n"
        "/about - Bot information\n\n"
        "*💡 Pro Tips:*\n"
        "• Add me to groups for shared updates\n"
        "• Use buttons for faster access\n"
        "• Commands work in any chat with me\n"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("📊 Alpha", callback_data="get_alpha"),
            InlineKeyboardButton("₿ Bitcoin", callback_data="get_btc")
        ],
        [
            InlineKeyboardButton("🔥 Trending", callback_data="get_trending"),
            InlineKeyboardButton("🏗️ DeFi", callback_data="get_defi")
        ],
        [
            InlineKeyboardButton("ℹ️ Help", callback_data="show_help"),
            InlineKeyboardButton("📝 About", callback_data="show_about")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        menu_message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = (
        f"🤖 *{BOT_NAME} HELP GUIDE*\n\n"
        
        "*🎯 What I Do:*\n"
        "I provide real-time cryptocurrency market intelligence by analyzing data from multiple sources.\n\n"
        
        "*📊 Data Sources:*\n"
        "• CoinGecko - Price & market data\n"
        "• DefiLlama - DeFi TVL data\n"
        "• Alternative.me - Sentiment analysis\n\n"
        
        "*💻 Available Commands:*\n"
        "/start - Welcome & quick buttons\n"
        "/alpha - Full market analysis\n"
        "/btc - Bitcoin price update\n"
        "/trending - Hot cryptocurrencies\n"
        "/defi - Top DeFi protocols\n"
        "/menu - Interactive menu\n"
        "/help - This help guide\n\n"
        
        "*🚀 How to Use:*\n"
        "• Personal chat: Just send any command\n"
        "• Groups: Add me and use commands\n"
        "• Channels: Add me as admin for posting\n\n"
        
        "*💡 Tips:*\n"
        "• Use buttons for faster interaction\n"
        "• All data is real-time and free\n"
        "• Perfect for crypto communities\n"
        "• No configuration required!\n\n"
        
        "🆘 *Need more help?* Contact my creator!"
    )
    
    await update.message.reply_text(
        help_text,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /about command"""
    uptime = datetime.now(timezone.utc) - bot_instance.start_time
    uptime_str = str(uptime).split('.')[0]
    
    about_text = (
        f"🤖 *{BOT_NAME}*\n\n"
        
        f"🔢 *Version:* {BOT_VERSION}\n"
        f"⏰ *Uptime:* {uptime_str}\n"
        f"🚀 *Started:* {bot_instance.start_time.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        
        "*🎯 Features:*\n"
        "• Real-time crypto market data\n"
        "• Bitcoin price tracking\n"
        "• Market sentiment analysis\n"
        "• DeFi protocol monitoring\n"
        "• Trending cryptocurrency alerts\n\n"
        
        "*🔧 Technical:*\n"
        "• Python 3.11+ powered\n"
        "• Multiple API integrations\n"
        "• Error-resilient design\n"
        "• Works in any chat type\n\n"
        
        "*📜 License:* Open Source (MIT)\n"
        "*💝 Created with:* ❤️ for the crypto community"
    )
    
    await update.message.reply_text(
        about_text,
        parse_mode=ParseMode.MARKDOWN
    )

# Callback query handler for inline buttons
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button callbacks"""
    query = update.callback_query
    await query.answer()
    
    await context.bot.send_chat_action(
        chat_id=query.message.chat_id,
        action="typing"
    )
    
    if query.data == "get_alpha":
        message = await bot_instance.create_market_summary()
        await query.edit_message_text(
            message,
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif query.data == "get_btc":
        btc_data = bot_instance.fetcher.get_bitcoin_price()
        if btc_data:
            price = f"${btc_data['price']:,.2f}"
            change = bot_instance.formatter.format_percentage(btc_data.get('change_24h', 0))
            mcap = bot_instance.formatter.format_number(btc_data.get('market_cap', 0))
            
            message = (
                f"₿ *BITCOIN UPDATE*\n\n"
                f"💰 *Price:* {price}\n"
                f"📊 *24h Change:* {change}\n"
                f"🏦 *Market Cap:* {mcap}\n\n"
                f"⏰ {datetime.now(timezone.utc).strftime('%H:%M UTC')}"
            )
        else:
            message = "❌ Unable to fetch Bitcoin data"
        
        await query.edit_message_text(
            message,
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif query.data == "get_trending":
        trending = bot_instance.fetcher.get_trending_coins()
        if trending:
            message_parts = ["🔥 *TRENDING COINS*\n"]
            
            for i, coin in enumerate(trending[:5], 1):
                name = coin.get('name', 'Unknown')[:15]
                symbol = coin.get('symbol', '').upper()
                rank = coin.get('market_cap_rank')
                rank_text = f"#{rank}" if rank else "NR"
                
                message_parts.append(f"{i}. *{name}* ({symbol}) {rank_text}")
            
            message_parts.append(f"\n⏰ {datetime.now(timezone.utc).strftime('%H:%M UTC')}")
            message = "\n".join(message_parts)
        else:
            message = "❌ Unable to fetch trending data"
        
        await query.edit_message_text(
            message,
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif query.data == "get_defi":
        defi_projects = bot_instance.fetcher.get_hot_defi_projects()
        if defi_projects:
            message_parts = ["🏗️ *TOP DEFI PROTOCOLS*\n"]
            
            for i, project in enumerate(defi_projects[:5], 1):
                name = project.get('name', 'Unknown')[:15]
                tvl = bot_instance.formatter.format_number(project.get('tvl', 0))
                change = bot_instance.formatter.format_percentage(project.get('change_1d', 0))
                
                message_parts.append(f"{i}. *{name}*")
                message_parts.append(f"    💎 {tvl} {change}")
            
            message_parts.append(f"\n⏰ {datetime.now(timezone.utc).strftime('%H:%M UTC')}")
            message = "\n".join(message_parts)
        else:
            message = "❌ Unable to fetch DeFi data"
        
        await query.edit_message_text(
            message,
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif query.data == "show_menu":
        await menu_command(update, context)
    elif query.data == "show_help":
        await help_command(update, context)
    elif query.data == "show_about":
        await about_command(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "⚠️ *Something went wrong!*\n\n"
            "Please try again in a moment. If the issue persists, "
            "the APIs might be temporarily unavailable.\n\n"
            "Use /help for assistance.",
            parse_mode=ParseMode.MARKDOWN
        )

def main():
    """Main function - POLLING ONLY (Always Works on Render)"""
    # Validate bot token
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN environment variable not set!")
        print("💡 Get your token from @BotFather on Telegram")
        sys.exit(1)
    
    logger.info(f"🚀 Starting {BOT_NAME} v{BOT_VERSION}")
    logger.info("🌟 Universal mode - works in any chat!")
    
    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("alpha", alpha_command))
    application.add_handler(CommandHandler("btc", btc_command))
    application.add_handler(CommandHandler("trending", trending_command))
    application.add_handler(CommandHandler("defi", defi_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("about", about_command))
    
    # Add callback query handler for inline buttons
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    logger.info("✅ Bot is ready! Commands available:")
    logger.info("   /start - Welcome message")
    logger.info("   /alpha - Market analysis")
    logger.info("   /btc - Bitcoin price")
    logger.info("   /trending - Hot coins")
    logger.info("   /defi - DeFi protocols")
    logger.info("   /menu - Interactive menu")
    
    # SIMPLIFIED: Always use polling (works everywhere)
    try:
        logger.info("🔄 Running in polling mode (works on all platforms)")
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
    except Exception as e:
        logger.error(f"❌ Error running bot: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
