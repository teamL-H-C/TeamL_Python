#!/usr/bin/env python3
"""
Azure Function 冷启动性能测试脚本 (专业版)
专门测试冷启动、热启动性能以及Azure Storage读取效果
测试步骤：
1. 冷启动基准测试（Hello World）- 测试纯冷启动时间
2. 业务逻辑调用测试 - 测试实际业务性能
3. 热启动测试 - 验证实例保持效果
4. Storage读取测试 - 验证数据持久化效果
5. 健康检查 - 最后执行
"""

import requests
import time
import json
from datetime import datetime

# Azure Function 的本地或云端URL
# FUNCTION_BASE_URL = "http://localhost:7071/api"  # 本地测试
FUNCTION_BASE_URL = "https://teaml-python-predict-api.azurewebsites.net/api"  # 云端测试

def test_cold_start_performance():
    """专业的冷启动性能测试"""
    
    print("❄️  Azure Function 冷启动性能专业测试")
    print(f"🎯 测试目标: {FUNCTION_BASE_URL}")
    print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # 测试结果存储
    test_results = []
    
    # 1. 冷启动基准测试（Hello World）
    print("🧪 步骤1: 冷启动基准测试（Hello World - 最简单函数）...")
    try:
        start_time = time.time()
        response = requests.get(f"{FUNCTION_BASE_URL}/coldstart", timeout=60)
        cold_start_time = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()
            function_processing_time = data.get('processing_time_seconds', 0)
            
            print(f"✅ 冷启动基准测试成功")
            print(f"   📊 总响应时间: {cold_start_time:.3f}秒")
            print(f"   ⚙️  函数内处理时间: {function_processing_time:.4f}秒")
            print(f"   🌐 网络+冷启动开销: {cold_start_time - function_processing_time:.3f}秒")
            
            test_results.append({
                'test': '冷启动基准(Hello World)',
                'total_time': cold_start_time,
                'processing_time': function_processing_time,
                'overhead': cold_start_time - function_processing_time,
                'type': '纯冷启动'
            })
            
            # 冷启动分析
            if cold_start_time < 1.0:
                print(f"   🚀 优秀！冷启动时间 < 1秒")
            elif cold_start_time < 3.0:
                print(f"   ✅ 良好！冷启动时间 < 3秒")
            elif cold_start_time < 5.0:
                print(f"   ⚠️  一般！冷启动时间 < 5秒")
            else:
                print(f"   ❌ 较慢！冷启动时间 > 5秒")
            
        else:
            print(f"❌ 冷启动基准测试失败: {response.status_code} - {response.text[:200]}")
            return
            
    except Exception as e:
        print(f"❌ 冷启动基准测试异常: {e}")
        return

    # 2. 业务逻辑调用测试（包含模型加载等复杂逻辑）
    print(f"\n🔄 步骤2: 业务逻辑调用测试（复杂AI预测）...")
    try:
        start_time = time.time()
        response = requests.get(f"{FUNCTION_BASE_URL}/weekly", timeout=60)
        business_call_time = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()
            perf_metrics = data.get('performance_metrics', {})
            from_storage = perf_metrics.get('from_storage', False)
            processing_time = perf_metrics.get('processing_time_seconds', 0)
            
            test_results.append({
                'test': '业务逻辑调用',
                'total_time': business_call_time,
                'processing_time': processing_time,
                'from_storage': from_storage,
                'type': 'Azure Storage读取' if from_storage else '完整AI计算'
            })
            
            print(f"✅ 业务逻辑调用成功")
            print(f"   📊 总响应时间: {business_call_time:.3f}秒")
            print(f"   💾 数据来源: {'Azure Storage' if from_storage else '实时AI计算'}")
            print(f"   ⚙️  业务处理时间: {processing_time:.3f}秒")
            
            # 与冷启动基准比较
            if len(test_results) >= 2:
                business_overhead = business_call_time - processing_time
                cold_start_overhead = test_results[0]['overhead']
                print(f"   🌐 业务调用网络开销: {business_overhead:.3f}秒")
                print(f"   📈 vs 纯冷启动开销: {cold_start_overhead:.3f}秒")
                additional_overhead = business_overhead - cold_start_overhead
                if additional_overhead > 0:
                    print(f"   ➕ 额外业务开销: {additional_overhead:.3f}秒")
                else:
                    print(f"   🎉 业务调用反而更快（可能函数实例已预热）")
                
        else:
            print(f"❌ 业务逻辑调用失败: {response.status_code} - {response.text[:200]}")
            return
            
    except Exception as e:
        print(f"❌ 业务逻辑调用异常: {e}")
        return

    # 3. 热启动测试（间隔2秒）
    print(f"\n⏱️  等待2秒后进行热启动测试...")
    time.sleep(2)
    
    print(f"🔥 步骤3: 热启动测试（验证实例保持）...")
    try:
        start_time = time.time()
        response = requests.get(f"{FUNCTION_BASE_URL}/weekly", timeout=30)
        warm_call_time = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()
            perf_metrics = data.get('performance_metrics', {})
            from_storage = perf_metrics.get('from_storage', False)
            processing_time = perf_metrics.get('processing_time_seconds', 0)
            
            test_results.append({
                'test': '热启动调用',
                'total_time': warm_call_time,
                'processing_time': processing_time,
                'from_storage': from_storage,
                'type': 'Azure Storage读取' if from_storage else '重新计算'
            })
            
            print(f"✅ 热启动调用成功")
            print(f"   📊 总响应时间: {warm_call_time:.3f}秒")
            print(f"   💾 数据来源: {'Azure Storage' if from_storage else '实时计算'}")
            print(f"   ⚙️  处理时间: {processing_time:.3f}秒")
            
            # 热启动效果分析
            if len(test_results) >= 3:
                first_business_time = test_results[1]['total_time']
                improvement = ((first_business_time - warm_call_time) / first_business_time) * 100
                print(f"   📈 vs 第一次业务调用性能提升: {improvement:.1f}%")
                print(f"   ⚡ 时间节省: {first_business_time - warm_call_time:.3f}秒")
            
        else:
            print(f"❌ 热启动测试失败: {response.status_code}")
            
    except Exception as e:
        print(f"❌ 热启动测试异常: {e}")

    # 4. 连续调用测试（验证稳定性）
    print(f"\n⚡ 步骤4: 连续调用稳定性测试（3次，间隔1秒）...")
    for i in range(3):
        try:
            start_time = time.time()
            response = requests.get(f"{FUNCTION_BASE_URL}/weekly", timeout=30)
            call_time = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                perf_metrics = data.get('performance_metrics', {})
                from_storage = perf_metrics.get('from_storage', False)
                processing_time = perf_metrics.get('processing_time_seconds', 0)
                
                test_results.append({
                    'test': f'连续调用{i+1}',
                    'total_time': call_time,
                    'processing_time': processing_time,
                    'from_storage': from_storage,
                    'type': 'Storage读取' if from_storage else '重新计算'
                })
                
                print(f"   第{i+1}次: {call_time:.3f}秒 ({'Storage' if from_storage else '计算'}) - 处理: {processing_time:.3f}秒")
                
            time.sleep(1)  # 间隔1秒
            
        except Exception as e:
            print(f"   第{i+1}次调用异常: {e}")

    # 5. 健康检查（最后执行）
    print(f"\n🔍 步骤5: 健康检查（确认系统状态）...")
    try:
        start_time = time.time()
        response = requests.get(f"{FUNCTION_BASE_URL}/health", timeout=30)
        health_time = time.time() - start_time
        
        if response.status_code == 200:
            health_data = response.json()
            models_info = health_data.get('models_info', {})
            print(f"✅ 健康检查通过 ({health_time:.3f}秒)")
            print(f"   🗄️  存储连接: {models_info.get('storage_connection', 'Unknown')}")
            print(f"   📋 Table Storage: {models_info.get('table_storage_enabled', False)}")
            print(f"   🤖 模型状态: {models_info.get('unified_model_loaded', False)}")
            print(f"   📊 特征数量: {models_info.get('features_count', 0)}")
        else:
            print(f"❌ 健康检查失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 健康检查异常: {e}")

    # 6. 综合性能分析
    print(f"\n📊 步骤6: 综合性能分析")
    print("=" * 70)
    
    if test_results:
        # 基本统计
        total_tests = len(test_results)
        storage_hits = len([r for r in test_results if r.get('from_storage', False)])
        compute_calls = total_tests - storage_hits
        
        print(f"📈 测试统计:")
        print(f"   总测试次数: {total_tests}")
        print(f"   Storage命中: {storage_hits}次")
        print(f"   重新计算: {compute_calls}次")
        if total_tests > 0:
            print(f"   Storage命中率: {storage_hits/total_tests*100:.1f}%")
        
        # 性能分类统计
        cold_start_tests = [r for r in test_results if '冷启动' in r['test']]
        business_tests = [r for r in test_results if '业务' in r['test'] or '热启动' in r['test'] or '连续' in r['test']]
        storage_tests = [r for r in test_results if r.get('from_storage', False)]
        compute_tests = [r for r in test_results if not r.get('from_storage', False) and '冷启动' not in r['test']]
        
        if cold_start_tests:
            avg_cold_start = sum(r['total_time'] for r in cold_start_tests) / len(cold_start_tests)
            print(f"\n❄️  冷启动性能:")
            print(f"   平均时间: {avg_cold_start:.3f}秒")
            
        if storage_tests:
            avg_storage_time = sum(r['total_time'] for r in storage_tests) / len(storage_tests)
            avg_storage_processing = sum(r['processing_time'] for r in storage_tests) / len(storage_tests)
            print(f"\n💾 Storage读取性能:")
            print(f"   平均总时间: {avg_storage_time:.3f}秒")
            print(f"   平均处理时间: {avg_storage_processing:.3f}秒")
            
        if compute_tests:
            avg_compute_time = sum(r['total_time'] for r in compute_tests) / len(compute_tests)
            avg_compute_processing = sum(r['processing_time'] for r in compute_tests) / len(compute_tests)
            print(f"\n🔄 AI计算性能:")
            print(f"   平均总时间: {avg_compute_time:.3f}秒")
            print(f"   平均处理时间: {avg_compute_processing:.3f}秒")
            
            if storage_tests:
                improvement = ((avg_compute_time - avg_storage_time) / avg_compute_time) * 100
                print(f"\n🚀 Storage优化效果:")
                print(f"   性能提升: {improvement:.1f}%")
                print(f"   时间节省: {avg_compute_time - avg_storage_time:.3f}秒")
        
        # 详细测试记录
        print(f"\n📋 详细测试记录:")
        print("   测试类型                总时间   处理时间  数据来源")
        print("   " + "-" * 50)
        for r in test_results:
            test_name = r['test'][:20].ljust(20)
            total_time = f"{r['total_time']:.3f}s".rjust(7)
            processing_time = f"{r.get('processing_time', 0):.3f}s".rjust(8)
            data_source = r['type']
            print(f"   {test_name} {total_time} {processing_time}  {data_source}")
    
    # 性能评估和建议
    print(f"\n💡 性能评估和建议:")
    if test_results:
        first_result = test_results[0]
        cold_start_time = first_result['total_time']
        
        if cold_start_time < 1.0:
            print("   🎉 冷启动性能优秀！< 1秒")
        elif cold_start_time < 3.0:
            print("   ✅ 冷启动性能良好！< 3秒")
        elif cold_start_time < 5.0:
            print("   ⚠️  冷启动性能一般，< 5秒")
        else:
            print("   ❌ 冷启动性能需要优化，> 5秒")
            
        if any(r.get('from_storage', False) for r in test_results):
            print("   ✅ Azure Storage集成正常工作")
            print("   ✅ 数据持久化有效提升性能")
        else:
            print("   ⚠️  未检测到Storage读取，检查配置")
            
        print("   📝 优化建议:")
        print("      - 使用Premium Plan减少冷启动")
        print("      - 配置预热实例保持性能稳定")
        print("      - 监控Storage命中率优化缓存策略")

def print_test_header():
    """打印测试开始的信息"""
    print("🎯 Azure Function 冷启动专业性能测试")
    print("🔬 测试内容: 冷启动基准、业务逻辑、热启动、Storage效果")
    print("📊 测试目标: 量化各阶段性能，识别优化点")
    print()

if __name__ == "__main__":
    print_test_header()
    test_cold_start_performance()
