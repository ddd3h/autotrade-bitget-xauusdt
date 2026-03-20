import json
import os
from typing import Dict, Any
from app.strategy.engine import StrategyParams
from app.logger import export_logger as logger

PARAMS_PATH = "data/optimized_params.json"

def save_optimized_params(params: Dict[str, Any]):
    os.makedirs(os.path.dirname(PARAMS_PATH), exist_ok=True)
    with open(PARAMS_PATH, "w") as f:
        json.dump(params, f, indent=4)
    logger.info(f"Optimized parameters saved to {PARAMS_PATH}")

def load_optimized_params() -> StrategyParams:
    if os.path.exists(PARAMS_PATH):
        try:
            with open(PARAMS_PATH, "r") as f:
                data = json.load(f)
                logger.info(f"Loaded optimized parameters from {PARAMS_PATH}")
                return StrategyParams(**data)
        except Exception as e:
            logger.error(f"Error loading parameters: {e}")
            
    logger.info("Using default strategy parameters.")
    return StrategyParams()
