import azure.functions as func
import logging
import json
import os
import pandas as pd
import numpy as np
import requests
from datetime import datetime

# 尝试导入必要的库
try:
    import joblib
except ImportError:
    logging.critical("joblib 或 scikit-learn 未安装。请将其添加到 requirements.txt。")

# Azure Functions v2 プログラミングモデルを使用
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# --- 啤酒销售预测器类 ---
class BeerSalesPredictorAzure:
    def __init__(self, model_dir_name="models"):
        self.models = {}
        self.weather_label_encoder = None
        
        # 特征列名和顺序：必须与您在 Colab 中训练时使用的完全一致
        self.feature_cols_from_colab = [
            "平均気温(℃)",
            "降水量の合計(mm)",
            "平均風速(m/s)",
            "平均湿度(％)",
            "曜日番号"
        ]

        # 啤酒模型映射 - 根据您从Colab保存的模型调整
        self.beer_target_col_to_model_key = {
            "ペールエール(本)": "decision_tree_model",  # 假设您的模型是这个名字
            "ラガー(本)": "decision_tree_model",
            "IPA(本)": "decision_tree_model", 
            "ホワイトビール(本)": "decision_tree_model",
            "黒ビール(本)": "decision_tree_model",
            "フルーツビール(本)": "decision_tree_model"
        }
        
        # API 输出顺序
        self.beer_names_for_output_ordered = [
            "ホワイトビール(本)",
            "ラガー(本)", 
            "ペールエール(本)",
            "フルーツビール(本)",
            "黒ビール(本)",
            "IPA(本)"
        ]

        self._load_models_and_encoder(model_dir_name)

    def _load_models_and_encoder(self, model_dir_name):
        script_dir = os.path.dirname(__file__)
        actual_model_dir = os.path.join(script_dir, model_dir_name)
        logging.info(f"尝试从以下目录加载模型: {actual_model_dir}")

        if not os.path.isdir(actual_model_dir):
            logging.error(f"模型目录未找到: {actual_model_dir}")
            return

        # 加载决策树模型 (假设您只有一个决策树模型用于所有啤酒)
        model_file = os.path.join(actual_model_dir, "decision_tree_model.joblib")
        if os.path.exists(model_file):
            try:
                shared_model = joblib.load(model_file)
                # 为所有啤酒类型使用同一个模型
                for beer_col_name in self.beer_target_col_to_model_key.keys():
                    self.models[beer_col_name] = shared_model
                logging.info(f"已加载共享模型: {model_file}")
            except Exception as e:
                logging.error(f"加载模型 {model_file} 失败: {e}")
        else:
            logging.warning(f"模型文件未找到: {model_file}")

        # 加载天气 LabelEncoder
        encoder_file = os.path.join(actual_model_dir, "weather_label_encoder.joblib")
        if os.path.exists(encoder_file):
            try:
                self.weather_label_encoder = joblib.load(encoder_file)
                logging.info(f"已加载 LabelEncoder: {encoder_file}")
            except Exception as e:
                logging.error(f"加载 LabelEncoder {encoder_file} 失败: {e}")
        else:
            logging.warning(f"LabelEncoder 文件未找到: {encoder_file}")

    def _get_future_weather_data_and_prepare_features(self, date_str):
        logging.info(f"正在为日期 {date_str} 获取天气数据...")
        latitude = 35.6895
        longitude = 139.6917
        
        open_meteo_params = "temperature_2m_mean,precipitation_sum,windspeed_10m_mean,relative_humidity_2m_mean"
        api_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={latitude}&longitude={longitude}"
            f"&daily={open_meteo_params}"
            f"&timezone=Asia%2FTokyo"
            f"&start_date={date_str}&end_date={date_str}"
        )
        
        raw_weather_features = {}
        try:
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            data = response.json()["daily"]

            raw_weather_features["平均気温(℃)"] = data.get("temperature_2m_mean", [20.0])[0]
            raw_weather_features["降水量の合計(mm)"] = data.get("precipitation_sum", [0.0])[0]
            raw_weather_features["平均風速(m/s)"] = data.get("windspeed_10m_mean", [3.0])[0]
            raw_weather_features["平均湿度(％)"] = data.get("relative_humidity_2m_mean", [60.0])[0]
            
            # 计算曜日番号（星期几）：月曜日=0, 火曜日=1, ..., 日曜日=6
            from datetime import datetime
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            raw_weather_features["曜日番号"] = date_obj.weekday()  # Monday=0, Sunday=6

            logging.info(f"获取并处理的天气特征: {raw_weather_features}")

        except requests.exceptions.RequestException as e:
            logging.error(f"获取天气数据失败: {e}。将使用默认天气特征。")
            # 如果API失败，使用默认值
            from datetime import datetime
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            raw_weather_features = {
                "平均気温(℃)": 20.0, "降水量の合計(mm)": 0.0, "平均風速(m/s)": 3.0,
                "平均湿度(％)": 60.0, "曜日番号": date_obj.weekday()
            }
        
        final_feature_values = []
        for col_name in self.feature_cols_from_colab:
            value = raw_weather_features.get(col_name)
            if value is None:
                logging.error(f"特征 '{col_name}' 缺失，使用 0。")
                final_feature_values.append(0)
            else:
                final_feature_values.append(value)
        
        return pd.DataFrame([final_feature_values], columns=self.feature_cols_from_colab)

    def predict_sales_for_date(self, date_str):
        if not self.models:
            logging.error("模型未加载。无法进行预测。")
            return [{"error": "模型服务未正确初始化。"}]

        features_df = self._get_future_weather_data_and_prepare_features(date_str)
        if features_df.empty:
            logging.error("无法为预测准备特征。")
            return [{"error": "无法准备预测特征。"}]
            
        all_predictions = []
        beer_id_counter = 1
        
        for beer_col_name_target in self.beer_names_for_output_ordered:
            model_to_use = self.models.get(beer_col_name_target)
            
            predicted_quantity = 10  # 默认值
            error_message = None
            comment = None

            if model_to_use:
                try:
                    prediction_result = model_to_use.predict(features_df)
                    # 处理可能的多维输出
                    if hasattr(prediction_result, 'flatten'):
                        predicted_quantity_float = float(prediction_result.flatten()[0])
                    else:
                        predicted_quantity_float = float(prediction_result[0])
                    predicted_quantity = max(0, int(round(predicted_quantity_float)))
                except Exception as e:
                    logging.error(f"为 {beer_col_name_target} 预测时出错: {e}")
                    error_message = str(e)
                    comment = "预测时发生错误"
            else:
                logging.warning(f"{beer_col_name_target} 的模型未找到。")
                comment = "模型不可用"
            
            prediction_item = {
                "beer_id": beer_id_counter,
                "beer_name": beer_col_name_target.replace("(本)", ""),
                "predicted_quantity": predicted_quantity
            }
            if error_message:
                prediction_item["error"] = error_message
            if comment:
                prediction_item["comment"] = comment
            
            all_predictions.append(prediction_item)
            beer_id_counter += 1
            
        return all_predictions

# 全局初始化预测器实例
try:
    predictor = BeerSalesPredictorAzure(model_dir_name="models")
except Exception as e:
    logging.critical(f"初始化 BeerSalesPredictorAzure 失败: {e}", exc_info=True)
    predictor = None

@app.route(route="predict", methods=["GET"])
def predict_beer_sales(req: func.HttpRequest) -> func.HttpResponse:
    """
    实际的啤酒销售预测 API
    """
    logging.info('实际的啤酒销售预测 API 被调用')

    if predictor is None or not predictor.models:
        logging.error("预测器服务未初始化或模型未加载。")
        return func.HttpResponse(
             json.dumps({"error": "预测服务当前不可用，请稍后重试。"}),
             status_code=503,
             mimetype="application/json",
             charset="utf-8"
        )

    request_date_str = req.params.get('date')
    if not request_date_str:
        logging.warning("未提供日期参数，将使用默认日期。")
        request_date_str = datetime.now().strftime("%Y-%m-%d")

    try:
        datetime.strptime(request_date_str, "%Y-%m-%d")
    except ValueError:
        logging.error(f"日期格式无效: {request_date_str}")
        return func.HttpResponse(
             json.dumps({"error": "请提供 YYYY-MM-DD 格式的日期。"}),
             status_code=400,
             mimetype="application/json",
             charset="utf-8"
        )

    predictions_list = predictor.predict_sales_for_date(request_date_str)

    response_data = {
        "requested_date": request_date_str,
        "predictions": predictions_list,
        "comment": "实际模型预测数据"
    }

    return func.HttpResponse(
        json.dumps(response_data, ensure_ascii=False, indent=2),
        status_code=200,
        mimetype="application/json",
        charset="utf-8"
    )

@app.route(route="health", methods=["GET"])
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """ヘルスチェック"""
    ok = predictor is not None and predictor.models and len(predictor.models) > 0
    status_message = "ok" if ok else "error"
    
    models_info = {}
    label_encoder_loaded = False
    
    if predictor:
        models_info = {
            "loaded_models": list(predictor.models.keys()),
            "models_count": len(predictor.models)
        }
        label_encoder_loaded = predictor.weather_label_encoder is not None
    
    return func.HttpResponse(
        json.dumps({
            "status": status_message,
            "models_info": models_info,
            "label_encoder_loaded": label_encoder_loaded
        }),
        status_code=200 if ok else 503,
        mimetype="application/json",
        charset="utf-8"
    )
