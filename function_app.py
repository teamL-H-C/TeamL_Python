import azure.functions as func
import logging
import json

# Azure Functions v2 プログラミングモデルを使用
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="predict", methods=["GET"])
def predict_beer_sales(req: func.HttpRequest) -> func.HttpResponse:
    """
    Mock API - ビール売上予測 (簡略版)
    """
    logging.info('Mock API called')

    # 日付パラメータを取得
    request_date = req.params.get('date')
    
    # 日付パラメータがない場合はデフォルト値を使用
    if not request_date:
        request_date = "2025-06-13"

    # 簡略化されたモックデータ
    mock_data = {
        "requested_date": request_date,
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

    # JSONレスポンスを返却
    return func.HttpResponse(
        json.dumps(mock_data, ensure_ascii=False),
        status_code=200,
        mimetype="application/json"
    )


@app.route(route="health", methods=["GET"])
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """ヘルスチェック"""
    return func.HttpResponse(
        json.dumps({"status": "ok"}),
        status_code=200,
        mimetype="application/json"
    )
