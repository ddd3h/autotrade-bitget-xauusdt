# Bitget XAUUSDT Automated Trading System

XAUUSDT (Gold/USDT) の USDT-M 永久先物向け、1分足ベースの自動売買システムです。

## システム概要
- **銘柄**: XAUUSDT (USDT-M Perpetual)
- **戦略**: 4本の EMA (Fast, Mid, Trend, Base) を使用したトレンド追随 + 押し目・戻り目 + 再加速エントリー
- **最適化**: Optuna を活用したパラメータチューニング。直近データを重視する指数減衰ウェイト方式。
- **リスク管理**: 許容損失 (Risk per trade) に基づくポジションサイジング、日次損失上限、連敗制限。

## ストラテジーロジック
### エントリー条件 (Long)
1. **トレンド感**: EMA_fast > EMA_mid > EMA_trend > EMA_base かつ 価格 > EMA_trend
2. **ボラティリティ**: ATR が一定以上
3. **押し目**: 直近 N 本の安値が EMA_fast または EMA_mid を下回る（タッチする）
4. **再加速**: EMA_fast 上抜け + 直近の高値更新

### 決済条件
- EMA_fast 下抜け
- EMA のデッドクロス
- 直近安値更新
- 利確 (TP) / 損切り (SL)
- 最大保有時間超過

## ディレクトリ構成
```text
app/
  main.py          # エントリポイント
  config.py        # 設定管理
  logger.py        # ログ管理
  models/          # データモデル
  services/        # コンポーネント（Bitget API、Market Data）
  strategy/        # 戦略ロジック (EMA + Pullback)
  execution/       # 注文執行・ポジション管理
  optimizer/       # Optuna パラメータ最適化
  risk/            # リスク管理
  storage/         # 永続化 (SQLite)
  backtest/        # バックテストエンジン
```

## セットアップ
1. 必要ライブラリのインストール
   ```bash
   pip install -r requirements.txt
   ```
2. `.env` の設定
   `.env.example` を `.env` にコピーし、Bitget の API キーを設定してください。

## 実行方法
### バックテスト
```bash
python -m app.main backtest
```

### パラメータ最適化
```bash
python -m app.main optimize
```

### ペーパー/ライブ運用
```bash
python -m app.main paper
# or
python -m app.main live
```

## 注意事項・免責
- 本ツールは投資の助言を行うものではありません。
- 実際の取引に使用する際は、十分なバックテストとペーパーテストを行ってください。
- API キーは最小限の権限（取引のみ）で作成し、IP 制限をかけることを推奨します。
- 発生したいかなる損失についても、作者は責任を負いません。
