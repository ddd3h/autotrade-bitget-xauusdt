import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Bitget API
    BITGET_API_KEY: str = ""
    BITGET_API_SECRET: str = ""
    BITGET_API_PASSPHRASE: str = ""
    
    # Bitget Demo API (Sandbox)
    BITGET_DEMO_API_KEY: str = ""
    BITGET_DEMO_API_SECRET: str = ""
    BITGET_DEMO_API_PASSPHRASE: str = ""
    
    # Market
    SYMBOL: str = "XAUUSDT"
    PRODUCT_TYPE: str = "USDT-M"
    MARGIN_COIN: str = "USDT"
    MARGIN_MODE: str = "crossed" # crossed or isolated
    POSITION_MODE: str = "hedge" # one-way or hedge
    LEVERAGE: int = 20
    
    # Risk
    EMERGENCY_STOP_LOSS_ENABLED: bool = True
    EMERGENCY_STOP_LOSS_THRESHOLD: float = 0.05 # 5%
    POSITION_FRACTION: float = 0.4 # 40% of balance as margin
    RISK_PER_TRADE: float = 0.02 # Unused now
    DAILY_LOSS_LIMIT: float = 0.05 # 5% of equity
    CONSECUTIVE_LOSS_LIMIT: int = 5
    
    # Backtest / Optimizer
    RUN_MODE: str = "backtest" # backtest, paper, live, optimize, walkforward
    INITIAL_EQUITY: float = 10000.0
    FEE_RATE: float = 0.0006 # 0.06% taker fee
    SLIPPAGE_BPS: float = 5.0 # 0.05%
    
    # Optimizer
    OPTIMIZER_ALPHA: float = 1.0
    OPTIMIZER_BETA: float = 0.1
    OPTIMIZER_GAMMA: float = 0.5
    
    # Notifications
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    PUSHBULLET_API_KEY: str = ""
    NGROK_AUTH_TOKEN: str = ""
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
