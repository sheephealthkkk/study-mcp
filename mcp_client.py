"""
+==============================================================+
|           MCP 客户端 — 实现完整的 MCP 协议交互              |
|           通过子进程 stdio 与服务端通信                      |
+==============================================================+

【这是什么？】
  一个 MCP 客户端，它：
    1. 以子进程方式启动 mcp_server.py
    2. 通过 stdin/stdout 管道与服务端进行 JSON-RPC 通信
    3. 完成 MCP 协议握手（initialize）
    4. 动态发现工具（tools/list）
    5. 根据用户输入调用工具（tools/call）

【MCP 客户端的职责】
  +--------------------------------------------------+
  | 1. 管理服务端进程的生命周期（启动/关闭）           |
  | 2. 完成协议握手（initialize -> initialized）      |
  | 3. 动态获取工具列表（tools/list）                 |
  | 4. 决策：用户想干什么？该用哪个工具？              |
  | 5. 调用工具并展示结果（tools/call）               |
  +--------------------------------------------------+

【和传统 Function Calling 客户端的核心区别】
  FC 客户端：
    工具定义硬编码在代码里 -> 每次请求都传全部工具 -> 耦合在 API 中

  MCP 客户端：
    工具定义从服务端动态获取 -> 工具变更客户端无需修改 -> 完全解耦

【运行方式】
  python mcp_client.py
"""

import subprocess
import sys
import json
import re
import logging
from typing import Any

# 日志写到 stderr（和协议通道 stdout 分开）
logging.basicConfig(
    level=logging.INFO,
    format="[CLIENT] %(levelname)s %(message)s",
    stream=sys.stderr
)
log = logging.getLogger("mcp-client")


# ============================================================
# 第1步：MCP 协议消息的读写（stdio transport）
# ============================================================
# 【关键】这些读写函数和服务端的完全对称——
# 客户端写 stdin，读 stdout；服务端读 stdin，写 stdout.
# 这就是 stdio transport 的精妙之处：双向管道,完全对称.

class McpTransport:
    """
    MCP stdio 传输层.

    封装了"启动子进程 + 收发 JSON-RPC 消息"的逻辑.
    上层只需要调用 send() 和 receive()，不用关心底层细节.

    为什么用子进程而不是 HTTP？
      - 本地场景 stdio 更简单（不需要端口,防火墙配置）
      - 进程生命周期天然绑定（Agent 退出 -> 工具服务自动退出）
      - 安全性更好（不暴露网络端口）
    """

    def __init__(self, server_script: str):
        """
        启动 MCP 服务端为子进程.

        subprocess.Popen 参数解释：
          stdin=PIPE   -> 创建一个管道，我们可以往里面写数据
          stdout=PIPE  -> 创建一个管道，我们可以从里面读数据
          stderr=PIPE  -> 服务端的日志管道（本 demo 没读它）
          text=True    -> 管道数据当文本处理（自动编解码）
          bufsize=1    -> 行缓冲（每行立即发送，不等待）
        """
        self.process = subprocess.Popen(
            [sys.executable, server_script],         # python mcp_server.py
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        self._request_id = 0

    def send_request(self, method: str, params: dict = None) -> int:
        """
        发送一个 JSON-RPC Request（有 id，期待响应）.

        返回 request_id，用于匹配响应.
        """
        self._request_id += 1
        msg = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or {}
        }
        self._write(msg)
        return self._request_id

    def send_notification(self, method: str, params: dict = None):
        """
        发送一个 JSON-RPC Notification（无 id，不期待响应）.

        MCP 协议中 initialized 就是一个 notification——
        客户端初始化完成，通知服务端，服务端不做回应.
        """
        msg = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        self._write(msg)

    def receive(self) -> dict:
        """
        从服务端的 stdout 读取一行 JSON-RPC 响应.

        会一直阻塞直到收到响应.
        """
        line = self.process.stdout.readline()
        if not line:
            raise ConnectionError("服务端已关闭连接")
        return json.loads(line)

    def _write(self, msg: dict):
        """写一行 JSON 到服务端的 stdin"""
        line = json.dumps(msg, ensure_ascii=False)
        # 日志：把发出的消息打印到 stderr，方便观察协议交互过程
        log.debug(f"-> {line}")
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()

    def close(self):
        """关闭连接，终止服务端进程"""
        self.process.stdin.close()
        self.process.terminate()
        self.process.wait()


# ============================================================
# 第2步：MCP 客户端 — 协议交互层
# ============================================================

class McpClient:
    """
    MCP 客户端.

    负责完成 MCP 协议规定的初始化流程和工具交互.

    MCP 的完整生命周期：
      initialize request  (client -> server)  握手：交换能力和版本
      initialize response (server -> client)
      initialized notif   (client -> server)  确认：初始化完成
      tools/list request  (client -> server)  发现：获取可用工具
      tools/list response (server -> client)
      tools/call request  (client -> server)  使用：调用工具（可多次）
      tools/call response (server -> client)
      ... (循环调用) ...
      [进程退出]                             关闭
    """

    def __init__(self, server_script: str = "mcp_server.py"):
        self.transport = McpTransport(server_script)
        self.tools = []                          # 缓存工具列表
        self._initialized = False

    def initialize(self):
        """
        执行 MCP 协议握手.

        【这是 MCP 独有的步骤，传统 FC 没有这个概念】

        为什么需要握手？
          1. 版本协商：客户端说"我支持 1.0"，服务端确认"我也支持 1.0"
             如果版本不匹配，可以在这里就发现问题
          2. 能力交换：服务端声明"我有 tools, resources, prompts 能力"
             客户端据此决定后面可以调哪些方法
          3. 身份声明：双方互报名字和版本，方便日志追踪和问题排查

        传统 FC 没有握手——工具定义跟在每个 API 请求里，
        没有"先认识一下"的过程.
        """
        print("=" * 55)
        print("[连接] 初始化 MCP 连接...")
        print("-" * 55)

        # --- Step 1: initialize request ---
        print("  [1/3] 发送 initialize 请求...")
        req_id = self.transport.send_request("initialize", {
            "protocolVersion": "1.0",            # 我支持的协议版本
            "capabilities": {},                   # 客户端能力（本 demo 为空）
            "clientInfo": {
                "name": "mcp-demo-client",
                "version": "1.0.0"
            }
        })

        resp = self.transport.receive()
        if "error" in resp:
            raise RuntimeError(f"初始化失败：{resp['error']}")
        result = resp["result"]
        print(f"  [OK] 握手成功！服务端：{result['serverInfo']['name']} "
              f"v{result['serverInfo']['version']}")
        print(f"  [信息] 协议版本：{result['protocolVersion']}")
        print(f"  [能力] 服务端能力：{list(result['capabilities'].keys())}")

        # --- Step 2: initialized notification ---
        # initialized 是 Notification（无 id），表示"我准备好了"
        print("  [2/3] 发送 initialized 通知...")
        self.transport.send_notification("notifications/initialized")
        self._initialized = True

        # --- Step 3: tools/list ---
        # 动态发现工具——这是 MCP 和 FC 最核心的架构差异
        print("  [3/3] 请求工具列表 (tools/list)...")
        req_id = self.transport.send_request("tools/list", {})

        resp = self.transport.receive()
        if "error" in resp:
            raise RuntimeError(f"获取工具列表失败：{resp['error']}")

        self.tools = resp["result"].get("tools", [])
        print(f"  [OK] 发现 {len(self.tools)} 个可用工具：")
        for t in self.tools:
            # 显示工具名 + 必填参数
            required = t.get("inputSchema", {}).get("required", [])
            params_str = ", ".join(required) if required else "无参数"
            print(f"     - {t['name']}({params_str}) — {t['description']}")
        print("=" * 55)
        print()

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        """
        调用服务端的一个工具.

        参数:
          tool_name: 工具名
          arguments: 参数字典

        返回:
          工具执行结果的文本
        """
        req_id = self.transport.send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })

        resp = self.transport.receive()
        if "error" in resp:
            return f"[X] 工具调用失败：{resp['error']['message']}"

        # MCP 的工具返回格式：{"content": [{"type": "text", "text": "..."}]}
        content = resp["result"].get("content", [])
        if content and content[0].get("type") == "text":
            return content[0]["text"]
        return "空结果"

    def get_tools(self) -> list:
        """返回缓存的工具列表"""
        return self.tools

    def close(self):
        """关闭 MCP 连接"""
        self.transport.close()
        print("[连接] MCP 连接已关闭")


# ============================================================
# 第3步：简单的 Agent 决策引擎（关键词匹配）
# ============================================================
# 【说明】真实系统中，这里会调用 LLM（Claude/GPT）来做决策.
# 本 Demo 用关键词匹配模拟，让你把注意力放在 MCP 协议本身.
#
# 这个 Agent 的作用等价于 Function Calling 中 LLM 做的事：
#   "分析用户输入 -> 选择合适的工具 -> 提取参数"

class SimpleAgent:
    """
    基于 MCP 的 Agent.

    流程：
      1. 通过 MCP 协议获取工具列表（而非硬编码）
      2. 用关键词匹配决定调用哪个工具
      3. 通过 MCP 协议调用工具
    """

    def __init__(self, mcp: McpClient):
        self.mcp = mcp
        self.tools = mcp.get_tools()

    def decide_and_call(self, user_input: str) -> str | None:
        """
        根据用户输入，决策并调用工具.

        返回工具执行结果，或 None（无法理解用户意图）.
        """
        user_lower = user_input.lower()

        # --- 规则1：数学计算 ---
        if self._match("calculator", user_input):
            # 用正则提取数学表达式
            expr = self._extract_expression(user_input)
            if expr:
                print(f"  [决策] 决策 -> calculator")
                print(f"  [参数] 提取参数 -> expression=\"{expr}\"")
                return self.mcp.call_tool("calculator", {"expression": expr})

        # --- 规则2：天气查询 ---
        if self._match("get_weather", user_input):
            city = self._extract_city(user_input)
            if city:
                print(f"  [决策] 决策 -> get_weather")
                print(f"  [参数] 提取参数 -> city=\"{city}\"")
                return self.mcp.call_tool("get_weather", {"city": city})

        # --- 规则3：时间查询 ---
        if self._match("get_current_time", user_input):
            print(f"  [决策] 决策 -> get_current_time")
            print(f"  [参数] 提取参数 -> (无)")
            return self.mcp.call_tool("get_current_time", {})

        return None

    def _match(self, tool_name: str, user_input: str) -> bool:
        """
        用关键词匹配判断用户意图.

        这是一个极度简化的"语义理解".
        真实场景中，LLM 会读 tool 的 description 和 inputSchema，
        然后判断最匹配的工具——逻辑上等价，只是实现手段不同.
        """
        keywords = {
            "calculator":       ["算", "计算", "等于", "多少", "+", "-", "*", "/"],
            "get_weather":      ["天气", "气温", "几度", "下雨", "晴天", "多云",
                                "北京", "上海", "广州", "深圳"],
            "get_current_time": ["时间", "几点", "日期", "今天几号", "星期"],
        }
        kw_list = keywords.get(tool_name, [])
        return any(kw in user_input for kw in kw_list)

    def _extract_expression(self, text: str) -> str | None:
        """从用户输入中提取数学表达式"""
        match = re.search(r'[\d+\-*/.()%\s]{3,}', text)
        return match.group().strip() if match else None

    def _extract_city(self, text: str) -> str | None:
        """从用户输入中提取城市名"""
        for city in ["北京", "上海", "广州", "深圳"]:
            if city in text:
                return city
        return None


# ============================================================
# 第4步：交互式主循环
# ============================================================

def main():
    print("""
+==========================================================+
|            [Agent] MCP Agent Demo                            |
|                                                          |
|  这是一个基于 MCP 协议的 Agent 示例.                      |
|                                                          |
|  架构：用户 -> Agent -> MCP客户端 -> (stdio) -> MCP服务端     |
|                                                          |
|  试试输入：                                               |
|    - 帮我算一下 100 + 200                                 |
|    - 北京今天天气怎么样                                    |
|    - 现在几点了                                           |
|                                                          |
|  输入 quit / exit / q 退出                                |
+==========================================================+
""")

    # ---- 创建 MCP 客户端并完成初始化 ----
    mcp = McpClient("mcp_server.py")
    try:
        mcp.initialize()                     # 协议握手 + 获取工具列表
    except Exception as e:
        log.error(f"MCP 初始化失败：{e}")
        return

    agent = SimpleAgent(mcp)

    # ---- 交互循环 ----
    while True:
        try:
            user_input = input("[>] 你：").strip()
            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                break

            result = agent.decide_and_call(user_input)
            if result:
                print(f"[信息] 结果：{result}")
            else:
                print("[?] 抱歉，我没理解你的需求.试试：")
                print("   - 帮我算一下 100 + 200")
                print("   - 北京今天天气怎么样")
                print("   - 现在几点了")
            print("-" * 55)

        except KeyboardInterrupt:
            print()
            break

    mcp.close()
    print("再见！")


if __name__ == "__main__":
    main()
