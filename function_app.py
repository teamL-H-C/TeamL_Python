import azure.functions as func
import logging
import json
import os
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from functools import lru_cache

# 尝试导入必要的库
try:
    import joblib
except ImportError:
    logging.critical("joblib 或 scikit-learn 未安装。请将其添加到 requirements.txt。")

# Azure Functions v2 プログラミングモデルを使用
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# --- 分类函数（从 notebook 移植） ---
def classify_rainfall(x):
    """降水量分类函数"""
    if x == 0:
        return 0  # 无雨
    elif x <= 10:
        return 1  # 小雨
    else:
        return 2  # 大雨

def classify_wind(x):
    """风速分类函数"""
    if x <= 3:
        return 0  # 轻风
    elif x <= 10:
        return 1  # 中风
    else:
        return 2  # 强风

# --- 改进的啤酒销售预测器类（使用统一RandomForest模型） ---
class BeerSalesPredictorAzure:
    def __init__(self, model_dir_name="models"):
        self.unified_model = None
        self.improved_features = None
        self.beer_sales_columns = None
        self.weather_label_encoder = None
        # 缓存系统 - 天气缓存和周预测缓存
        self._weather_cache = {}
        self._weekly_cache = {}  # 新增：周预测结果缓存
        self._cache_max_size = 100
        
        self._load_models_and_features(model_dir_name)

    def _load_models_and_features(self, model_dir_name):
        script_dir = os.path.dirname(__file__)
        actual_model_dir = os.path.join(script_dir, model_dir_name)
        logging.info(f"尝试从以下目录加载模型: {actual_model_dir}")

        if not os.path.isdir(actual_model_dir):
            logging.error(f"模型目录未找到: {actual_model_dir}")
            return

        # 加载统一的RandomForest模型
        model_file = os.path.join(actual_model_dir, "unified_rf_model.joblib")
        if os.path.exists(model_file):
            try:
                self.unified_model = joblib.load(model_file)
                logging.info(f"已加载统一RandomForest模型: {model_file}")
            except Exception as e:
                logging.error(f"加载统一模型 {model_file} 失败: {e}")
        else:
            logging.warning(f"统一模型文件未找到: {model_file}")

        # 加载特征列表
        features_file = os.path.join(actual_model_dir, "improved_features.joblib")
        if os.path.exists(features_file):
            try:
                self.improved_features = joblib.load(features_file)
                logging.info(f"已加载特征列表: {features_file}")
            except Exception as e:
                logging.error(f"加载特征列表失败: {e}")
        else:
            logging.warning(f"特征列表文件未找到: {features_file}")

        # 加载啤酒列名
        beer_cols_file = os.path.join(actual_model_dir, "beer_sales_columns.joblib")
        if os.path.exists(beer_cols_file):
            try:
                self.beer_sales_columns = joblib.load(beer_cols_file)
                logging.info(f"已加载啤酒列名: {beer_cols_file}")
            except Exception as e:
                logging.error(f"加载啤酒列名失败: {e}")
        else:
            logging.warning(f"啤酒列名文件未找到: {beer_cols_file}")

        # 加载天气 LabelEncoder（保持向后兼容）
        encoder_file = os.path.join(actual_model_dir, "weather_label_encoder.joblib")
        if os.path.exists(encoder_file):
            try:
                self.weather_label_encoder = joblib.load(encoder_file)
                logging.info(f"已加载 LabelEncoder: {encoder_file}")
            except Exception as e:
                logging.error(f"加载 LabelEncoder 失败: {e}")

    def _get_cached_weather_data(self, date_str):
        """从缓存中获取天气数据"""
        return self._weather_cache.get(date_str)
    
    def _cache_weather_data(self, date_str, weather_df):
        """缓存天气数据"""
        if len(self._weather_cache) >= self._cache_max_size:
            oldest_key = next(iter(self._weather_cache))
            del self._weather_cache[oldest_key]
        self._weather_cache[date_str] = weather_df

    def _get_cached_weekly_data(self, start_date_str):
        """从缓存中获取周预测数据"""
        logging.info(f"查找缓存数据，start_date: {start_date_str}")
        logging.info(f"当前缓存大小: {len(self._weekly_cache)}")
        logging.info(f"缓存键列表: {list(self._weekly_cache.keys())}")
        result = self._weekly_cache.get(start_date_str)
        logging.info(f"缓存查找结果: {'找到' if result is not None else '未找到'}")
        return result
    
    def _cache_weekly_data(self, start_date_str, weekly_result):
        """缓存周预测数据"""
        logging.info(f"正在缓存周预测数据，start_date: {start_date_str}")
        if len(self._weekly_cache) >= self._cache_max_size:
            oldest_key = next(iter(self._weekly_cache))
            del self._weekly_cache[oldest_key]
            logging.info(f"删除最旧的缓存项: {oldest_key}")
        self._weekly_cache[start_date_str] = weekly_result
        logging.info(f"缓存成功，当前缓存大小: {len(self._weekly_cache)}")
        logging.info(f"缓存键列表: {list(self._weekly_cache.keys())}")

    def _preprocess_weather_data(self, df_weather):
        """
        对天气数据进行特徴量エンジニアリング（从 notebook 移植）
        """
        df_weather = df_weather.copy()

        # 确保必要的时间信息
        if '日付' in df_weather.columns:
            df_weather['year'] = df_weather['日付'].dt.year
            df_weather['month'] = df_weather['日付'].dt.month
            df_weather['day'] = df_weather['日付'].dt.day
            df_weather['weekday'] = df_weather['日付'].dt.weekday
            df_weather['曜日番号'] = df_weather['weekday']

        # 特徴量作成
        df_weather['温度差'] = df_weather['最高気温(℃)'] - df_weather['最低気温(℃)']
        df_weather['温度変化率'] = df_weather['温度差'] / (df_weather['平均気温(℃)'] + 1e-6)
        df_weather['快適度指数'] = (
            (df_weather['平均気温(℃)'] - 20).abs() * -1 +
            (df_weather['平均湿度(％)'] - 60).abs() * -0.5 +
            df_weather['降水量の合計(mm)'] * -2
        )
        df_weather['季節'] = df_weather['month'].map({
            12: 0, 1: 0, 2: 0,  # 冬
            3: 1, 4: 1, 5: 1,   # 春
            6: 2, 7: 2, 8: 2,   # 夏
            9: 3, 10: 3, 11: 3  # 秋
        })
        df_weather['週末フラグ'] = (df_weather['weekday'] >= 5).astype(int)
        df_weather['良天気'] = 0  # APIには天気概況がないので一律0

        # 降水・风速分类
        df_weather['風速分類'] = df_weather['最大風速(m/s)'].apply(classify_wind)
        df_weather['降水量分類'] = df_weather['降水量の合計(mm)'].apply(classify_rainfall)

        # ダミー変数化
        df_weather = pd.get_dummies(df_weather, columns=["降水量分類", "風速分類"], 
                                  prefix=["降水量", "風速"], dtype=int)

        # 曜日のダミー変数
        for i in range(7):
            df_weather[f'曜日_{i}'] = (df_weather['曜日番号'] == i).astype(int)

        # 天気概況のエンコード（API には天気概況がないので 0 で固定）
        df_weather['天気概況_encoded'] = 0

        # 欠損補完（学習用特徴量と合わせる）
        if self.improved_features:
            for col in self.improved_features:
                if col not in df_weather.columns:
                    df_weather[col] = 0

        return df_weather

    def _get_future_weather_data_and_prepare_features(self, date_str):
        logging.info(f"正在为日期 {date_str} 获取天气数据...")
        
        # 检查缓存
        cached_weather = self._get_cached_weather_data(date_str)
        if cached_weather is not None:
            logging.info(f"使用缓存的天气数据")
            return cached_weather
            
        latitude = 35.6895
        longitude = 139.6917
        
        # 改进的API参数（从 notebook 移植）
        open_meteo_params = ("temperature_2m_max,temperature_2m_mean,temperature_2m_min,"
                           "precipitation_sum,wind_speed_10m_max,relative_humidity_2m_mean,"
                           "shortwave_radiation_sum,pressure_msl_mean")
        
        api_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={latitude}&longitude={longitude}"
            f"&daily={open_meteo_params}"
            f"&timezone=Asia%2FTokyo"
            f"&start_date={date_str}&end_date={date_str}"
        )
        
        try:
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            data = response.json()["daily"]

            # 创建天气DataFrame（与 notebook 一致）
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            df_weather = pd.DataFrame({
                "日付": [date_obj],
                "最高気温(℃)": data.get("temperature_2m_max", [20.0]),
                "平均気温(℃)": data.get("temperature_2m_mean", [20.0]),
                "最低気温(℃)": data.get("temperature_2m_min", [15.0]),
                "降水量の合計(mm)": data.get("precipitation_sum", [0.0]),
                "最大風速(m/s)": [v / 3.6 for v in data.get("wind_speed_10m_max", [10.8])],  # km/h → m/s
                "平均湿度(％)": data.get("relative_humidity_2m_mean", [60.0]),
                "合計全天日射量(MJ/㎡)": data.get("shortwave_radiation_sum", [15.0]),
                "平均現地気圧(hPa)": data.get("pressure_msl_mean", [1013.25])
            })

            # 「平均風速(m/s)」を「最大風速(m/s)」で代用
            df_weather["平均風速(m/s)"] = df_weather["最大風速(m/s)"]
            df_weather["曜日番号"] = date_obj.weekday()

            # 应用特征工程
            processed_weather = self._preprocess_weather_data(df_weather)
            
            # 缓存结果
            self._cache_weather_data(date_str, processed_weather)
            
            logging.info(f"成功获取并处理天气数据")
            return processed_weather

        except requests.exceptions.RequestException as e:
            logging.warning(f"获取天气数据失败: {e}。将使用默认天气特征。")
            
            # 使用默认值创建DataFrame
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            df_weather = pd.DataFrame({
                "日付": [date_obj],
                "最高気温(℃)": [25.0], "平均気温(℃)": [20.0], "最低気温(℃)": [15.0],
                "降水量の合計(mm)": [0.0], "最大風速(m/s)": [3.0], "平均風速(m/s)": [3.0],
                "平均湿度(％)": [60.0], "合計全天日射量(MJ/㎡)": [15.0], "平均現地気圧(hPa)": [1013.25],
                "曜日番号": [date_obj.weekday()]
            })
            
            processed_weather = self._preprocess_weather_data(df_weather)
            return processed_weather

    def predict_sales_for_date(self, date_str):
        if not self.unified_model or not self.improved_features or not self.beer_sales_columns:
            logging.error("统一模型或相关数据未加载。无法进行预测。")
            return {"error": "模型服务未正确初始化。"}

        # 获取并处理天气数据
        weather_df = self._get_future_weather_data_and_prepare_features(date_str)
        if weather_df.empty:
            logging.error("无法为预测准备特征。")
            return {"error": "无法准备预测特征。"}
            
        try:
            # 准备预测特征（确保特征顺序正确）
            predict_X = weather_df[self.improved_features]
            
            # 使用统一模型进行预测（返回所有6种啤酒的预测值）
            predictions = self.unified_model.predict(predict_X)[0]  # 取第一行（只预测一天）
            
            # 构建预测结果字典
            beer_predictions = {}
            for i, beer_name in enumerate(self.beer_sales_columns):
                beer_predictions[beer_name] = max(0, round(float(predictions[i]), 1))
            
            return beer_predictions
            
        except Exception as e:
            logging.error(f"预测时出错: {e}")
            return {"error": f"预测时发生错误: {str(e)}"}

    def predict_weekly_shipment(self, start_date_str):
        """
        根据起始日期预测一周的出货汇总（改进版本，包含出货日期和缓存）
        """
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        except ValueError:
            return {"error": "日期格式无效"}
        
        # 检查缓存
        cached_result = self._get_cached_weekly_data(start_date_str)
        if cached_result is not None:
            logging.info(f"使用缓存的周预测数据: {start_date_str}")
            # 从缓存结果构建完整响应
            result_from_cache = {
                **cached_result,
                "from_cache": True,
                "generated_at": "来自缓存"
            }
            return result_from_cache
        
        logging.info(f"生成新的周预测数据: {start_date_str}")
        
        # 生成未来7天的预测
        daily_predictions = []
        weekdays_data = {}
        
        for i in range(7):
            current_date = start_date + timedelta(days=i)
            date_str = current_date.strftime("%Y-%m-%d")
            weekday = current_date.weekday()
            
            prediction = self.predict_sales_for_date(date_str)
            if "error" in prediction:
                continue
                
            daily_predictions.append({
                "date": date_str,
                "weekday": weekday,
                "predictions": prediction
            })
            
            # 记录每个weekday对应的日期
            weekdays_data[weekday] = current_date
        
        if not daily_predictions:
            return {"error": "无法生成预测数据"}
        
        # 按照改进的逻辑分组
        monday_group = []  # 月火水 (weekday 0,1,2)
        thursday_group = []  # 木金土 (weekday 3,4,5)
        
        for pred in daily_predictions:
            weekday = pred["weekday"]
            if weekday in [0, 1, 2]:  # 月火水
                monday_group.append(pred)
            elif weekday in [3, 4, 5]:  # 木金土
                thursday_group.append(pred)
        
        # 计算汇总
        def sum_group(group):
            total = {beer: 0 for beer in self.beer_sales_columns}
            for pred in group:
                for beer, quantity in pred["predictions"].items():
                    if beer in total:
                        total[beer] += quantity
            return total
        
        results = {}
        
        # 检查月曜用的发货日（月0、火1、水2）是否都存在
        if set([0, 1, 2]).issubset(set(weekdays_data.keys())):
            monday_sum = sum_group(monday_group)
            
            # 计算下一个周一的日期作为出货日
            today = start_date.date()
            next_monday = today + timedelta(days=(7 - today.weekday()) % 7)
            
            results["月曜用の出荷集計"] = {
                "出荷日": next_monday.strftime("%Y-%m-%d"),
                **monday_sum
            }
        
        # 检查木曜用的发货日（木3、金4、土5）是否都存在
        if set([3, 4, 5]).issubset(set(weekdays_data.keys())):
            thursday_sum = sum_group(thursday_group)
            
            # 找到木曜日的日期作为出货日
            thursday_date = weekdays_data.get(3)  # weekday 3 = 木曜日
            if thursday_date:
                results["木曜用の出荷集計"] = {
                    "出荷日": thursday_date.strftime("%Y-%m-%d"),
                    **thursday_sum
                }
        
        if not results:
            return {"error": "月曜用・木曜用いずれも発注日が不足しています。"}
        
        # 构建最终结果
        final_result = {
            "🍻 発注用ビール出荷集計": results,
            "daily_details": daily_predictions,
            "comment": "出荷日付を含む改良版集計",
            "from_cache": False,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # 缓存结果（不包含 from_cache 和 generated_at 字段）
        cache_data = {
            "🍻 発注用ビール出荷集計": results,
            "daily_details": daily_predictions,
            "comment": "出荷日付を含む改良版集計"
        }
        self._cache_weekly_data(start_date_str, cache_data)
        logging.info(f"已缓存周预测数据: {start_date_str}")
        
        return final_result

# 全局初始化预测器实例
try:
    predictor = BeerSalesPredictorAzure(model_dir_name="models")
except Exception as e:
    logging.critical(f"初始化 BeerSalesPredictorAzure 失败: {e}", exc_info=True)
    predictor = None

@app.route(route="predict", methods=["GET"])
def predict_beer_sales(req: func.HttpRequest) -> func.HttpResponse:
    """
    改进的啤酒销售预测 API（基于统一RandomForest模型）
    """
    logging.info('改进的啤酒销售预测 API 被调用')

    if predictor is None or not predictor.unified_model:
        logging.error("预测器服务未初始化或模型未加载。")
        return func.HttpResponse(
             json.dumps({"error": "预测服务当前不可用，请稍后重试。"}),
             status_code=503,
             mimetype="application/json",
             charset="utf-8"
        )

    request_date_str = req.params.get('date')
    if not request_date_str:
        logging.warning("未提供日期参数，将使用当前日期。")
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

    predictions_result = predictor.predict_sales_for_date(request_date_str)

    response_data = {
        "requested_date": request_date_str,
        "predictions": predictions_result,
        "model_info": {
            "type": "Unified RandomForest MultiOutput",
            "features_count": len(predictor.improved_features) if predictor.improved_features else 0,
            "cached_weather": request_date_str in predictor._weather_cache
        },
        "comment": "rf.ipynb ベースの統一RandomForest予測"
    }

    return func.HttpResponse(
        json.dumps(response_data, ensure_ascii=False, indent=2),
        status_code=200,
        mimetype="application/json",
        charset="utf-8"
    )

@app.route(route="weekly", methods=["GET"])
def predict_weekly_beer_shipment(req: func.HttpRequest) -> func.HttpResponse:
    """
    周単位のビール出荷予測 API（改进版本）
    """
    logging.info('週単位ビール出荷予測 API が呼び出されました')

    if predictor is None or not predictor.unified_model:
        logging.error("予測器サービスが初期化されていないか、モデルが読み込まれていません。")
        return func.HttpResponse(
             json.dumps({"error": "予測サービスは現在利用できません。しばらくしてから再試行してください。"}),
             status_code=503,
             mimetype="application/json",
             charset="utf-8"
        )

    request_date_str = req.params.get('start_date')
    if not request_date_str:
        logging.warning("開始日付パラメータが提供されていません。デフォルト日付を使用します。")
        request_date_str = datetime.now().strftime("%Y-%m-%d")

    try:
        datetime.strptime(request_date_str, "%Y-%m-%d")
    except ValueError:
        logging.error(f"無効な日付形式: {request_date_str}")
        return func.HttpResponse(
             json.dumps({"error": "YYYY-MM-DD形式の日付を提供してください。"}),
             status_code=400,
             mimetype="application/json",
             charset="utf-8"
        )

    weekly_predictions = predictor.predict_weekly_shipment(request_date_str)

    response_data = {
        "start_date": request_date_str,
        "shipment_summary": weekly_predictions,
        "comment": "統一RandomForest モデルによる週単位出荷予測"
    }

    return func.HttpResponse(
        json.dumps(response_data, ensure_ascii=False, indent=2),
        status_code=200,
        mimetype="application/json",
        charset="utf-8"
    )

@app.route(route="health", methods=["GET"])
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """改进的ヘルスチェック"""
    ok = (predictor is not None and 
          predictor.unified_model is not None and 
          predictor.improved_features is not None and 
          predictor.beer_sales_columns is not None)
    
    status_message = "ok" if ok else "error"
    
    models_info = {}
    if predictor:
        models_info = {
            "unified_model_loaded": predictor.unified_model is not None,
            "features_loaded": predictor.improved_features is not None,
            "beer_columns_loaded": predictor.beer_sales_columns is not None,
            "features_count": len(predictor.improved_features) if predictor.improved_features else 0,
            "beer_types_count": len(predictor.beer_sales_columns) if predictor.beer_sales_columns else 0,
            "weather_cache_size": len(predictor._weather_cache),
            "weekly_cache_size": len(predictor._weekly_cache)  # 新增：周缓存状态
        }
    
    return func.HttpResponse(
        json.dumps({
            "status": status_message,
            "model_type": "Unified RandomForest MultiOutput",
            "models_info": models_info
        }),
        status_code=200 if ok else 503,
        mimetype="application/json",
        charset="utf-8"
    )

# 新增：定时触发器，用于预热缓存
@app.timer_trigger(schedule="0 0 1 * * *", arg_name="myTimer", run_on_startup=True) 
def warm_up_cache_timer(myTimer: func.TimerRequest) -> None:
    """
    每天凌晨1点自动运行，预测当天的销量并缓存结果。
    run_on_startup=True 确保函数应用启动时也会运行一次。
    """
    if myTimer.past_due:
        logging.info('定时器函数执行延迟。')

    logging.info('定时缓存预热函数启动。')
    
    if predictor is None or not predictor.unified_model:
        logging.error("预测器服务未初始化，无法预热缓存。")
        return

    # 预测当天的销量以填充缓存
    # 注意：Azure Function默认使用UTC时间，如果需要特定时区，请在Azure门户设置WEBSITE_TIME_ZONE
    today_str = datetime.now().strftime("%Y-%m-%d")
    logging.info(f"正在为日期 {today_str} 预热缓存...")
    
    try:
        # 调用此方法将自动执行预测并将结果存入缓存
        predictions = predictor.predict_sales_for_date(today_str)
        if "error" in predictions:
            logging.error(f"预热缓存时发生错误: {predictions['error']}")
        else:
            logging.info(f"已成功为日期 {today_str} 预热缓存。")
    except Exception as e:
        logging.error(f"预热缓存时发生未处理的异常: {e}", exc_info=True)

    logging.info('Python 定时器触发器函数执行完毕。')
