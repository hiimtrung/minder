# Swarm Setup — Claude Code + Antigravity (step-by-step)

> Hướng dẫn cấu hình để **Claude Code** và **Antigravity IDE** tham gia một Minder swarm.
> Bối cảnh thiết kế: `docs/roadmap/08-swarm-coordination-substrate.md`. Cam kết tại quyết định Q2.

Có hai vai trò một agent có thể đảm nhận, và hai kênh tương ứng:

| Kênh                      | Ai dùng    | Mục đích                                                       |
| ------------------------- | ---------- | -------------------------------------------------------------- |
| **MCP** (Minder = server) | mọi agent  | Agent **đọc/ghi blackboard**: `minder_swarm_*`, memory, graph… |
| **ACP** (Minder = client) | runner S-5 | Minder **chủ động điều khiển** một agent (tùy chọn, nâng cao)  |

Trước mắt chỉ cần **MCP** là chạy được swarm (pull-spawn). ACP là bước nâng cao ở cuối.

---

## 0. Khởi động Minder server

```bash
make native-run          # hoặc: minder-server
# Server SSE mặc định: http://localhost:8800/sse
```

Kiểm tra swarm bật trong `minder.toml`:

```toml
[swarm]
enabled = true
require_manifest_approval = true   # luôn cần người duyệt trước khi spawn
dispatcher_enabled = false         # pull-spawn trước; bật true để Minder tự spawn (S-4)
```

Lấy **client key** (dùng cho MCP header `X-Minder-Client-Key`): tạo từ Dashboard → Clients,
hoặc `minder login`.

---

## 1. Claude Code — cắm vào Minder qua MCP

Claude Code là MCP client. Thêm Minder làm MCP server:

```bash
# SSE (server đang chạy)
claude mcp add --transport sse minder http://localhost:8800/sse \
  --header "X-Minder-Client-Key: <YOUR_CLIENT_KEY>"
```

Hoặc thêm tay vào `~/.claude.json` / `.mcp.json` trong repo:

```json
{
  "mcpServers": {
    "minder": {
      "transport": "sse",
      "url": "http://localhost:8800/sse",
      "headers": { "X-Minder-Client-Key": "<YOUR_CLIENT_KEY>" }
    }
  }
}
```

Xác nhận: trong Claude Code chạy `/mcp` → thấy `minder` connected, và các tool `minder_swarm_*`.

> Mẹo: Minder cũng tự cài được MCP config cho nhiều IDE: `minder install --target claude-code`.

---

## 2. Antigravity IDE — cắm vào Minder qua MCP

Antigravity hỗ trợ MCP. Mở **Settings → MCP Servers → Add**, điền:

- **Name:** `minder`
- **Transport:** SSE (hoặc HTTP) → `http://localhost:8800/sse`
- **Header:** `X-Minder-Client-Key: <YOUR_CLIENT_KEY>`

Lưu, reload, kiểm tra danh sách tool có `minder_swarm_who`, `minder_swarm_claim`, …

> Nếu phiên bản Antigravity chỉ nhận file cấu hình, dùng `minder install --target antigravity`
> (hoặc copy khối JSON ở mục 1 vào file MCP config của Antigravity).

---

## 3. Chạy một swarm (pull-spawn, không cần ACP)

### 3a. Orchestrator (ví dụ Claude Code) — tạo & xin duyệt

Trong Claude Code, yêu cầu nó dùng các tool sau (hoặc tự gọi):

```
1. minder_swarm_create(goal="Refactor auth module")          → swarm_id
2. minder_swarm_plan(swarm_id, tasks=[
     {title:"scan callsites", runtime_hint:"claude"},
     {title:"apply patch",    runtime_hint:"codex", depends_on:[0]}
   ])
3. minder_swarm_propose(swarm_id)        → sinh manifest (pending_approval)
```

### 3b. Con người — duyệt manifest (cổng Q5)

Spawn **bị chặn** cho tới khi duyệt. Duyệt bằng một trong các cách:

```bash
minder swarm list                         # xem swarm_id + trạng thái
minder swarm who <swarm_id>               # xem worker dự kiến, ai/đâu/gì
minder swarm approve <swarm_id>           # hoặc --action edit --workers-file specs.json
```

Hoặc mở **Dashboard → Swarm**, bấm **Approve manifest**.

### 3c. Worker — tham gia & làm việc

Mỗi worker (Claude/Codex/Antigravity, đã cắm MCP) chạy quy trình chuẩn:

```
minder_swarm_join(swarm_id, runtime="claude", workspace="/path/repo")  → node_id
minder_swarm_who(swarm_id)                  # đọc trước khi làm → không trùng việc
minder_swarm_claim(task_id, node_id)        # chỉ làm khi claimed=true
... làm việc, GHI KẾT QUẢ vào store: minder_memory_store / graph / document ...
minder_swarm_report(task_id, node_id, status="done",
                    result_ref="memory:<id>", facts=["..."])
# gửi minder_swarm_heartbeat(node_id) định kỳ
```

### 3d. Orchestrator — tổng hợp

```
minder_swarm_collect(swarm_id)   → tóm tắt task + toàn bộ handoff (kèm artifact refs)
```

---

## 4. (Nâng cao) Để Minder tự spawn worker — Dispatcher (S-4)

Bật trong `minder.toml`:

```toml
[swarm]
dispatcher_enabled = true
dispatcher_tick_seconds = 60
max_concurrent_spawns = 3
```

Sau khi manifest được duyệt, dispatcher tự launch worker cho mỗi task `ready` có `runtime_hint`
(qua runner `claude`/`codex`/`antigravity`), tự thu hồi claim của node chết, tự dừng spawn sau
`failure_limit` lần fail. Worker được Minder spawn vẫn tự `join`/`claim`/`report` như mục 3c.

> Lệnh launch mỗi runtime nằm ở `application/swarm/runners/vendors.py` — chỉnh flag cho khớp
> phiên bản CLI bạn cài (ví dụ `claude -p ... --mcp-config ...`).

---

## 5. (Nâng cao) ACP — Minder điều khiển agent đồng nhất (S-5)

Khi muốn Minder **chủ động drive** một agent ACP-compatible qua một interface chung:

```bash
export MINDER_ACP_AGENT_CMD="<lệnh khởi động agent ACP của bạn>"
```

Runner `acp` sẽ: spawn agent → `initialize` → `session/new` (tiêm Minder MCP vào session) →
`session/prompt`, và **auto-approve** permission (vì đã qua cổng duyệt manifest). Dùng `runtime="acp"`
trong `runtime_hint` để dispatcher chọn đường ACP.

> ACP của Antigravity/Claude tùy phiên bản — xác nhận entrypoint headless trước khi dùng đường này.
> Đường MCP (mục 1–3) luôn là cách đơn giản và ổn định nhất để bắt đầu.

---

## 6. Khắc phục sự cố

| Triệu chứng                                  | Nguyên nhân & cách xử lý                                                           |
| -------------------------------------------- | ---------------------------------------------------------------------------------- |
| Agent không thấy tool `minder_swarm_*`       | MCP chưa connect — kiểm tra URL `/sse`, client key, và server đang chạy            |
| `minder_swarm_*` báo "manifest not approved" | Chưa duyệt — chạy `minder swarm approve <id>` hoặc duyệt ở Dashboard               |
| `claim` luôn trả `claimed:false`             | Task đã có người nhận, hoặc dependency chưa `done`. Gọi `minder_swarm_who` để xem  |
| Worker bị đánh dấu `dead`                    | Thiếu heartbeat — gửi `minder_swarm_heartbeat` định kỳ (< `heartbeat_ttl_seconds`) |
| Dispatcher không spawn                       | `dispatcher_enabled=false`, manifest chưa duyệt, hoặc task thiếu `runtime_hint`    |
