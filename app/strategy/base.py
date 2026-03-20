from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, Any, Optional

class BaseStrategy(ABC):
    @abstractmethod
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators required for the strategy."""
        pass

    @abstractmethod
    def get_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate entry and exit signal columns in the DataFrame."""
        pass

    @abstractmethod
    def check_exit(self, position: Dict, current_candle: pd.Series, prev_candle: pd.Series) -> Optional[str]:
        """Check for exit conditions based on current position and market state."""
        pass
