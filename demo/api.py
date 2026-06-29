import requests
import json

# 将这里替换为你刚刚创建的 API Key
API_KEY = "sk-44f497b3da974d6ea9aae706f9cb9b93"

url = "https://api.deepseek.com/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}"
}
data = {
    "model": "deepseek-chat",
    "messages": [{"role": "user", "content": "你好，这是一条API连通性测试消息。"}]
}

response = requests.post(url, headers=headers, data=json.dumps(data))

if response.status_code == 200:
    print("✅ API Key 验证成功！")
    print("模型回复:", response.json()["choices"][0]["message"]["content"])
else:
    print("❌ 验证失败。状态码:", response.status_code)
    print("错误详情:", response.text)
