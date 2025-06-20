# 機械学習モデル訓練資料

このフォルダには、ビール出荷予測AIモデルの訓練に使用された資料が含まれています。

## ファイル構成

### 📊 データセット
- `df_merge (2).csv` - 統合されたビール売上データと天気データ
  - 期間: 2024年4月〜2025年3月
  - 内容: クラフトビール売上実績 + 気象データ

### 🧪 Jupyter Notebook
- `rf.ipynb` - RandomForestモデル訓練ノートブック
  - 特徴量エンジニアリング実装
  - モデル訓練とハイパーパラメータ調整
  - 統一RandomForestモデル構築
  - 評価指標とパフォーマンス分析

## 📈 訓練されたモデル

最終的に以下のモデルファイルが生成され、Azure Functions で使用されています：

- `unified_rf_model.joblib` - 統一RandomForestモデル
- `improved_features.joblib` - 特徴量リスト
- `beer_sales_columns.joblib` - ビール種類カラム
- `weather_label_encoder.joblib` - 天気ラベルエンコーダー

## 🚀 運用環境

訓練されたモデルは Azure Functions にデプロイされ、週単位のビール出荷予測APIとして稼働中です。

## 📝 注意事項

- このフォルダのファイルは参考用です
- 運用環境では最新のモデルファイル（models/フォルダ）を使用
- データファイルは機密情報を含むため、本番デプロイには含まれません
