# ビール売上予測 Mock API 使用説明書

## 📖 このプログラムについて

このプログラムは、ビール売上を予測するMock（模擬）APIです。
実際の予測は行いませんが、開発やテスト用に固定のデータを返します。

## 🚀 プログラムの使い方

### ステップ1: プログラムを起動する

ターミナル（コマンドプロンプト）を開いて、以下のコマンドを入力してください：

```bash
func start
```

成功すると、以下のような表示が出ます：
```
Functions:
    health_check: [GET] http://localhost:7071/api/health
    predict_beer_sales: [GET] http://localhost:7071/api/predict
```

### ステップ2: APIを使用する

プログラムが起動したら、以下の方法でAPIを使用できます：

#### 方法1: ブラウザで確認
ブラウザのアドレスバーに以下のURLを入力：
```
http://localhost:7071/api/predict?date=2025-06-13
```

#### 方法2: コマンドで確認
新しいターミナルウィンドウを開いて：
```bash
curl "http://localhost:7071/api/predict?date=2025-06-13"
```

### ステップ3: プログラムを停止する

プログラムを停止したい時は、起動したターミナルで `Ctrl+C` を押してください。

## 📋 何ができるか

### 1. ビール売上の予測データを取得
- **使い方**: `http://localhost:7071/api/predict?date=2025-06-13`
- **説明**: 指定した日付のビール売上予測データを取得します
- **日付の形式**: YYYY-MM-DD（例：2025-06-13）

### 2. プログラムの動作確認
- **使い方**: `http://localhost:7071/api/health`
- **説明**: プログラムが正常に動作しているかを確認します

## 🎯 返ってくるデータの例

ビール予測APIを呼び出すと、以下のようなデータが返ってきます：

```json
{
  "requested_date": "2025-06-13",
  "predictions": [
    {"beer_id": 1, "beer_name": "ホワイトビール", "predicted_quantity": 15},
    {"beer_id": 2, "beer_name": "ラガー", "predicted_quantity": 22},
    {"beer_id": 3, "beer_name": "ペールエール", "predicted_quantity": 18},
    {"beer_id": 4, "beer_name": "フルーツビール", "predicted_quantity": 8},
    {"beer_id": 5, "beer_name": "黒ビール", "predicted_quantity": 12},
    {"beer_id": 6, "beer_name": "IPA", "predicted_quantity": 35}
  ],
  "comment": "Mock API - テストデータ"
}
```

**データの意味:**
- `requested_date`: 指定した日付
- `predictions`: ビールの予測データのリスト
  - `beer_id`: ビールのID番号
  - `beer_name`: ビールの名前（日本語）
  - `predicted_quantity`: 予測販売数量
- `comment`: このデータがテスト用であることの説明

## ❓ よくある質問

### Q: 日付を指定しないとどうなりますか？
A: 自動的に `2025-06-13` の予測データが返されます。

**例:**
```
http://localhost:7071/api/predict
```
↑これでも動作します

### Q: エラーが出たときはどうすればいいですか？
A: 以下を確認してください：
1. `func start` でプログラムが起動しているか
2. URLが正しいか（`http://localhost:7071`）
3. 日付の形式が正しいか（YYYY-MM-DD）

### Q: 他の人に使ってもらうには？
A: あなたのPCでプログラムを起動していれば、同じネットワーク上の人が使用できます。

## 🔧 トラブルシューティング

### プログラムが起動しない場合
```bash
# 必要なツールがインストールされているか確認
func --version

# 依存関係をインストール
pip install -r requirements.txt
```

### ポートが使用中の場合
別のプログラムがポート7071を使用している可能性があります。
一度PCを再起動するか、他のプログラムを終了してから再試行してください。

## 📝 注意事項

⚠️ **重要**: このプログラムは**テスト用**です
- 実際の売上予測は行いません
- 常に同じ固定データを返します
- 開発・テスト目的でのみ使用してください

## 📞 サポート

質問や問題がある場合は、TeamLのメンバーまでお声がけください。
