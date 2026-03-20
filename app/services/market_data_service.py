import asyncio
from typing import Optional, List
import pandas as pd
from datetime import datetime, timedelta
from app.services.bitget_service import BitgetService
from app.logger import export_logger as logger
from app.config import settings

class MarketDataService:
    def __init__(self, bitget_service: BitgetService):
        self.bitget = bitget_service

    async def fetch_data(self, limit: int = 500) -> Optional[pd.DataFrame]:
        """Fetch the latest OHLCV data for the current cycle."""
        try:
            # We use the configured symbol from settings
            from app.config import settings
            df = await self.bitget.fetch_ohlcv(settings.SYMBOL, timeframe='1m', limit=limit)
            if df is not None and not df.empty:
                return self.validate_candles(df)
            return None
        except Exception as e:
            logger.error(f"Error in fetch_data: {e}")
            return None

    async def fetch_historical_candles(self, symbol: str, days: int = 7) -> pd.DataFrame:
        """Fetch historical 1m candles for the last N days."""
        logger.info(f"Fetching up to {days} days of historical 1m candles for {symbol}...")
        
        limit = 200  # Smaller limit to ensure loop continues correctly on Bitget V2
        timeframe = '1m'
        since = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
        max_candles = 10000 # Limit to ~7 days of 1m data to avoid extreme delays
        
        all_candles = []
        while len(all_candles) * limit < max_candles:
            try:
                df = await self.bitget.fetch_ohlcv(symbol, timeframe, limit=limit, since=since)
                if df is None or df.empty:
                    break
                
                all_candles.append(df)
                # Update 'since' to the last timestamp + timeframe (1 min)
                # Ensure we advance to avoid infinite loops
                last_ts = int(df.index[-1].timestamp() * 1000)
                since = last_ts + 60000 # 60 seconds
                
                # If the batch was smaller than requested, we might be at the end
                if len(df) < limit:
                    # But don't break immediately—only if current timestamp is very recent
                    now_ms = int(datetime.now().timestamp() * 1000)
                    if since >= now_ms - 60000:
                        break
                        
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Error in fetch loop: {e}")
                break
            
        if not all_candles:
            return pd.DataFrame()
            
        full_df = pd.concat(all_candles)
        full_df = full_df[~full_df.index.duplicated(keep='first')]
        full_df.sort_index(inplace=True)
        
        logger.info(f"Total historical candles fetched: {len(full_df)}")
        return full_df

    def validate_candles(self, df: pd.DataFrame) -> pd.DataFrame:
        """Check for missing candles and fill them."""
        # Find gaps
        expected_range = pd.date_range(start=df.index[0], end=df.index[-1], freq='1min')
        if len(df) < len(expected_range):
            logger.warning(f"Detected {len(expected_range) - len(df)} missing candles. Interpolating...")
            df = df.reindex(expected_range)
            df.interpolate(method='linear', inplace=True)
            df.ffill(inplace=True)
            
        return df
