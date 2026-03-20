import asyncio
import argparse
import sys
from datetime import datetime, timedelta
from app.services.bitget_service import BitgetService
from app.services.market_data_service import MarketDataService
from app.strategy.engine import StrategyEngine, StrategyParams
from app.backtest.engine import BacktestEngine
from app.optimizer.tuner import ParameterOptimizer
from app.execution.engine import ExecutionEngine
from app.risk.manager import RiskManager
from app.services.notification_service import NotificationService
from app.storage.database import StorageService
from app.utils.params import save_optimized_params, load_optimized_params
from app.config import settings
from app.logger import export_logger as logger

async def run_backtest():
    logger.info("Starting 30-day backtest simulation...")
    bitget = BitgetService()
    md = MarketDataService(bitget)
    
    # Fetch 30 days of data
    df = await md.fetch_historical_candles("XAUUSDT", days=30)
    await bitget.close()
    
    if df.empty:
        logger.error("No data found for backtest.")
        return
        
    params = load_optimized_params()
    strategy = StrategyEngine(params)
    backtest = BacktestEngine(df, strategy)
    results = backtest.run()
    
    # Display Results & Verdict
    logger.info("=" * 40)
    logger.info("BACKTEST 30-DAY RESULTS")
    logger.info("=" * 40)
    logger.info(f"Net PnL: {results.get('net_pnl', 0):.2f} USDT")
    logger.info(f"Win Rate: {results.get('win_rate', 0)*100:.1f}%")
    logger.info(f"Max Drawdown: {results.get('max_drawdown', 0)*100:.2f}%")
    logger.info(f"Total Trades: {results.get('total_trades', 0)}")
    logger.info("-" * 40)
    
    if "verdict" in results:
        v = results["verdict"]
        logger.info(f"FINAL VERDICT: {v['status']}")
        for criterion, passed in v["details"].items():
            status_str = "✓ PASS" if passed else "✗ FAIL"
            logger.info(f"  [{status_str}] {criterion}")
    logger.info("=" * 40)
    
    # Generate PnL Graph
    if "net_pnl" in results:
        from app.utils.plotting import plot_equity_curve
        plot_equity_curve(backtest.equity_curve, filename="data/backtest_results_30d.png")

from app.utils.plotting import plot_equity_curve

async def run_optimize():
    logger.info("Starting optimization mode...")
    bitget = BitgetService()
    md = MarketDataService(bitget)
    df = await md.fetch_historical_candles("XAUUSDT", days=30)
    await bitget.close()
    
    if df.empty:
        logger.error("No data found for optimization.")
        return
        
    optimizer = ParameterOptimizer(df)
    best_params = optimizer.optimize(n_trials=50)
    logger.info(f"Optuna Best Params: {best_params}")
    save_optimized_params(best_params)
    
    # Run one final backtest with best parameters to generate the graph
    logger.info("Generating final PnL graph for the best parameters...")
    from app.strategy.engine import StrategyParams
    strategy_params = StrategyParams(**best_params)
    strategy = StrategyEngine(strategy_params)
    backtest = BacktestEngine(df, strategy)
    results = backtest.run()
    
    if "final_equity" in results:
        plot_equity_curve(backtest.equity_curve)
        logger.info(f"Final Optimization Backtest: {results}")
    else:
        logger.warning("Could not generate PnL graph – no trades executed in best trial.")

async def run_demo_v0():
    """Demo Live v0: Just place random orders to check if functions are correct."""
    from app.services.bitget_service import BitgetService
    from app.logger import export_logger as logger
    import random
    import asyncio
    
    logger.info("Starting Demo Live v0 - Connectivity Test")
    bitget = BitgetService(use_demo=True)
    
    try:
        # Load markets
        await bitget.client.load_markets()
        
        # Check balance first
        balance = await bitget.get_balance('USDT')
        if isinstance(balance, dict):
            logger.info(f"Demo USDT Balance: {balance.get('total', 'unknown')} (Available: {balance.get('free', 'unknown')})")
        else:
            logger.info(f"Demo USDT Balance: {balance}")

        # Try 5 small trades
        for i in range(1, 6):
            side = 'buy' if i % 2 != 0 else 'sell'
            amount = 0.01 # Minimum for XAU/USDT
            logger.info(f"Test Order {i}/5: {side} {amount}")
            try:
                order = await bitget.create_market_order(settings.SYMBOL, side, amount)
                logger.info(f"Order Success: {order['id']}")
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Order Failed: {e}")
            await asyncio.sleep(1)
            
    finally:
        await bitget.close()
        logger.info("Demo Live v0 finished")

async def run_trading(mode: str):
    logger.info(f"Starting {mode} trading mode...")
    
    if mode == "demo_v0":
        await run_demo_v0()
        return

    # Strict credential check
    if not all([settings.BITGET_API_KEY, settings.BITGET_API_SECRET, settings.BITGET_API_PASSPHRASE]) and mode not in ["demo_v0", "demo_v1"]:
        logger.error("API credentials (Key, Secret, Passphrase) are missing in .env. Cannot start.")
        return

    # Start Web Dashboard in separate thread
    from app.web.server import run_server
    import threading
    threading.Thread(target=run_server, daemon=True).start()
    
    dashboard_url = "http://localhost:8000"
    
    # Ngrok Integration
    if settings.NGROK_AUTH_TOKEN:
        try:
            from pyngrok import ngrok
            ngrok.set_auth_token(settings.NGROK_AUTH_TOKEN)
            public_url = ngrok.connect(8000).public_url
            dashboard_url = public_url
            logger.info(f"Ngrok tunnel established: {dashboard_url}")
        except Exception as e:
            logger.error(f"Failed to start ngrok: {e}")

    logger.info(f"Web dashboard available at {dashboard_url}")

    use_demo = (mode == "demo_v1")
    bitget = BitgetService(use_demo=use_demo)
    md = MarketDataService(bitget)
    storage = StorageService()
    
    # Get balance
    balance = await bitget.get_balance()
    if balance <= 0 and not (use_demo or mode == "paper"):
        logger.error(f"Failed to fetch balance or balance is 0. Check credentials and account status.")
        await bitget.close()
        return
    elif (use_demo or mode == "paper") and balance <= 0:
        logger.warning(f"{mode.capitalize()} balance is 0 or failed to fetch. Using default 10000 for simulation if needed.")
        balance = 10000.0
        
    risk = RiskManager(balance)
    params = load_optimized_params()
    strategy = StrategyEngine(params)
    notifier = NotificationService()
    
    # Startup Notification
    notify_mode = mode.upper()
    await notifier.send_telegram(f"🚀 Trading Bot Started ({notify_mode})\nDashboard: {dashboard_url}")
    await notifier.send_pushbullet(f"Trading Bot Started ({notify_mode})", f"Dashboard: {dashboard_url}")
    
    execution = ExecutionEngine(bitget, strategy, risk, notifier, storage)
    
    try:
        while True:
            # Fetch data
            df = await md.fetch_data()
            if df is not None:
                # Execute strategy
                await execution.execute_cycle(df)
            
            # Wait for next cycle
            # Use high-frequency (5s) if holding a position, else default (60s)
            sleep_time = 5 if execution.current_pos else 60
            await asyncio.sleep(sleep_time)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await bitget.close()

async def run_walkforward():
    logger.info("Starting walk-forward test...")
    bitget = BitgetService()
    md = MarketDataService(bitget)
    df = await md.fetch_historical_candles("XAUUSDT", days=40)
    await bitget.close()
    
    # Simple Walk-forward: 30 days train, 1 day test, roll forward
    window_train = 30
    window_test = 1
    
    total_days = (df.index.max() - df.index.min()).days
    current_start = df.index.min()
    
    all_test_trades = []
    
    while current_start + timedelta(days=window_train + window_test) <= df.index.max():
        train_end = current_start + timedelta(days=window_train)
        test_end = train_end + timedelta(days=window_test)
        
        train_df = df.loc[current_start:train_end]
        test_df = df.loc[train_end:test_end]
        
        logger.info(f"Training from {current_start.date()} to {train_end.date()}")
        optimizer = ParameterOptimizer(train_df)
        best_params = optimizer.optimize(n_trials=30)
        
        logger.info(f"Testing from {train_end.date()} to {test_end.date()}")
        strategy = StrategyEngine(StrategyParams(**best_params))
        backtest = BacktestEngine(test_df, strategy)
        results = backtest.run()
        
        if "trades" in results: # Simplified
             pass
        
        current_start += timedelta(days=window_test)

def main():
    parser = argparse.ArgumentParser(description="Bitget XAUUSDT Trading Bot")
    parser.add_argument("mode", choices=["backfill", "backtest", "optimize", "walkforward", "paper", "live", "demo_v0", "demo_v1"])
    args = parser.parse_args()
    
    if args.mode == "backtest":
        asyncio.run(run_backtest())
    elif args.mode == "optimize":
        asyncio.run(run_optimize())
    elif args.mode in ["paper", "live", "demo_v1"]:
        settings.RUN_MODE = args.mode
        asyncio.run(run_trading(args.mode))
    elif args.mode == "demo_v0":
        asyncio.run(run_trading("demo_v0"))
    elif args.mode == "walkforward":
        asyncio.run(run_walkforward())
    else:
        logger.info(f"Mode {args.mode} not implemented or handled yet.")

if __name__ == "__main__":
    main()
