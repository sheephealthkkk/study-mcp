"""
+==============================================================+
|           MCP 服务端 — 基于 JSON-RPC 2.0 协议               |
|            transport: stdio (标准输入/输出)                  |
+==============================================================+

【这是什么？】
  一个符合 MCP (Model Context Protocol) 规范的工具服务端.
  它通过标准输入(stdin)接收 JSON-RPC 请求，通过标准输出(stdout)返回结果.

【MCP 协议核心概念】
  协议层：JSON-RPC 2.0 — 一种用 JSON 来远程调用的标准协议
  传输层：stdio — 通过进程的标准输入输出来通信
  消息格式：每行一个完整的 JSON 对象（换行符分隔）

【和传统 Function Calling 的关键区别】
  +----------------------+-----------------------------+
  | 传统 Function Calling |       MCP 协议              |
  +----------------------┼-----------------------------+
  | 工具定义写在 LLM      | 工具定义由服务端独立管理     |
  | 请求的 JSON 里        | 客户端动态发现              |
  +----------------------┼-----------------------------+
  | 耦合在 LLM API 中     | 独立进程，通过标准协议通信   |
  +----------------------┼-----------------------------+
  | 每家 LLM 格式不同     | 统一的 JSON-RPC 标准        |
  +----------------------┼-----------------------------+
  | 无状态，每次请求传     | 有状态长连接                |
  | 全部工具定义          | 工具注册一次，持续可用       |
  +----------------------+-----------------------------+

【运行方式】
  python mcp_server.py
  （不直接交互——它通过 stdio 与客户端进程通信）
"""

import sys
import json
import logging
from datetime import datetime
from typing import Any

# ============================================================
# 第1步：日志配置（写到 stderr，不污染协议通道）
# ============================================================
# 【关键设计】MCP 的 stdio 传输层中：
#   - stdin  = 接收 JSON-RPC 请求
#   - stdout = 发送 JSON-RPC 响应
#   - stderr = 日志/调试信息（不参与协议通信）
#
# 这样日志和协议数据完全分开，互不干扰.
logging.basicConfig(
    level=logging.DEBUG,
    format="[SERVER] %(levelname)s %(message)s",
    stream=sys.stderr  # ← 注意：写到 stderr，不污染 stdout 协议通道
)
log = logging.getLogger("mcp-server")


# ============================================================
# 第2步：工具的实际实现（纯业务逻辑，和协议无关）
# ============================================================
# 【关键设计】工具函数本身不包含任何 MCP/JSON-RPC 代码.
# 这是 MCP 的重要优势：工具实现和通信协议完全解耦.
# 同一个函数可以被 MCP,HTTP,CLI 等任何方式调用.

def _calculator(expression: str) -> str:
    """计算器：安全地执行数学表达式"""
    try:
        allowed = set("0123456789+-*/.()% ")
        if not all(c in allowed for c in expression):
            return f"错误：表达式包含不允许的字符"
        result = eval(expression)
        return f"{expression} = {result}"
    except Exception as e:
        return f"计算出错：{e}"


def _get_weather(city: str) -> str:
    """天气查询：返回模拟天气数据"""
    data = {
        "北京": "[晴] 晴天，25°C，湿度 40%，风力 2级",
        "上海": "[多云] 多云，28°C，湿度 65%，风力 3级",
        "广州": "[雨] 雷阵雨，30°C，湿度 80%，风力 4级",
        "深圳": "[阴] 阴天，29°C，湿度 70%，风力 3级",
    }
    return data.get(city, f"暂无「{city}」的天气数据.目前支持：{', '.join(data.keys())}")


def _get_time() -> str:
    """时间查询：返回当前日期时间"""
    now = datetime.now()
    weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    return f"{now.strftime('%Y年%m月%d日 %H:%M:%S')} 星期{weekdays[now.weekday()]}"


# ============================================================
# 第3步：工具注册表（MCP 格式的 inputSchema）
# ============================================================
# 【关键设计 — 和 Function Calling 的重要区别】
#
# 传统 FC 的工具定义格式（以 OpenAI 为例）：
#   {"type": "function", "function": {"name": "...", "parameters": {...}}}
#
# MCP 的工具定义格式：
#   {"name": "...", "description": "...", "inputSchema": {"type": "object", ...}}
#
# 差异点：
#   1. MCP 用 "inputSchema"，FC 用 "parameters"
#   2. MCP 的 inputSchema 是标准 JSON Schema 格式
#   3. MCP 的工具定义存在服务端，FC 的写在客户端代码里
#   4. MCP 通过 tools/list 动态发现，FC 每次请求都要传全部工具

TOOLS = [
    {
        "name": "calculator",
        "description": "执行数学运算.支持加减乘除,括号,小数和百分号.",
        "inputSchema": {                         # ← MCP 叫 inputSchema
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "数学表达式，例如 2+3,(10-2)*5"
                }
            },
            "required": ["expression"]           # "expression" 是必填参数
        }
    },
    {
        "name": "get_weather",
        "description": "查询指定城市当前的天气情况，包括温度,湿度,风力等.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "城市名称，例如：北京,上海,广州,深圳"
                }
            },
            "required": ["city"]
        }
    },
    {
        "name": "get_current_time",
        "description": "获取当前的日期,时间和星期.不需要任何参数.",
        "inputSchema": {
            "type": "object",
            "properties": {},                     # 无参数工具
            "required": []
        }
    },
]

# 工具名 -> 函数 的映射
TOOL_MAP = {
    "calculator": _calculator,
    "get_weather": _get_weather,
    "get_current_time": _get_time,
}


# ============================================================
# 第4步：JSON-RPC 2.0 消息处理
# ============================================================
# 【协议基础】JSON-RPC 2.0 定义了四种消息：
#   1. Request（请求） — 有 id 字段，期待响应
#   2. Response（成功响应） — 有 id 和 result 字段
#   3. Error（错误响应） — 有 id 和 error 字段
#   4. Notification（通知） — 无 id 字段，不期待响应

def make_response(req_id: Any, result: Any) -> dict:
    """构造一个 JSON-RPC 成功响应"""
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": result
    }


def make_error(req_id: Any, code: int, message: str) -> dict:
    """构造一个 JSON-RPC 错误响应"""
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {
            "code": code,
            "message": message
        }
    }


# ============================================================
# 第5步：MCP 协议方法处理
# ============================================================
# MCP 协议定义了几个核心方法（method），服务端必须处理它们：

def handle_initialize(req_id: Any, params: dict) -> dict:
    """
    处理 initialize 请求 — MCP 连接的第一步.

    【这是 MCP 独有的概念，FC 没有】
    客户端和服务端在开始工作前，先做一次"握手"：
      - 客户端告诉服务端：我支持什么协议版本,我有什么能力
      - 服务端告诉客户端：我支持什么版本,我有什么能力

    这样双方协商出一个都能接受的"能力集".
    比如：服务端可以说"我有 tools 能力"，客户端就知道可以调 tools/list.
    """
    client_version = params.get("protocolVersion", "unknown")
    log.info(f"客户端握手：协议版本={client_version}")
    log.info(f"客户端能力：{params.get('capabilities', {})}")

    return make_response(req_id, {
        "protocolVersion": "1.0",                 # 支持的协议版本
        "capabilities": {
            "tools": {}                           # 声明"我有工具能力"
            # 如果没有 tools 能力，客户端调 tools/list 就会收到错误
        },
        "serverInfo": {
            "name": "mcp-demo-server",
            "version": "1.0.0"
        }
    })


def handle_tools_list(req_id: Any, params: dict) -> dict:
    """
    处理 tools/list 请求 — 返回工具列表.

    【这是 MCP 和 FC 最大的架构差异之一】
    传统 FC：工具的"说明书"写在客户端代码里，发 LLM 请求时附带.
    MCP：工具说明书存在服务端，客户端通过 tools/list 动态发现.

    优势：
      1. 新增工具 -> 只需改服务端，客户端自动发现
      2. 不同客户端共享同一份工具定义
      3. 工具定义可以非常大（比如复杂 API 的 schema），
         不需要每次都传输
    """
    log.info(f"客户端请求工具列表，返回 {len(TOOLS)} 个工具")
    return make_response(req_id, {
        "tools": TOOLS                         # 直接返回注册表中的工具定义
    })


def handle_tools_call(req_id: Any, params: dict) -> dict:
    """
    处理 tools/call 请求 — 执行一个工具.

    params 格式：
      {
        "name": "calculator",                  # 工具名
        "arguments": {"expression": "2+3"}     # 参数键值对
      }

    MCP 中工具的返回格式是固定的：
      {
        "content": [
          {"type": "text", "text": "结果字符串"}
        ]
      }

    这个 content 数组可以有多个元素（多段文本,图片等），
    本 demo 只用最简单的单文本.
    """
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    log.info(f"调用工具 [{tool_name}] 参数={arguments}")

    # 查找工具
    func = TOOL_MAP.get(tool_name)
    if func is None:
        return make_error(req_id, -32601, f"工具不存在：{tool_name}")

    # 参数校验：检查必填参数是否齐全
    # 【MCP 优势】inputSchema 已经声明了 required 字段，
    # MCP 客户端可以在调用前就校验参数，减少无效请求.
    tool_def = next((t for t in TOOLS if t["name"] == tool_name), None)
    if tool_def:
        required_params = tool_def["inputSchema"].get("required", [])
        for rp in required_params:
            if rp not in arguments:
                return make_error(req_id, -32602, f"缺少必填参数：{rp}")

    # 执行业务逻辑
    try:
        result_text = func(**arguments)          # 展开字典为关键字参数
    except TypeError as e:
        return make_error(req_id, -32602, f"参数类型错误：{e}")
    except Exception as e:
        return make_error(req_id, -32603, f"工具执行出错：{e}")

    # 包装成 MCP 标准返回格式
    return make_response(req_id, {
        "content": [
            {"type": "text", "text": result_text}
        ]
    })


# 方法路由表：收到什么 method，就调哪个处理函数
METHOD_HANDLERS = {
    "initialize":       handle_initialize,
    "tools/list":       handle_tools_list,
    "tools/call":       handle_tools_call,
}


# ============================================================
# 第6步：stdio 传输层 — 消息的收发
# ============================================================
# MCP 支持多种传输方式（stdio,HTTP+SSE,WebSocket），
# 本 demo 使用 stdio，因为：
#   1. 最简单，不需要网络端口
#   2. 进程管理清晰（客户端启动服务端为子进程）
#   3. 天然隔离（只能和父进程通信，不会被外部访问）
#   4. 是 MCP 规范中最基础,最推荐的本地传输方式

def read_message() -> dict | None:
    """
    从 stdin 读取一行 JSON-RPC 消息.

    MCP 的 stdio 传输中，每条消息是一行完整的 JSON.
    为什么用"行分隔"而不是"固定长度"？
      - JSON 天然是文本，长度不固定
      - 换行符分隔最简单,人类可读,易调试
      - 和许多日志/流处理工具兼容
    """
    line = sys.stdin.readline()
    if not line:
        return None                              # EOF，客户端关闭了连接
    try:
        return json.loads(line)
    except json.JSONDecodeError as e:
        log.error(f"无效的 JSON：{e}")
        return None


def write_message(msg: dict):
    """
    向 stdout 写入一行 JSON-RPC 消息.

    关键点：
      1. json.dumps 不换行（不要 indent，减少传输量）
      2. 手动加换行符分隔
      3. flush 立即刷新缓冲区（否则消息可能卡在缓冲里）
    """
    line = json.dumps(msg, ensure_ascii=False)    # ensure_ascii=False 保留中文
    sys.stdout.write(line + "\n")
    sys.stdout.flush()                             # 必须立即 flush


def dispatch_message(msg: dict) -> dict | None:
    """
    根据 method 字段，把消息分发给对应的处理函数.

    返回值：
      - 如果是 Request（有 id），返回响应字典
      - 如果是 Notification（无 id），返回 None（不需要响应）
    """
    method = msg.get("method", "")
    req_id = msg.get("id")                         # Notification 没有 id
    params = msg.get("params", {})

    # 特殊处理：initialized 通知（握手完成后的确认，无需响应）
    if method == "notifications/initialized":
        log.info("客户端通知：初始化完成")
        return None

    handler = METHOD_HANDLERS.get(method)
    if handler is None:
        log.warning(f"未知方法：{method}")
        return make_error(req_id, -32601, f"不支持的方法：{method}")

    return handler(req_id, params)


# ============================================================
# 第7步：主循环
# ============================================================
def main():
    """
    MCP 服务端主循环.

    工作流程：
      1. 从 stdin 读一行 JSON
      2. 根据 method 分发给对应处理函数
      3. 把响应写到 stdout
      4. 重复，直到 stdin 关闭（客户端退出）

    这是一个经典的"请求-响应"循环.
    """
    log.info("MCP 服务端启动，等待客户端连接...")
    log.info(f"已注册 {len(TOOLS)} 个工具")

    while True:
        msg = read_message()
        if msg is None:
            log.info("stdin 已关闭，服务端退出")
            break

        method = msg.get("method", "?")
        req_id = msg.get("id", "?")
        log.debug(f"收到请求：method={method} id={req_id}")

        response = dispatch_message(msg)
        if response is not None:
            write_message(response)


if __name__ == "__main__":
    main()
