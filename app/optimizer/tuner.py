import optuna
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any
from app.strategy.engine import StrategyEngine, StrategyParams
from app.backtest.engine import BacktestEngine
from app.config import settings
from app.logger import export_logger as logger

class ParameterOptimizer:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        # Calculate weights for objective function
        self.df_with_dates = df.copy()
        max_date = self.df_with_dates.index.max()
        self.df_with_dates['age_days'] = (max_date - self.df_with_dates.index).days
        # lambda for 30 days = 0.15 weight -> exp(-lambda * 30) = 0.15 -> lambda = -ln(0.15)/30
        self.decay_lambda = -np.log(0.15) / 30

    def objective(self, trial: optuna.Trial) -> float:
        params = StrategyParams(
            ema_fast=trial.suggest_int('ema_fast', 10, 40),
            ema_mid=trial.suggest_int('ema_mid', 50, 100),
            ema_trend=trial.suggest_int('ema_trend', 110, 200),
            ema_base=trial.suggest_int('ema_base', 210, 500),
            atr_len=trial.suggest_int('atr_len', 14, 50),
            atr_min=trial.suggest_float('atr_min', 1.0, 5.0),
            pullback_bars=trial.suggest_int('pullback_bars', 5, 20),
            tp_usd=trial.suggest_float('tp_usd', 15.0, 50.0), # Encourage larger moves
            sl_usd=trial.suggest_float('sl_usd', 10.0, 30.0),
            hold_max_minutes=trial.suggest_int('hold_max_minutes', 15, 240),
            strict_trigger=trial.suggest_categorical('strict_trigger', [True, False])
        )
        
        strategy = StrategyEngine(params)
        backtest = BacktestEngine(self.df, strategy)
        results = backtest.run()
        
        # Penalize too few OR too many trades
        # Goal: ~2-5 trades per day. For 7 days, that's 15-35 trades.
        trades_count = results['total_trades']
        if "msg" in results or trades_count < 5 or trades_count > 100: 
            return -99999.0
        
        # 1. Net PnL (Scaled)
        wnp = results['net_pnl']
        
        # 2. Profit Factor (High priority)
        df_trades = pd.DataFrame([t.model_dump() for t in backtest.trades])
        gains = df_trades[df_trades['net_pnl'] > 0]['net_pnl'].sum()
        losses = abs(df_trades[df_trades['net_pnl'] < 0]['net_pnl'].sum())
        profit_factor = (gains / losses) if losses > 0 else 1.0
        if profit_factor < 1.1: # Must be profitable before fees
             return -50000.0
        
        # 3. Penalties
        mdd_penalty = abs(results['max_drawdown']) * 20000
        
        # 4. Win rate constraint (Strict)
        win_rate = results['win_rate']
        wr_penalty = 0
        if win_rate < 0.60:
            wr_penalty = (0.60 - win_rate) * 50000 
            
        # Composite Score
        score = wnp + (profit_factor * 1000) - mdd_penalty - wr_penalty
        
        return score

    def optimize(self, n_trials: int = 100):
        study = optuna.create_study(direction='maximize')
        study.optimize(self.objective, n_trials=n_trials)
        logger.info(f"Best parameters: {study.best_params}")
        logger.info(f"Best score: {study.best_value}")
        return study.best_params
