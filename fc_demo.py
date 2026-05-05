"""
+==============================================================+
|   传统 Function Calling 写法 — 用于和 MCP 对比              |
|   把同样的功能用 FC 方式实现，感受差异                        |
+==============================================================+

【这是什么？】
  用传统的 Function Calling 思路实现和 MCP Demo 一模一样的功能.
  目的：让你通过对比，直观理解 MCP 到底改变了什么.

【阅读建议】
  先打开 mcp_client.py 和 mcp_server.py，再读这个文件，
  注意看代码结构,工具定义位置,调用方式的不同.

【运行方式】
  python fc_demo.py
"""

from datetime import datetime
from typing import Any

# ============================================================
# 对比点1：工具定义硬编码在客户端
# ============================================================
# 【FC 方式】工具定义直接写在客户端代码里，是一个普通的 Python 列表.
# 每次调用 LLM API 时，都要把这个列表作为参数传过去.
#
# 【MCP 方式】工具定义在服务端，客户端通过 tools/list 动态获取.

FC_TOOLS = [
    {
        "type": "function",              # FC 用 "type": "function"
        "function": {
            "name": "calculator",
            "description": "执行数学运算",
            "parameters": {              # FC 叫 "parameters"（不是 inputSchema）
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式"
                    }
                },
                "required": ["expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询城市天气",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名"}
                },
                "required": ["city"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前时间",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
]


# ============================================================
# 对比点2：工具实现也写在客户端（或同进程中）
# ============================================================
# 【FC 方式】工具函数和 Agent 代码在同一个进程里，直接调用.
# 【MCP 方式】工具函数在独立进程（服务端）中，通过网络/管道调用.

def _calculator(expression: str) -> str:
    try:
        result = eval(expression)
        return f"{expression} = {result}"
    except Exception as e:
        return f"计算出错：{e}"


def _get_weather(city: str) -> str:
    data = {
        "北京": "晴天，25°C",
        "上海": "多云，28°C",
    }
    return data.get(city, f"暂无{city}的天气数据")


def _get_time() -> str:
    return datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')


# 工具名 -> 函数（本地直接调用）
FC_TOOL_MAP = {
    "calculator": _calculator,
    "get_weather": _get_weather,
    "get_current_time": _get_time,
}


# ============================================================
# 对比点3：LLM 调用模拟（传统 FC 流程）
# ============================================================
# 在真实的 FC 系统中，把 FC_TOOLS 和用户输入一起发给 LLM API
# （如 OpenAI 的 chat/completions），LLM 返回一个 JSON：
#   {"name": "calculator", "arguments": {"expression": "2+3"}}
# 然后你在代码里根据返回值执行对应的函数.
#
# 本 demo 用关键词匹配模拟 LLM 的决策过程.

class FcAgent:
    """
    传统 Function Calling 方式的 Agent.

    【架构差异】
    FC：工具定义 + 工具实现 + Agent 决策 -> 全在一个进程里
    MCP：工具定义 + 工具实现 -> 服务端进程 | Agent -> 客户端进程
    """

    def __init__(self):
        # 工具定义是 Agent 的"内置知识"
        self.tools = FC_TOOLS

    def run(self, user_input: str):
        """
        模拟一次完整的 FC 调用流程.
        """
        # --- Step 1：决策（模拟 LLM 返回 tool_call）---
        tool_call = self._simulate_llm_decision(user_input)
        if tool_call is None:
            print("  [?] 不理解你的需求")
            return

        tool_name = tool_call["name"]
        arguments = tool_call["arguments"]
        print(f"  [决策] LLM决定调用 -> {tool_name}")
        print(f"  [参数] LLM提取参数 -> {arguments}")

        # --- Step 2：执行工具（本地直接调函数）---
        # 【关键差异】FC 是本地函数调用，无网络开销
        # MCP 是跨进程调用（通过 JSON-RPC）
        func = FC_TOOL_MAP.get(tool_name)
        if func:
            result = func(**arguments)
            print(f"  [信息] 结果：{result}")
        else:
            print(f"  [X] 未知工具：{tool_name}")

    def _simulate_llm_decision(self, user_input: str) -> dict | None:
        """
        模拟 LLM 的 function calling 返回.

        真实 FC 流程中，LLM 返回的格式类似：
          {
            "tool_calls": [{
              "function": {
                "name": "calculator",
                "arguments": "{\"expression\": \"2+3\"}"
              }
            }]
          }
        """
        import re
        if any(kw in user_input for kw in ["算", "计算", "+", "-", "*", "/"]):
            m = re.search(r'[\d+\-*/.()%\s]{3,}', user_input)
            expr = m.group().strip() if m else "2+3"
            return {"name": "calculator", "arguments": {"expression": expr}}

        for city in ["北京", "上海", "广州", "深圳"]:
            if city in user_input and any(
                w in user_input for w in ["天气", "气温", "几度"]
            ):
                return {"name": "get_weather", "arguments": {"city": city}}

        if any(kw in user_input for kw in ["时间", "几点", "日期"]):
            return {"name": "get_current_time", "arguments": {}}

        return None


# ============================================================
# 对比点4：没有协议,没有握手,没有动态发现
# ============================================================
# 【FC 方式】
#   - 无握手：不需要 initialize
#   - 无发现：工具列表硬编码，每次请求完整携带
#   - 无状态：每次 LLM API 调用都是独立的
#   - 无协议：工具定义格式跟随 LLM 厂商（OpenAI/Anthropic 各不同）
#
# 【MCP 方式】
#   - 有握手：initialize 交换能力和版本
#   - 有发现：tools/list 动态获取
#   - 有状态：长连接，工具注册一次持续可用
#   - 有标准：JSON-RPC 2.0，和 LLM 厂商无关

def main():
    print("""
+==========================================================+
|   传统 Function Calling Demo（对比用）                    |
|                                                          |
|   和 MCP Demo 同样的功能，用传统 FC 方式实现               |
|   注意观察：工具定义在哪？怎么调用？有没有协议层？          |
+==========================================================+
""")

    agent = FcAgent()

    while True:
        try:
            user_input = input("\n[>] 你：").strip()
            if user_input.lower() in ("quit", "exit", "q"):
                break
            if not user_input:
                continue
            agent.run(user_input)
            print("-" * 55)
        except KeyboardInterrupt:
            break

    print("再见！")


if __name__ == "__main__":
    main()
