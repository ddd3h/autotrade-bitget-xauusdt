import pytest
import pandas as pd
import numpy as np
from app.strategy.engine import StrategyEngine, StrategyParams

def test_strategy_indicators():
    # Create dummy data
    data = {
        'open': [100.0] * 200,
        'high': [102.0] * 200,
        'low': [98.0] * 200,
        'close': [101.0] * 200,
        'volume': [1000] * 200
    }
    df = pd.DataFrame(data)
    
    params = StrategyParams()
    strategy = StrategyEngine(params)
    df_with_inds = strategy.calculate_indicators(df)
    
    assert 'ema_fast' in df_with_inds.columns
    assert 'atr' in df_with_inds.columns
    assert not df_with_inds['ema_fast'].isnull().all()

def test_long_entry_signal():
    # Setup data where trend is clearly up
    prices = np.linspace(100, 200, 200)
    data = {
        'open': prices,
        'high': prices + 2,
        'low': prices - 1,
        'close': prices + 1,
        'volume': [1000] * 200
    }
    df = pd.DataFrame(data)
    
    params = StrategyParams(ema_fast=5, ema_mid=10, ema_trend=20, ema_base=50)
    strategy = StrategyEngine(params)
    signals = strategy.get_signals(df)
    
    # Check if trend_up is detected
    assert signals['trend_up'].iloc[-1] == True
