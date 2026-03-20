import matplotlib.pyplot as plt
import japanize_matplotlib
import pandas as pd
from typing import List
import os

def plot_equity_curve(equity_curve: List[float], filename: str = "data/optimization_results.png"):
    """
    Generate and save an equity curve plot.
    """
    if not equity_curve:
        return
        
    plt.figure(figsize=(12, 6))
    plt.plot(equity_curve, label='Equity (資産推移)', color='#1f77b4', linewidth=2)
    
    plt.title('Optimization Results: Equity Curve (最適化結果: 資産推移グラフ)', fontsize=14)
    plt.xlabel('Trades / Time Steps (トレード回数 / ステップ)', fontsize=12)
    plt.ylabel('Equity (USDT)', fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.legend()
    
    # Add final value annotation
    final_equity = equity_curve[-1]
    plt.annotate(f'Final: {final_equity:.2f} USDT', 
                 xy=(len(equity_curve)-1, final_equity),
                 xytext=(len(equity_curve)*0.8, final_equity * 1.05),
                 arrowprops={'facecolor': 'black', 'shrink': 0.05},
                 fontsize=10, weight='bold')

    # Ensure directory exists
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    plt.tight_layout()
    plt.savefig(filename)
    plt.close()
    
    print(f"Equity curve saved to {filename}")
