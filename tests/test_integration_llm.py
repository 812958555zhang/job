"""
集成验证：真实API调用测试
验证 VolcengineLLMClient 与火山引擎 API 的实际连通性
"""
import sys
import os
import io

# 确保项目根目录在Python路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 设置控制台输出编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from core.llm_client import VolcengineLLMClient, _mask_api_key

print("=" * 60)
print("集成验证：真实API调用测试")
print("=" * 60)

# 测试1: 初始化客户端
print("\n[1] 初始化客户端...")
client = VolcengineLLMClient()
print(f"    默认模型: {client.default_model}")
print(f"    Base URL: {client.base_url}")
print(f"    API Key (脱敏): {_mask_api_key(client.api_key)}")

# 测试2: 基础chat调用
print("\n[2] 执行 chat() 调用...")
result = client.chat(
    message="你好，请用一句话介绍你自己",
    system_prompt="你是一个友好的AI助手，回答简洁",
    temperature=0.7,
    max_tokens=100,
)
print(f"    模型: {result['model']}")
print(f"    回复内容: {result['content'][:150]}")
print(f"    Token用量: {result['usage']}")
print(f"    结束原因: {result['finish_reason']}")

# 测试3: simple_chat简化调用
print("\n[3] 执行 simple_chat() 调用...")
simple_reply = client.simple_chat("1+1等于几？只回答数字")
print(f"    回复: {simple_reply.strip()}")

# 测试4: chat_json结构化输出
print("\n[4] 执行 chat_json() 调用...")
json_result = client.chat_json(
    message="姓名张三，年龄25岁，城市北京，技能Python和Django",
    system_prompt="提取用户信息并以JSON格式返回，包含name/age/city/skills字段"
)
content = json_result["content"]
print(f"    类型: {type(content).__name__}")
print(f"    内容: {content}")

# 测试5: 流式输出
print("\n[5] 执行 chat_stream() 流式输出...")
chunks = []
for chunk in client.chat_stream(message="用15个字以内介绍Python语言", max_tokens=50):
    print(chunk, end="", flush=True)
    chunks.append(chunk)
print(f"\n    共收到 {len(chunks)} 个文本块")

client.close()
print("\n" + "=" * 60)
print("[SUCCESS] 所有集成验证通过！VolcengineLLMClient 工作正常")
print("=" * 60)
