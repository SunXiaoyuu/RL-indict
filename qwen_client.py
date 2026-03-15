from openai import OpenAI
import os

class QwenClient:
    def __init__(self, model_name='qwen2.5-14b-instruct'):
        self.model = model_name
        # 使用OpenAI兼容的客户端
        self.client = OpenAI(
            api_key=os.getenv("QWEN_API_KEY", "你的API密钥"),
            base_url=os.getenv("QWEN_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        )
    
    def generate(self, messages, temperature=0.7, max_tokens=2000, **kwargs):
        """兼容OpenAI的聊天完成接口"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            
            return {
                'choices': [{
                    'message': {
                        'content': response.choices[0].message.content
                    }
                }]
            }
            
        except Exception as e:
            print(f"Qwen API调用错误: {e}")
            return None

# 为了保持兼容性，也可以创建一个与OPENAI类相同的接口
class QWEN:
    def __init__(self, model_name='qwen2.5-14b-instruct'):
        self.client = QwenClient(model_name)
        self.model_name = model_name
    
    def __call__(self, *args, **kwargs):
        # 保持与原有OPENAI类相同的调用方式
        return self.client.generate(*args, **kwargs)