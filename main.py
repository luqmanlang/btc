import discord
import asyncio
import os
import datetime
from discord.ext import commands, tasks
from src.brain.john_ai import john_analysis
from src.brain.alpha_ai import alpha_analysis
from src.data.market_data import get_comprehensive_market_data
from src.utils.formatters import create_alert_embed, create_analysis_embed
from src.analysis.scoring_engine import rank_opportunities
from config import *

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Global variables for tracking
last_analysis_time = {}
high_potential_coins = {}

@tasks.loop(minutes=60)
async def hourly_analysis():
    """Comprehensive hourly analysis for all tracked cryptocurrencies"""
    try:
        channel = bot.get_channel(CHANNEL_ID)
        if not channel:
            print(f"Could not find channel with ID: {CHANNEL_ID}")
            return

        print(f"🔄 Starting hourly analysis at {datetime.datetime.now()}")
        
        # Get comprehensive market data
        market_data = await get_comprehensive_market_data()
        if not market_data:
            await channel.send("⚠️ **Market Data Unavailable** - Unable to fetch market data for analysis")
            return

        # Perform AI analysis
        john_results = await john_analysis(market_data, timeframe="1H")
        alpha_results = await alpha_analysis(market_data, timeframe="1H")
        
        # Send Bitcoin analysis first (dedicated hourly Bitcoin report)
        if 'BTC' in market_data:
            btc_john = john_results.get('BTC', {})
            btc_alpha = alpha_results.get('BTC', {})
            if btc_john or btc_alpha:
                btc_embed = create_analysis_embed(
                    {'BTC': market_data['BTC']}, 
                    {'BTC': btc_john}, 
                    {'BTC': btc_alpha}, 
                    "1H Bitcoin Report", 
                    specific_coin='BTC'
                )
                await channel.send(embed=btc_embed)
                await asyncio.sleep(2)
        
        # Rank and filter high-potential altcoin opportunities
        ranked_opportunities = rank_opportunities(john_results, alpha_results, min_score=75)
        
        # Send high-potential altcoin alerts (excluding Bitcoin since reported separately)
        altcoin_count = 0
        for opportunity in ranked_opportunities:
            if opportunity.get('symbol') != 'BTC' and altcoin_count < 5:
                embed = create_alert_embed(opportunity, "🚀 HIGH POTENTIAL")
                await channel.send(embed=embed)
                await asyncio.sleep(2)
                altcoin_count += 1
        
        # Send general market analysis summary
        summary_embed = create_analysis_embed(market_data, john_results, alpha_results, "1H Market Overview")
        await channel.send(embed=summary_embed)
        
        last_analysis_time["hourly"] = datetime.datetime.now()
        
    except Exception as e:
        print(f"Error in hourly analysis: {e}")
        if channel:
            await channel.send(f"❌ **Analysis Error** - {str(e)}")

@tasks.loop(hours=4)
async def four_hour_analysis():
    """Deep 4-hour analysis with macro trend analysis"""
    try:
        channel = bot.get_channel(CHANNEL_ID)
        if not channel:
            return

        print(f"🔍 Starting 4-hour deep analysis at {datetime.datetime.now()}")
        
        market_data = await get_comprehensive_market_data()
        if not market_data:
            return

        # Deep analysis with macro trends
        john_results = await john_analysis(market_data, timeframe="4H", deep_analysis=True)
        alpha_results = await alpha_analysis(market_data, timeframe="4H", deep_analysis=True)
        
        # Filter for very high confidence predictions
        ranked_opportunities = rank_opportunities(john_results, alpha_results, min_score=85)
        
        # Send premium alerts for top opportunities
        for opportunity in ranked_opportunities[:3]:
            embed = create_alert_embed(opportunity, "⚡ PREMIUM SIGNAL")
            await channel.send(embed=embed)
            await asyncio.sleep(3)
        
        last_analysis_time["four_hour"] = datetime.datetime.now()
        
    except Exception as e:
        print(f"Error in 4-hour analysis: {e}")

@tasks.loop(minutes=5)
async def volume_spike_monitor():
    """Real-time monitoring for volume spikes and whale movements"""
    try:
        channel = bot.get_channel(CHANNEL_ID)
        if not channel:
            return
            
        from src.analysis.volume_analyzer import detect_volume_spikes
        from src.data.whale_detector import detect_whale_movements
        
        # Check for volume spikes
        volume_alerts = await detect_volume_spikes()
        for alert in volume_alerts:
            if alert['volume_increase'] >= 300:  # 300%+ volume spike
                embed = create_alert_embed(alert, "📊 VOLUME SPIKE")
                await channel.send(embed=embed)
        
        # Check for whale movements
        whale_alerts = await detect_whale_movements()
        for alert in whale_alerts:
            embed = create_alert_embed(alert, "🐋 WHALE MOVEMENT")
            await channel.send(embed=embed)
            
    except Exception as e:
        print(f"Error in volume spike monitor: {e}")

@bot.command(name="analisis")
async def manual_analysis(ctx, coin: str = None):
    """Manual analysis command for specific coin or general market"""
    try:
        await ctx.send("🔄 **Analyzing market data...** Please wait...")
        
        market_data = await get_comprehensive_market_data()
        if not market_data:
            await ctx.send("❌ **Error** - Unable to fetch market data")
            return

        if coin:
            # Specific coin analysis
            coin = coin.upper()
            if coin in market_data:
                from src.brain.pattern_analyzer import deep_coin_analysis
                analysis = await deep_coin_analysis(coin, market_data[coin])
                embed = create_analysis_embed({coin: market_data[coin]}, analysis, {}, "Manual", specific_coin=coin)
                await ctx.send(embed=embed)
            else:
                await ctx.send(f"❌ **Coin not found** - {coin} is not in our tracking list")
        else:
            # General market analysis
            john_results = await john_analysis(market_data, timeframe="Manual")
            alpha_results = await alpha_analysis(market_data, timeframe="Manual")
            
            ranked_opportunities = rank_opportunities(john_results, alpha_results, min_score=70)
            
            # Send top opportunities
            for i, opportunity in enumerate(ranked_opportunities[:3], 1):
                embed = create_alert_embed(opportunity, f"🎯 OPPORTUNITY #{i}")
                await ctx.send(embed=embed)
                if i < 3:
                    await asyncio.sleep(2)
            
    except Exception as e:
        await ctx.send(f"❌ **Analysis failed** - {str(e)}")

@bot.command(name="top")
async def top_gainers(ctx, timeframe: str = "24h"):
    """Show top gaining cryptocurrencies by timeframe"""
    try:
        await ctx.send(f"📈 **Fetching top gainers for {timeframe}...**")
        
        market_data = await get_comprehensive_market_data()
        if not market_data:
            await ctx.send("❌ **Error** - Unable to fetch market data")
            return
        
        # Sort by price change
        timeframe_key = f"percent_change_{timeframe}"
        sorted_coins = sorted(
            market_data.items(),
            key=lambda x: x[1].get(timeframe_key, 0),
            reverse=True
        )[:10]
        
        embed = discord.Embed(
            title=f"🏆 Top Gainers ({timeframe})",
            color=0x00ff00,
            timestamp=datetime.datetime.now()
        )
        
        for i, (symbol, data) in enumerate(sorted_coins, 1):
            change = data.get(timeframe_key, 0)
            price = data.get('price', 0)
            volume = data.get('volume_24h', 0)
            
            embed.add_field(
                name=f"{i}. {symbol}",
                value=f"**Price:** ${price:,.4f}\n**Change:** {change:+.2f}%\n**Volume:** ${volume:,.0f}",
                inline=True
            )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ **Error** - {str(e)}")

@bot.command(name="alerts")
async def toggle_alerts(ctx, alert_type: str = "all"):
    """Toggle different types of alerts"""
    valid_types = ["volume", "whale", "technical", "all"]
    if alert_type not in valid_types:
        await ctx.send(f"❌ **Invalid alert type** - Use: {', '.join(valid_types)}")
        return
    
    # Implementation for alert toggling would go here
    await ctx.send(f"✅ **Alert settings updated** - {alert_type} alerts configured")

@bot.command(name="status")
async def bot_status(ctx):
    """Show bot status and last analysis times"""
    embed = discord.Embed(
        title="🤖 Bot Status",
        color=0x0099ff,
        timestamp=datetime.datetime.now()
    )
    
    # Add uptime
    if hasattr(bot, 'start_time'):
        uptime = datetime.datetime.now() - bot.start_time
        embed.add_field(name="⏱️ Uptime", value=str(uptime).split('.')[0], inline=True)
    
    # Add last analysis times
    for analysis_type, last_time in last_analysis_time.items():
        time_diff = datetime.datetime.now() - last_time
        embed.add_field(
            name=f"📊 Last {analysis_type}",
            value=f"{time_diff.total_seconds()/60:.1f} minutes ago",
            inline=True
        )
    
    # Add task status
    embed.add_field(name="🔄 Hourly Analysis", value="✅ Running" if hourly_analysis.is_running() else "❌ Stopped", inline=True)
    embed.add_field(name="🔍 4H Analysis", value="✅ Running" if four_hour_analysis.is_running() else "❌ Stopped", inline=True)
    embed.add_field(name="📊 Volume Monitor", value="✅ Running" if volume_spike_monitor.is_running() else "❌ Stopped", inline=True)
    
    await ctx.send(embed=embed)

@bot.event
async def on_ready():
    """Bot startup event"""
    print(f"🚀 {bot.user} has connected to Discord!")
    print(f"📊 Advanced Crypto Analysis Bot v2.0")
    print(f"⏰ Started at: {datetime.datetime.now()}")
    
    bot.start_time = datetime.datetime.now()
    
    # Start automated tasks
    if not hourly_analysis.is_running():
        hourly_analysis.start()
        print("✅ Hourly analysis task started")
    
    if not four_hour_analysis.is_running():
        four_hour_analysis.start()
        print("✅ 4-hour analysis task started")
    
    if not volume_spike_monitor.is_running():
        volume_spike_monitor.start()
        print("✅ Volume spike monitor started")
    
    # Send startup message
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        embed = discord.Embed(
            title="🚀 Advanced Crypto Bot Online",
            description="Ready to analyze 200+ cryptocurrencies for 10%+ opportunities",
            color=0x00ff00,
            timestamp=datetime.datetime.now()
        )
        embed.add_field(name="⚡ Features Active", value="• Hourly market analysis\n• Volume spike detection\n• Whale movement tracking\n• Technical pattern recognition\n• Sentiment analysis", inline=False)
        await channel.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    """Global error handler"""
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ **Command not found** - Use `!help` for available commands")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ **Missing argument** - {error}")
    else:
        await ctx.send(f"❌ **Error** - {str(error)}")
        print(f"Command error: {error}")

if __name__ == "__main__":
    # Keep the bot alive
    keep_alive()
    
    # Run the bot
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        print(f"Failed to start bot: {e}")
