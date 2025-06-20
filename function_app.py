import azure.functions as func
import logging
import json
import os
import time
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from functools import lru_cache
from azure.data.tables import TableServiceClient, TableEntity

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
    if x is None:
        return 0  # 默认为无雨
    elif x == 0:
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
        # Azure Table Storage 客户端
        self.table_client = None
        
        self._load_models_and_features(model_dir_name)
        self._init_table_storage()

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

    def _init_table_storage(self):
        """初始化Table Storage客户端，使用Function App默认存储账户"""
        try:
            # 优先使用自定义连接字符串
            conn_str = os.environ.get("AZURE_TABLES_CONNECTION_STRING")
            
            # 如果没有自定义连接字符串，则使用Function App默认存储
            if not conn_str:
                conn_str = os.environ.get("AzureWebJobsStorage")
                if conn_str:
                    logging.info("使用Function App默认存储账户进行Table Storage")
                else:
                    logging.warning("未找到存储连接字符串，Table Storage将被禁用")
                    return
            else:
                logging.info("使用自定义AZURE_TABLES_CONNECTION_STRING")
                
            table_name = os.environ.get("AZURE_TABLES_NAME", "BeerWeeklyPrediction")
            
            service = TableServiceClient.from_connection_string(conn_str)
            self.table_client = service.get_table_client(table_name)
            
            # 尝试创建表（如果不存在）
            try:
                self.table_client.create_table()
                logging.info(f"成功创建Table Storage表: {table_name}")
            except Exception as create_error:
                # 表已存在是正常情况
                if "already exists" in str(create_error).lower():
                    logging.info(f"Table Storage表已存在: {table_name}")
                else:
                    logging.warning(f"创建表时遇到问题: {create_error}")
                    
            # 测试连接
            try:
                # 执行一个简单的查询来验证连接
                list(self.table_client.list_entities(select=["PartitionKey"], top=1))
                logging.info("Table Storage连接测试成功")
            except Exception as test_error:
                logging.error(f"Table Storage连接测试失败: {test_error}")
                self.table_client = None
                
        except Exception as e:
            logging.error(f"Table Storage初始化失败: {e}")
            self.table_client = None

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

    def _get_weekly_weather_data(self, start_date_str, days=7):
        """
        一次性获取未来一周的天气数据（核心性能优化）
        这个方法将7次串行API调用合并为1次，显著提升性能
        """
        logging.info(f"正在为起始于 {start_date_str} 的一周批量获取天气数据...")
        
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        except ValueError:
            logging.error(f"日期格式无效: {start_date_str}")
            return None
            
        end_date = start_date + timedelta(days=days - 1)
        end_date_str = end_date.strftime("%Y-%m-%d")

        latitude = 35.6895
        longitude = 139.6917
        
        # 改进的API参数（与单日版本保持一致）
        open_meteo_params = ("temperature_2m_max,temperature_2m_mean,temperature_2m_min,"
                           "precipitation_sum,wind_speed_10m_max,relative_humidity_2m_mean,"
                           "shortwave_radiation_sum,pressure_msl_mean")
        
        api_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={latitude}&longitude={longitude}"
            f"&daily={open_meteo_params}"
            f"&timezone=Asia%2FTokyo"
            f"&start_date={start_date_str}&end_date={end_date_str}"  # 关键改动：请求日期范围
        )
        
        try:
            # 适当延长超时时间，因为请求的是一周的数据
            response = requests.get(api_url, timeout=15)
            response.raise_for_status()
            data = response.json()["daily"]

            # 创建一周的天气DataFrame
            dates = pd.to_datetime(data["time"])
            df_weather = pd.DataFrame({
                "日付": dates,
                "最高気温(℃)": data.get("temperature_2m_max", [20.0] * len(dates)),
                "平均気温(℃)": data.get("temperature_2m_mean", [20.0] * len(dates)),
                "最低気温(℃)": data.get("temperature_2m_min", [15.0] * len(dates)),
                "降水量の合計(mm)": data.get("precipitation_sum", [0.0] * len(dates)),
                "最大風速(m/s)": [v / 3.6 if v is not None else 3.0 for v in data.get("wind_speed_10m_max", [10.8] * len(dates))],  # km/h → m/s, 处理None值
                "平均湿度(％)": data.get("relative_humidity_2m_mean", [60.0] * len(dates)),
                "合計全天日射量(MJ/㎡)": data.get("shortwave_radiation_sum", [15.0] * len(dates)),
                "平均現地気圧(hPa)": data.get("pressure_msl_mean", [1013.25] * len(dates))
            })

            # 添加平均风速（使用最大风速代替）
            df_weather["平均風速(m/s)"] = df_weather["最大風速(m/s)"]
            
            # 应用特征工程处理
            processed_weather = self._preprocess_weather_data(df_weather)
            
            logging.info(f"成功批量获取并处理了 {len(dates)} 天的天气数据")
            return processed_weather

        except requests.exceptions.RequestException as e:
            logging.error(f"批量获取天气数据失败: {e}。返回None")
            return None
        except Exception as e:
            logging.error(f"处理批量天气数据时发生意外错误: {e}")
            return None

    def _get_storage_data(self, date_str):
        """从Table Storage获取数据"""
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                if not self.table_client:
                    logging.warning("Table Storage客户端未初始化")
                    return None
                    
                entity = self.table_client.get_entity(partition_key="weekly", row_key=date_str)
                result = json.loads(entity["Result"])
                
                # 检查数据时效性（可选：24小时过期）
                if "generated_at" in entity and entity["generated_at"]:
                    cache_time = datetime.strptime(entity["generated_at"], "%Y-%m-%d %H:%M:%S")
                    if (datetime.now() - cache_time).total_seconds() > 86400:  # 24小时
                        logging.info(f"Table Storage数据已过期: {date_str}")
                        return None
                
                logging.info(f"成功从Table Storage获取数据: {date_str}")
                return result
                
            except Exception as e:
                if attempt < max_retries - 1:
                    logging.warning(f"Table Storage读取失败，重试中 ({attempt + 1}/{max_retries}): {e}")
                    time.sleep(retry_delay * (2 ** attempt))  # 指数退避
                else:
                    logging.error(f"Table Storage读取最终失败: {e}")
                    return None

    def _save_storage_data(self, date_str, result):
        """保存数据到Table Storage"""
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                if not self.table_client:
                    logging.warning("Table Storage客户端未初始化，跳过保存")
                    return
                    
                entity = TableEntity()
                entity["PartitionKey"] = "weekly"
                entity["RowKey"] = date_str
                entity["Result"] = json.dumps(result, ensure_ascii=False)
                entity["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                entity["ttl"] = int((datetime.now() + timedelta(days=7)).timestamp())  # 7天TTL
                
                self.table_client.upsert_entity(entity)
                logging.info(f"成功保存到Table Storage: {date_str}")
                return
                
            except Exception as e:
                if attempt < max_retries - 1:
                    logging.warning(f"Table Storage写入失败，重试中 ({attempt + 1}/{max_retries}): {e}")
                    time.sleep(retry_delay * (2 ** attempt))
                else:
                    logging.error(f"Table Storage写入最终失败: {e}")

    def predict_weekly_shipment(self, start_date_str):
        """
        根据起始日期预测一周的出货汇总（Azure Storage版本）
        直接从 Azure Table Storage 读取或计算后保存
        """
        # 先检查 Table Storage 中是否有现成数据
        stored_result = self._get_storage_data(start_date_str)
        if stored_result:
            logging.info(f"从Table Storage获取数据: {start_date_str}")
            return {**stored_result, "from_storage": True, "generated_at": "从存储获取"}
        
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        except ValueError:
            return {"error": "日期格式无效"}
        
        logging.info(f"生成新的周预测数据: {start_date_str}")
        
        # 🚀 关键优化：一次性获取7天的天气数据，而不是循环7次
        weekly_weather_features = self._get_weekly_weather_data(start_date_str, days=7)
        if weekly_weather_features is None or weekly_weather_features.empty:
            logging.error("无法获取天气数据，周预测失败")
            return {"error": "无法获取天气数据，周预测失败。"}

        # 🚀 关键优化：对7天数据进行一次性批量预测，而不是循环调用模型
        try:
            # 确保特征顺序正确
            predict_X = weekly_weather_features[self.improved_features]
            # RandomForest.predict 可以高效处理多行输入
            all_predictions = self.unified_model.predict(predict_X)  # 形状: (7, 6) - 7天每天6种啤酒
            logging.info(f"批量模型预测完成，预测了 {len(all_predictions)} 天的数据")
        except Exception as e:
            logging.error(f"周预测的批量模型推理出错: {e}")
            return {"error": f"批量模型预测时发生错误: {str(e)}"}

        # 组织预测结果为与原始版本兼容的格式
        daily_predictions = []
        weekdays_data = {}
        
        for i, (_, row) in enumerate(weekly_weather_features.iterrows()):
            current_date = row['日付']
            date_str = current_date.strftime("%Y-%m-%d")
            weekday = current_date.weekday()
            
            # 构建该天的啤酒预测结果
            beer_predictions = {}
            for j, beer_name in enumerate(self.beer_sales_columns):
                beer_predictions[beer_name] = max(0, round(float(all_predictions[i][j]), 1))
            
            daily_predictions.append({
                "date": date_str,
                "weekday": weekday,
                "predictions": beer_predictions
            })
            
            # 记录每个weekday对应的日期
            weekdays_data[weekday] = current_date
        
        if not daily_predictions:
            return {"error": "无法生成预测数据"}
        
        # 按照改进的逻辑分组（与原版保持一致）
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
            "comment": "出荷日付を含む改良版集计",
            "from_storage": False,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # 保存到 Table Storage
        self._save_storage_data(start_date_str, final_result)
        logging.info(f"已保存周预测数据到Table Storage: {start_date_str}")
        
        return final_result

# 全局初始化预测器实例
try:
    predictor = BeerSalesPredictorAzure(model_dir_name="models")
except Exception as e:
    logging.critical(f"初始化 BeerSalesPredictorAzure 失败: {e}", exc_info=True)
    predictor = None

@app.route(route="weekly", methods=["GET"])
def predict_weekly_beer_shipment(req: func.HttpRequest) -> func.HttpResponse:
    """
    週単位のビール出荷予測 API（性能优化版本）
    核心优化：将7次串行API调用合并为1次批量调用，大幅提升响应速度
    """
    logging.info('週単位ビール出荷予測 API（优化版）が呼び出されました')

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

    # 记录处理开始时间
    start_time = datetime.now()
    weekly_predictions = predictor.predict_weekly_shipment(request_date_str)
    end_time = datetime.now()
    processing_time = (end_time - start_time).total_seconds()

    response_data = {
        "start_date": request_date_str,
        "shipment_summary": weekly_predictions,
        "performance_metrics": {
            "processing_time_seconds": round(processing_time, 2),
            "storage_type": "Azure Table Storage",
            "from_storage": weekly_predictions.get("from_storage", False)
        },
        "comment": "統一RandomForest モデルによる週単位出荷予測（Azure Storage版）"
    }

    return func.HttpResponse(
        json.dumps(response_data, ensure_ascii=False, indent=2),
        status_code=200,
        mimetype="application/json",
        charset="utf-8"
    )

@app.route(route="health", methods=["GET"])
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """增强的ヘルスチェック（包含性能优化信息）"""
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
            "table_storage_enabled": predictor.table_client is not None,
            "storage_connection": "Function App Default" if not os.environ.get("AZURE_TABLES_CONNECTION_STRING") else "Custom",
            "storage_type": "Azure Table Storage",
            "performance_optimizations": {
                "batch_api_calls": True,
                "model_batch_prediction": True,
                "azure_storage_persistence": True,
                "simplified_architecture": True
            }
        }
    
    return func.HttpResponse(
        json.dumps({
            "status": status_message,
            "model_type": "Unified RandomForest MultiOutput (性能优化版)",
            "version": "v2.0-optimized",
            "models_info": models_info,
            "optimizations_applied": [
                "7次串行API调用合并为1次批量调用",
                "批量模型预测替换循环预测",
                "增强缓存预热机制",
                "性能监控指标"
            ]
        }),
        status_code=200 if ok else 503,
        mimetype="application/json",
        charset="utf-8"
    )

@app.timer_trigger(schedule="0 0 1 * * *", arg_name="myTimer", run_on_startup=True) 
def warm_up_storage_timer(myTimer: func.TimerRequest) -> None:
    """
    定时预热触发器：每天凌晨1点自动运行，预测当天和未来一周的销量并保存到Azure Storage。
    run_on_startup=True 确保函数应用启动时也会运行一次。
    """
    if myTimer.past_due:
        logging.info('定时器函数执行延迟。')

    logging.info('Azure Storage 定时预热函数启动。')
    
    if predictor is None or not predictor.unified_model:
        logging.error("预测器服务未初始化，无法预热。")
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # 预热本周预测
    logging.info(f"正在为起始于 {today_str} 的周预测保存到Azure Storage...")
    try:
        weekly_predictions = predictor.predict_weekly_shipment(today_str)
        if "error" in weekly_predictions:
            logging.error(f"预热周预测时发生错误: {weekly_predictions['error']}")
        else:
            logging.info(f"已成功为起始于 {today_str} 的周预测保存到Azure Storage。")
    except Exception as e:
        logging.error(f"预热周预测时发生未处理的异常: {e}", exc_info=True)

    # 预热下周的预测
    next_week_str = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    logging.info(f"正在为下周起始于 {next_week_str} 的预测保存到Azure Storage...")
    try:
        next_week_predictions = predictor.predict_weekly_shipment(next_week_str)
        if "error" in next_week_predictions:
            logging.warning(f"预热下周预测时发生错误: {next_week_predictions['error']}")
        else:
            logging.info(f"已成功为下周起始于 {next_week_str} 的预测保存到Azure Storage。")
    except Exception as e:
        logging.warning(f"预热下周预测时发生异常: {e}")

    logging.info('Azure Storage 定时预热函数执行完毕。')

@app.route(route="coldstart", methods=["GET"])
def cold_start_test(req: func.HttpRequest) -> func.HttpResponse:
    """
    冷启动测试函数 - 最简单的Hello World
    用于测试纯粹的Azure Function冷启动时间，不涉及任何复杂逻辑
    """
    start_time = datetime.now()
    
    print("Hello World - Cold Start Test!")
    logging.info("冷启动测试函数被调用")
    
    end_time = datetime.now()
    processing_time = (end_time - start_time).total_seconds()
    
    response_data = {
        "message": "Hello World",
        "function": "cold_start_test",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "processing_time_seconds": round(processing_time, 4),
        "purpose": "测试Azure Function纯冷启动速度"
    }
    
    return func.HttpResponse(
        json.dumps(response_data, ensure_ascii=False, indent=2),
        status_code=200,
        mimetype="application/json",
        charset="utf-8"
    )
