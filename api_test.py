#!/usr/bin/env python3
import os
import dashscope
from dashscope import Generation

def test_api_key(api_key):
    """测试API密钥是否有效"""
    print(f"测试API密钥: {api_key[:10]}...{api_key[-6:]}")
    
    # 设置API密钥
    dashscope.api_key = api_key
    
    try:
        # 使用免费模型进行测试
        response = Generation.call(
            model="qwen-turbo",  # 免费模型
            messages=[{"role": "user", "content": "请回复'测试成功'四个字"}],
            max_tokens=10
        )
        
        print(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ API密钥有效！")
            print(f"响应内容: {response.output.choices[0].message.content}")
            return True
        else:
            print(f"❌ API错误: {response.message}")
            print(f"错误码: {response.code}")
            return False
            
    except Exception as e:
        print(f"❌ 异常: {e}")
        return False

def test_different_models(api_key):
    """测试不同模型"""
    models_to_test = [
        "qwen-turbo",      # 免费
        "qwen-plus",       # 付费
        "qwen-max",        # 付费
        "qwen2.5-14b-instruct"  # 你使用的模型
    ]
    
    dashscope.api_key = api_key
    
    for model in models_to_test:
        print(f"\n测试模型: {model}")
        try:
            response = Generation.call(
                model=model,
                messages=[{"role": "user", "content": "hello"}],
                max_tokens=5
            )
            
            if response.status_code == 200:
                print(f"  ✅ {model} 可用")
            elif response.status_code == 400:
                print(f"  ⚠️ {model} 模型不存在或参数错误")
            elif response.status_code == 401:
                print(f"  ❌ {model} 认证失败")
            elif response.status_code == 429:
                print(f"  ⚠️ {model} 频率限制")
            else:
                print(f"  ❌ {model} 错误: {response.message}")
                
        except Exception as e:
            print(f"  ❌ {model} 异常: {e}")

if __name__ == "__main__":
    # 测试你的密钥
    your_api_key = "sk-e0684cacf12246528358ae32ee4fc135"
    
    print("=" * 50)
    print("Qwen API密钥验证")
    print("=" * 50)
    
    # 测试1: 原始密钥
    test_api_key(your_api_key)
    
    # 测试2: 去掉sk-前缀
    if your_api_key.startswith('sk-'):
        test_api_key(your_api_key[3:])
    
    # 测试3: 测试不同模型
    print("\n" + "=" * 50)
    print("测试不同模型")
    print("=" * 50)
    test_different_models(your_api_key)
    
    # 测试4: 检查环境变量
    print("\n" + "=" * 50)
    print("检查环境变量")
    print("=" * 50)
    env_key = os.getenv('DASHSCOPE_API_KEY')
    if env_key:
        print(f"环境变量DASHSCOPE_API_KEY: {env_key[:10]}...")
        test_api_key(env_key)
    else:
        print("❌ 未设置DASHSCOPE_API_KEY环境变量")