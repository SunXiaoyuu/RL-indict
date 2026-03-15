import os 
import pdb 
import signal
import time

# Yahoo search engine
from search_engine_parser.core.engines.yahoo import Search as YahooSearch

# OLD LangChain imports (compatible with langchain==0.0.208)
from langchain.agents.react.base import DocstoreExplorer
from langchain_community.docstore.wikipedia import Wikipedia   # 修复导入路径

# old experimental Python REPL
from langchain_experimental.utilities import PythonREPL  # 修复导入路径

# 导入Qwen相关的模块
import dashscope
from dashscope import Generation

# 移除OpenAI导入，添加Qwen配置
from dotenv import load_dotenv
load_dotenv()

# 设置DashScope API密钥
dashscope_api_key = os.getenv('DASHSCOPE_API_KEY')
if not dashscope_api_key:
    print("警告: 请设置DASHSCOPE_API_KEY环境变量")
    # 可以设置一个默认值或抛出异常
    dashscope_api_key = "dummy-key"  # 仅用于测试

dashscope.api_key = dashscope_api_key

yahoo_api = YahooSearch()

# 移除OpenAI API，创建Qwen API类
class QWEN:
    def __init__(self, model_name="qwen-max"):
        self.model_name = model_name
    
    def query_with_retries(self, query, max_tokens=256, max_retries=3):
        """使用Qwen模型进行查询"""
        for attempt in range(max_retries):
            try:
                messages = [{'role': 'user', 'content': query}]
                response = Generation.call(
                    model=self.model_name,
                    messages=messages,
                    max_tokens=max_tokens,
                    result_format='message'
                )
                
                if response.status_code == 200:
                    return response.output.choices[0].message.content
                else:
                    print(f"Qwen API错误 (尝试 {attempt + 1}/{max_retries}): {response.message}")
                    time.sleep(2)  # 等待后重试
                    
            except Exception as e:
                print(f"Qwen查询异常 (尝试 {attempt + 1}/{max_retries}): {e}")
                time.sleep(2)
        
        return "抱歉，暂时无法获取回答。"

# 创建Qwen实例
qwen_api = QWEN(model_name="qwen-max")

# setup wikipedia docstore
wikipedia_api = DocstoreExplorer(Wikipedia())

refusal_seqs = ["i can't", "i cannot", 
        "i don't know", "i do not know", 
        "i am not sure", "i'm not sure",
        "sorry i", "i refuse"]

python_repl = PythonREPL()

class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    print("alarm went off")
    raise TimeoutException
    
signal.signal(signal.SIGALRM, timeout_handler)
timeout = 120  # seconds

def run_code(code):
    signal.alarm(timeout)
    try:
        result = python_repl.run(code)
        signal.alarm(0)
    except Exception as e:
        result = 'Exception: ' + str(e) 
        signal.alarm(0)
    return result 

def internet_search(query):
    search_args = (query, 1)
    try:
        results = yahoo_api.search(*search_args)
        output = {}
        for result in results:
            if 'titles' in result and result['titles']:
                output['title'] = query + ' - ' + result['titles']
            else:
                output['title'] = query 
            if 'descriptions' in result and result['descriptions']:
                output['description'] = result['descriptions']
                break 
        return output
    except Exception as e:
        print('Internet Exception:', query, '-----', e)
        return None 

def query_qwen(query):
    """使用Qwen代替OpenAI进行查询"""
    try:
        result = qwen_api.query_with_retries(query, max_tokens=256)
        return {'title': query, 'description': result}
    except Exception as e:
        print('Qwen Exception:', query, '----', e)
        return None 
    
def query_wikipedia(query):
    try:
        result = wikipedia_api.search(query)
        if 'could not find' in result.lower():
            print('No result by Wikipedia:', query, '-----', result)
            return None
        return {'title': query, 'description': result}
    except Exception as e:
        print('Wikipedia Exception:', query, '-----', e)
        return None 
    
def query_all_tools(query, combined_query):
    tool_outputs = []
    sources = ['qwen', 'internet', 'wikipedia']  # 将chatgpt改为qwen
    
    for source in sources:
        if source == 'qwen':  # 修改为qwen
            result = query_qwen(combined_query)  # 使用新的Qwen函数
        elif source == 'internet':
            result = internet_search(combined_query)
        elif source == 'wikipedia' and query is not None and len(query)>0: 
            result = query_wikipedia(query)
        if not invalid_response(result): 
            result['source'] = source 
            tool_outputs.append(result) 
   
    if len(tool_outputs)==0:
        print("No found result in all search:", combined_query)
    
    return tool_outputs 
    
def invalid_response(response):
    if response is None:
        return True
    if 'description' not in response:
        return True 
    description = response['description']
    if len(description.strip()) == 0:
        return True
    for seq in refusal_seqs:
        if seq in description.lower():
            return True
    return False 

def code_search(query, snippet=None):
    if snippet is not None and len(snippet.strip())>0: 
        combined_query = 'Code context:\n```{}\n```'.format(snippet) + '\nQuery: ' + query
    else:
        combined_query = 'Provide critical and useful information about the following: ' + query 
    
    outputs = query_all_tools(query, combined_query)
    
    return outputs  

def code_review(query=None, code=None):
    snippet = code 
    if query is None and snippet is None:
        return None
    
    combined_query = ''
    if snippet is not None and len(snippet.strip())>0:         
        execution_result = run_code(snippet)
        if len(execution_result.strip())==0:
            execution_result = 'the code is compiled successfully without any error.'
        combined_query += 'Code context:\n```{}\n```'.format(snippet) + \
            '\nCode output: ' + execution_result 
        if query is not None:
            combined_query += '\nQuery: ' + query    
    elif query is not None: 
        combined_query += 'Provide critical and useful information about the following: ' + query 
    
    outputs = query_all_tools(query, combined_query)
    
    return outputs