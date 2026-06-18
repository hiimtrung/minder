# 08. Minder - Lớp nền Điều phối Swarm đa Agent (Multi-Agent Swarm Coordination Substrate)

> **Trạng thái:** ĐÃ TRIỂN KHAI (S-0 → S-5 + CLI/OBS + HƯỚNG DẪN) · **Ngày:** 2026-06-18

## Trạng thái triển khai thực tế (Cập nhật 2026-06-18)

| Phase | Hạng mục công việc | Trạng thái | Tệp tin liên quan |
| :--- | :--- | :--- | :--- |
| **S-0** | Presence registry (đăng ký trạng thái hoạt động) + cơ sở dữ liệu `swarm.db` riêng biệt | ✅ Hoàn thành | `domain/entities/swarm.py`, `models/swarm.py`, `store/swarm.py` |
| **S-1** | Task Board (bảng tác vụ) + cơ chế nhận việc atomic (atomic claim) + DAG (đồ thị có hướng không chu trình) + Handoff (con trỏ bàn giao) + Giới hạn số lần lỗi (failure-limit) | ✅ Hoàn thành | `application/swarm/service.py` |
| **S-2b** | Cổng phê duyệt: Quy hoạch manifest + phê duyệt (approve) + cổng kiểm soát cứng tại Runner | ✅ Hoàn thành | `service.py` (`propose`/`approve`/`assert_can_spawn`) |
| **—** | Tập hợp 11 công cụ MCP Swarm + đăng ký hệ thống + các mẫu tự động khám phá (discovery patterns) | ✅ Hoàn thành | `tools/swarm.py`, `bootstrap/handlers/swarm_handlers.py`, `domain/value_objects.py` |
| **S-3** | Đăng ký các bộ chạy (Runner Adapter Registry): claude/codex/antigravity/acp/mock, hỗ trợ tự kích hoạt (pull-spawn) | ✅ Hoàn thành | Thư mục `application/swarm/runners/` |
| **S-4** | Dispatcher (Bộ điều phối tự động kích hoạt worker theo gợi ý `runtime_hint`, tự động thu hồi khi mất kết nối/heartbeat-reclaim, cổng phê duyệt và thời gian chờ hạ nhiệt/cooldown) | ✅ Hoàn thành | `application/swarm/dispatcher.py` |
| **S-5** | `AcpRunner` + `AcpClient` (Tương tác qua giao thức ACP, tự động chấp thuận quyền) | ✅ Hoàn thành | `application/swarm/runners/acp.py` |
| **CLI/OBS**| API HTTP (`/api/v1/swarms*`) + Lệnh CLI `minder swarm` + Giao diện quản lý Swarm trên Dashboard | ✅ Hoàn thành | `presentation/http/admin/swarm.py`, `presentation/cli/commands/swarm.py`, `dashboard/.../SwarmShell.astro` |
| **GUIDE** | Hướng dẫn cấu hình từng bước cho Claude Code và Antigravity IDE | ✅ Hoàn thành | `docs/guides/swarm-setup-claude-antigravity.md` |
| **—** | Kết nối server + cấu hình hệ thống + tích hợp vào `minder.toml` | ✅ Hoàn thành | `server.py`, `bootstrap/transport.py`, `config.py`, `minder.toml` |
| **—** | Bộ kiểm thử tích hợp (kiểm tra luồng hoạt động, atomic claim, failure-limit, dọn dẹp node chết, dispatcher, ACP, HTTP) | ✅ Hoàn thành | `tests/integration/test_swarm*.py` (9/9 pass) |

> **Toàn bộ lộ trình Phase 08 đã được triển khai thành công** (từ S-0 đến S-5, CLI/OBS và Hướng dẫn). 9 bài kiểm thử tích hợp cho Swarm đã chạy thành công, không gây ảnh hưởng đến các thành phần cũ trong kho mã nguồn.
> *Lưu ý vận hành*: Các lệnh khởi chạy trong `runners/vendors.py` và cổng vào của ACP cần được tinh chỉnh thêm tùy thuộc vào phiên bản CLI thực tế được cài đặt trên môi trường của bạn.

---

> **Tóm tắt ý tưởng**: Biến Minder từ vai trò ban đầu là "MCP server lưu trữ kiến thức" thành một **lớp nền điều phối (coordination substrate)**. Nhờ đó, bất kỳ agent nào (Claude Code, Codex, Gemini, Antigravity...) cũng có thể lấy quy trình làm việc từ Minder, tạo ra một swarm gồm các subagent thuộc các nhà cung cấp khác nhau, phối hợp hành động thông qua Minder, và lưu kết quả cuối cùng. Minder đóng vai trò là **nguồn sự thật duy nhất (single source of truth)** giúp các agent luôn biết "ai đang làm gì, ở đâu, trạng thái thế nào", giảm thiểu tối đa hiện tượng ảo tưởng (hallucination).

---

## 1. Bài toán cần giải quyết (Problem Statement)

Kịch bản điều phối mong muốn:

```
Claude ──gọi (call)──▶ Minder: "Lấy quy trình cho công việc X"
Claude ──phân tích──▶ Tạo Swarm gồm: subagent A, B, C
   A,B,C ──gọi Minder──▶ Trao đổi thông tin, biết ai đang làm gì
   A,B,C ──hoàn thành──▶ Ghi kết quả thực hiện vào Minder
Minder ──tổng hợp──▶ Trả kết quả cho Claude
   (Và Claude có thể được thay thế bằng bất kỳ agent nào khác)
```

Bốn yêu cầu cốt lõi được rút ra:

| Mã yêu cầu | Yêu cầu thiết kế | Hậu quả nếu thiếu |
| :--- | :--- | :--- |
| **R1** | **Quy trình nghiệp vụ nằm tại Minder, không phụ thuộc vào Claude** | Đổi orchestrator (agent điều phối chính) là mất toàn bộ quy trình nghiệp vụ |
| **R2** | **Subagent có thể thuộc bất kỳ nhà cung cấp nào** (Codex, Antigravity,...) | Bị khóa chặt (vendor lock-in) vào một hãng cung cấp dịch vụ LLM duy nhất |
| **R3** | **Các agent nắm bắt được trạng thái hoạt động của nhau** | Trùng lặp công việc, đưa ra giả định sai, dẫn đến **ảo tưởng (hallucination)** |
| **R4** | **Minder là kho lưu trữ và tổng hợp mọi tri thức** | Mỗi agent lưu trữ dữ liệu một kiểu, thông tin bị phân mảnh, sai lệch |

**Nguyên tắc nền tảng (Blackboard Architecture - Kiến trúc Bảng đen)**: Các agent **không giao tiếp trực tiếp với nhau**. Chúng đọc và ghi thông tin lên một bảng dữ liệu chung là Minder. Khi một agent cần biết bất kỳ thông tin gì, nó sẽ **truy vấn sự thật từ Minder** thay vì tự suy đoán. Đây là cơ chế cốt lõi chống ảo tưởng ở cấp độ kiến trúc hệ thống.

---

## 2. Minder đã có sẵn gì (Tránh phát triển lại)

Khảo sát kho mã nguồn hiện tại — chúng ta đã có nền móng vững chắc:

| Năng lực Swarm cần | Minder hiện có | Ghi chú |
| :--- | :--- | :--- |
| **Phiên làm việc đa agent** | ✅ `minder_session_boot(project_name=...)` | Hỗ trợ "Máy A tạo, Máy B tham gia" — **đã có cơ chế đa node nguyên bản** |
| **Quy trình có kiểm soát** | ✅ `minder_workflow_get/step/guard/update` | `workflow_guard` giúp ngăn chặn việc nhảy bước hoặc làm sai trình tự |
| **Nguồn sự thật duy nhất (R4)**| ✅ graph + memory + document + history store | Đã có sẵn vector (turbovec) và cơ sở dữ liệu quan hệ (sqlite) |
| **Định nghĩa Agent** | ✅ `minder_agent_store/list/get` (thực thể `agent.py`) | Tuy nhiên đây mới chỉ là **định nghĩa cấu hình**, chưa phải **thực thể đang chạy** |
| **Tự học Kỹ năng / Mẫu** | ✅ `learning/*` + `tools/skills.py` | Xem chi tiết tại tài liệu Phase 07 |
| **Chống Tool-blindness** | ✅ `tool_capability_manifest`, deferred discovery | Xem chi tiết tại tài liệu cải tiến LLM UX |
| **Presence / Liveness (R3)** | ❌ **THIẾU** | Trạng thái "Ai đang hoạt động, làm công việc gì ngay lúc này" |
| **Task Board / Claim / Handoff**| ❌ **THIẾU** | Quy trình hiện tại là tuyến tính cho một repo, chưa hỗ trợ hàng đợi đa worker |
| **Runner cho agent dị chủng (R2)**| ❌ **THIẾU** | Cơ chế khởi chạy Codex/Antigravity và kết nối chúng vào hệ thống Minder |
| **CLI điều phối Swarm** | ❌ Chỉ có lệnh `sync` | Cần mở rộng thêm tập lệnh CLI điều phối (mục 8) |

Ba khoảng trống đánh dấu ❌ chính là phạm vi công việc đã được hoàn thành trong lộ trình này.

---

## 3. Khả năng tương tác của Codex / Antigravity

**Hoàn toàn khả thi. Cơ chế tương tác chung là giao thức MCP (Model Context Protocol) — đó là lý do vì sao việc thiết kế Minder dưới dạng MCP server là một lựa chọn đúng đắn.**

### 3.1. MCP đóng vai trò ngôn ngữ chung (Lingua Franca)

Vì Minder hoạt động như một **MCP server**, bất kỳ agent nào có khả năng đóng vai trò là **MCP client** đều có thể kết nối vào cùng một thực thể Minder:

```
            ┌──────────────────── Minder (MCP server + Bảng đen) ──────────────┐
            │  presence · board · workflow · graph · memory · skills           │
            └───▲────────────▲────────────▲────────────▲───────────────────────┘
                │ MCP        │ MCP        │ MCP        │ MCP
          ┌─────┴────┐ ┌─────┴────┐ ┌─────┴─────┐ ┌────┴──────┐
          │ Claude   │ │ Codex    │ │ Gemini    │ │ Antigravity│   ← Bất kỳ agent nào hỗ trợ MCP
          │ (orchestr)│ │ (worker) │ │ (worker)  │ │ (worker)   │
          └──────────┘ └──────────┘ └───────────┘ └───────────┘
```

Minder **không cần biết** kiến trúc bên trong của Claude hay Codex hoạt động ra sao. Nó chỉ yêu cầu mỗi node thực hiện đúng 4 tác vụ thông qua giao thức MCP: **(1) Khai báo sự hiện diện (presence)**, **(2) Đăng ký/cập nhật công việc (claim task)**, **(3) Đọc trạng thái chung của hệ thống**, và **(4) Ghi nhận kết quả vào nguồn sự thật duy nhất**. Bất kỳ hãng AI nào cũng được chấp nhận, miễn là hỗ trợ giao thức MCP.

> *Tính khả thi của MCP theo runtime*: Claude Code ✅, Codex CLI ✅, Gemini CLI ✅, Cursor/Windsurf ✅, Zed ✅, Google Antigravity (agentic IDE) — hỗ trợ MCP, cần cấu hình phù hợp.

### 3.2. Hai mô hình khởi chạy worker (Spawn Models)

**(a) Pull / Orchestrator-spawn (Kích hoạt từ Agent)**:
Orchestrator (ví dụ: Claude Code) tự khởi chạy subagent của mình bằng cách thực thi lệnh hệ thống (shell-out) ví dụ như `codex ...` kèm theo cấu hình MCP trỏ về Minder và một ID công việc (`task_id`). Subagent khởi động và gửi yêu cầu `minder_swarm_join(task_id=...)` để đăng ký hoạt động. Minder **không trực tiếp khởi chạy** tiến trình — chỉ đóng vai trò giám sát.
*Ưu điểm*: Đơn giản, việc khởi chạy do orchestrator tự đảm nhận.

**(b) Dispatcher / Minder-spawn (Minder tự khởi chạy)**:
Tương tự như cơ chế quản lý Kanban của Hermes. Orchestrator chỉ tạo công việc trên bảng và chỉ định tham số `runtime_hint="codex"`. Một bộ điều phối chạy ngầm (`Dispatcher`) trong Minder sẽ phát hiện công việc chưa có người làm, gọi đến **Runner Adapter** tương ứng để khởi chạy tiến trình agent, tiêm cấu hình MCP và ID công việc qua biến môi trường.
*Ưu điểm*: Quản lý tập trung tốt hơn (R3), dễ dàng hoán đổi runtime linh hoạt bằng cách thay đổi giá trị trường `runtime`.

### 3.3. Trình đăng ký Bộ chạy (Runner Adapter Registry)

Tương tự như cấu trúc quản lý môi trường (`tools/environments/`) của Hermes, nhưng áp dụng cho **Agent Runtime**:

```python
# application/swarm/runners/base.py
class AgentRunner(Protocol):
    name: str                       # "claude" | "codex" | "gemini" | "antigravity" | "acp:<id>"
    async def spawn(self, *, task_id, mcp_endpoint, prompt, cwd, env) -> RunnerHandle: ...
    async def status(self, handle) -> RunnerStatus: ...
    async def cancel(self, handle) -> None: ...
```

- `ClaudeRunner`: Khởi chạy `claude` (chế độ không giao diện/headless) với tham số `--mcp-config` trỏ đến Minder.
- `CodexRunner`: Khởi chạy `codex exec` kết hợp cấu hình MCP server.
- `AcpRunner`: Sử dụng giao thức **ACP (Agent Client Protocol)** để điều phối bất kỳ agent nào tương thích với ACP thông qua một giao diện chung duy nhất (gửi prompt → nhận luồng updates → duyệt yêu cầu xin quyền). Đây là cách Hermes tích hợp vào Zed/VS Code (`acp_adapter/`); ở đây chúng ta dùng theo chiều ngược lại — Minder làm **ACP client** để sai khiến worker. Một ACP adapter có thể áp dụng cho nhiều runtime mà không cần viết lại mã nguồn riêng cho từng hãng.
- Cài đặt đăng ký dạng nhà cung cấp (provider-style) tương tự như `llm/factory.py` (`create_runner(runtime)`).

> **Kết quả đạt được cho R2**: Để bổ sung một agent runtime mới, chúng ta chỉ cần viết thêm một adapter tương ứng dài khoảng 100 dòng mã nguồn mà không cần thay đổi cấu trúc chung của hệ thống.

### 3.4. Giao thức ACP là gì?

**ACP = Agent Client Protocol**. Có thể dễ dàng hình dung ACP thông qua bảng so sánh đối chiếu với giao thức MCP:

| Đặc điểm so sánh | MCP (Minder hiện tại) | ACP (Dùng cho Runner) |
| :--- | :--- | :--- |
| **Câu hỏi cốt lõi** | "Agent **sử dụng công cụ** như thế nào?" | "Hệ thống **điều khiển một agent** như thế nào?" |
| **Vai trò của Minder** | **Server** — cung cấp công cụ/dữ liệu cho agent | **Client** — gửi yêu cầu công việc, nhận kết quả trả về từ agent |
| **Ví dụ thực tế** | Claude gọi công cụ `minder_swarm_who` | Minder chỉ thị agent: "Làm công việc X đi" và quan sát tiến độ qua stream |

Nói cách khác: **MCP giúp agent giao tiếp với Minder; ACP giúp Minder điều khiển agent**. Hai giao thức bổ trợ cho nhau và hoạt động song song.

**Lý do tích hợp ACP cho Runner (R2)**: Thay vì phải viết mã nguồn riêng biệt để xử lý luồng phản hồi cho từng hãng (`claude`, `codex`, `gemini` mỗi bên có một định dạng CLI và cấu trúc đầu ra khác nhau), giao thức ACP cung cấp **một giao diện chuẩn hóa duy nhất**: *gửi yêu cầu (prompt) → nhận luồng xử lý (suy nghĩ, gọi công cụ, trạng thái) → gửi phản hồi duyệt quyền khi agent yêu cầu phê duyệt*. Một tiến trình `AcpRunner` chuẩn giao thức ACP có thể điều khiển bất kỳ agent nào hỗ trợ ACP mà không cần duy trì nhiều bộ adapter khác nhau.

```
Minder (ACP client)  ──"Làm công việc #42"──▶  Agent dị chủng (ACP server: claude/gemini/…)
        ◀── stream: suy nghĩ / gọi tool / xin quyền / hoàn thành ──
        (Và song song đó, agent vẫn kết nối với Minder qua MCP để đọc/ghi thông tin lên bảng đen)
```

> Một worker sẽ đồng thời là **ACP server** (để tiếp nhận chỉ thị từ Minder) và là **MCP client** (để đọc/ghi dữ liệu lên Minder). Hai kênh truyền thông với hai mục tiêu hoàn toàn khác nhau.

**Vận hành thực tế với Claude Code & Antigravity IDE**:
- **Chạy cơ bản (Không cần ACP)**: Cả hai công cụ đều đã tích hợp sẵn tính năng làm **MCP client**. Bạn chỉ cần cấu hình cấu điểm kết nối MCP trỏ về Minder là chúng có thể tham gia vào Swarm ngay lập tức (đọc thông tin bảng, đăng ký nhận việc, báo cáo tiến độ). Đây là lộ trình từ S-0 đến S-3 (pull-spawn), **không phụ thuộc vào giao thức ACP**.
- **Chạy nâng cao (Điều khiển đồng nhất)**: Sử dụng thêm `AcpRunner` để Minder chủ động điều khiển worker qua giao thức ACP (S-5). Khi đó mới cần kích hoạt giao thức ACP trên Antigravity/Claude.
- 📌 **Cam kết**: Hướng dẫn cấu hình từng bước cho cả hai công cụ được trình bày chi tiết tại tệp tin hướng dẫn độc lập: [swarm-setup-claude-antigravity.md](file:///Users/trungtran/ai-agents/minder/docs/guides/swarm-setup-claude-antigravity.md).

---

## 4. Mô hình Dữ liệu Swarm

> **QUYẾT ĐỊNH (Q3): Tách biệt cơ sở dữ liệu cho presence/board**. Tần suất gửi ping (heartbeat) từ nhiều worker hoạt động song song là rất lớn. Nếu lưu trữ chung trong cơ sở dữ liệu nghiệp vụ (`state.db`) sẽ dễ xảy ra tình trạng tranh chấp khóa ghi (WAL lock) và làm chậm các truy vấn thông thường của Graph/Memory.
> Do đó, toàn bộ dữ liệu điều phối trạng thái (node, task, heartbeat) sẽ được lưu trữ riêng tại **`~/.minder/data/swarm.db` (SQLite độc lập)**. Khi worker cần ghi nhận **kết quả công việc thực tế**, nó sẽ ghi trực tiếp vào cơ sở dữ liệu nghiệp vụ (graph/memory) thông qua các công cụ MCP sẵn có.

Ba thực thể dữ liệu mới được quản lý tại cơ sở dữ liệu `swarm.db`:

### 4.1. `SwarmNode` — Đăng ký sự hiện diện (Presence Registry)

```python
# domain/entities/swarm_node.py
class SwarmNode:
    id: str
    runtime: str            # "claude" | "codex" | ...
    role: str               # "orchestrator" | "worker"
    session_id: str         # Gắn với phiên làm việc của dự án
    current_task_id: str | None
    status: str             # "idle" | "working" | "blocked" | "done" | "dead"
    workspace: str          # Thư mục làm việc hiện tại (cwd/repo path)
    capabilities: list[str] # Tập công cụ/kỹ năng được cấp quyền
    last_heartbeat_at: datetime
    started_at: datetime
    finished_at: datetime | None
```

Cơ chế Heartbeat (tương tự như `kanban_heartbeat` của Hermes): Worker gửi ping cập nhật trạng thái định kỳ mỗi N giây. Nếu quá hạn ping, trạng thái node sẽ tự động chuyển thành `dead` và hệ thống sẽ thu hồi công việc nó đang đảm nhận. Đây là cơ sở để trạng thái hoạt động thực tế của swarm luôn được cập nhật chính xác.

### 4.2. `SwarmTask` — Bảng quản lý công việc (Task Board)

```python
# domain/entities/swarm_task.py
class SwarmTask:
    id: str
    swarm_id: str
    title: str
    description: str
    workflow_id: str | None   # Liên kết quy trình nghiệp vụ tương ứng (R1)
    status: str               # "ready" | "claimed" | "in_progress" | "blocked" | "done" | "failed"
    assignee_node_id: str | None
    runtime_hint: str | None  # Gợi ý runtime cho bộ điều phối Dispatcher
    depends_on: list[str]     # Đồ thị phụ thuộc DAG
    claim_expires_at: datetime | None
    result_ref: str | None    # Con trỏ liên kết đến kết quả lưu tại Graph/Memory store (R4)
    attempts: int             # Số lần thử thực hiện
```

Tích hợp cơ chế đăng ký nhận việc atomic (atomic claim), ràng buộc đồ thị DAG `depends_on`, và tự động chặn công việc (`failure_limit` auto-block) sau 2 lần thực hiện thất bại liên tiếp để tránh rơi vào vòng lặp vô hạn.

### 4.3. Cơ chế Lưu trữ Kết quả & Thực thể bàn giao `Handoff`

> **QUYẾT ĐỊNH (Q4): Cho phép worker ghi trực tiếp vào Graph/Memory store nghiệp vụ**. Chúng ta không bắt buộc mọi dữ liệu ghi nhận phải đi qua một cổng trung gian kiểm soát của Handoff. Việc kiểm tra chất lượng và loại bỏ dữ liệu trùng lặp sẽ do **trình lập lịch dọn dẹp chạy nền** xử lý (chi tiết tại tài liệu Phase 07: `memory_dedupe`, `graph_prune`, `vector_optimize`). Thiết kế gác cổng quá chặt ở bước ghi dữ liệu sẽ gây nghẽn tiến độ làm việc của Swarm.

Luồng hoạt động:
1. Worker hoàn thành công việc → **ghi trực tiếp** kết quả vào cơ sở dữ liệu nghiệp vụ thông qua các công cụ MCP sẵn có (`minder_memory_store`, graph sync, document ingest).
2. Worker gọi công cụ `minder_swarm_report(...)` → hệ thống tạo ra một thực thể **`Handoff` gọn nhẹ** đóng vai trò là **con trỏ liên kết và tóm tắt kết quả** (hoàn toàn không sao chép lại toàn bộ nội dung dữ liệu). Mục tiêu là giúp orchestrator hoặc worker ở bước kế tiếp biết thông tin đang nằm ở đâu để truy vấn.
3. Trình lập lịch bảo trì chạy nền (Phase 07) sẽ đảm nhận dọn dẹp và chuẩn hóa dữ liệu sau đó.

```python
# domain/entities/handoff.py
class Handoff:
    from_task_id: str
    to_task_id: str
    from_node_id: str
    summary: str               # Tóm tắt ngắn gọn 1-3 câu về kết quả công việc
    artifact_refs: list[str]   # Danh sách ID liên kết đến dữ liệu trong document/graph/memory store
    facts: list[str]           # Các kết luận chính rút ra từ công việc
```

Cơ chế chống ảo tưởng vẫn được đảm bảo: Agent ở bước sau sẽ **đọc dữ liệu thực tế từ liên kết `artifact_refs`** thay vì chỉ dựa vào thông tin tóm tắt ngắn gọn ở `summary`.

---

## 5. Giao diện Công cụ MCP mới cho Swarm

Được định nghĩa tại `tools/swarm.py` và đăng ký tập trung tại `domain/value_objects.py`:

| Tên công cụ | Đối tượng gọi | Tác dụng |
| :--- | :--- | :--- |
| `minder_swarm_create(workflow_id, goal)` | Orchestrator | Khởi tạo một swarm mới liên kết với một quy trình (R1) |
| `minder_swarm_plan(swarm_id)` | Orchestrator | Phân rã quy trình thành các công việc cụ thể liên kết dạng đồ thị DAG |
| `minder_swarm_propose(swarm_id)` | Orchestrator | **Tạo Swarm Manifest để người dùng phê duyệt** (Bắt buộc trước khi khởi chạy worker) |
| `minder_swarm_approve(swarm_id, action, edits)` | Người dùng | Phê duyệt / Chỉnh sửa / Từ chối manifest để mở khóa quyền khởi chạy worker |
| `minder_swarm_join(task_id, runtime, workspace)` | Worker | Đăng ký thông tin hoạt động của worker vào swarm (R3) |
| `minder_swarm_heartbeat(node_id, status)` | Worker | Gửi ping cập nhật trạng thái hoạt động |
| `minder_swarm_who(swarm_id)` | Mọi Agent | Truy vấn trạng thái hoạt động thực tế của toàn swarm (R3) |
| `minder_swarm_claim(task_id, node_id)` | Worker | Đăng ký nhận việc atomic để tránh làm trùng lặp công việc |
| `minder_swarm_report(task_id, result_ref, status)`| Worker | Báo cáo hoàn thành công việc và tạo thực thể liên kết Handoff (R4) |
| `minder_swarm_block(task_id, reason)` | Worker | Báo cáo trạng thái bị nghẽn công việc để Dispatcher xử lý |
| `minder_swarm_collect(swarm_id)` | Orchestrator | Tổng hợp toàn bộ Handoff để kết thúc quy trình |

Cấu hình ẩn công cụ khi không hoạt động (`always_available=False`) giúp giữ giao diện danh sách công cụ sạch sẽ khi không chạy Swarm.

---

## 6. Cơ chế Độc lập với Orchestrator (Orchestrator-Agnostic)

**Quy trình làm việc được lưu giữ và quản lý tại Minder, không phụ thuộc vào bộ não của Claude**. Agent điều phối chỉ đóng vai trò chạy một vòng lặp kiểm tra đơn giản:

```
Vòng lặp:
  Trạng thái hiện tại = minder_swarm_who(swarm) + danh sách công việc trên bảng
  Công việc tiếp theo = minder_workflow_step(...)          # Minder quyết định bước đi tiếp theo
  Nếu bước tiếp theo cần worker: Khởi chạy worker tương ứng (qua pull hoặc dispatcher)
  Tổng hợp kết quả bàn giao; cập nhật trạng thái quy trình qua minder_workflow_update(...)
  Lặp lại cho đến khi quy trình hoàn thành → gọi minder_swarm_collect()
```

Vòng lặp điều phối này rất đơn giản nên có thể thực thi dễ dàng bởi Claude Code, Codex, hay chỉ là một script Python chạy cục bộ. Đổi agent điều phối chỉ là thay thế lớp vỏ tương tác bên ngoài, toàn bộ quy trình nghiệp vụ và dữ liệu vẫn được bảo toàn trọn vẹn tại Minder.

---

## 6b. Cổng phê duyệt Swarm — Swarm Manifest

> **Quyết định chốt**: **Luôn bắt buộc con người phê duyệt trước khi khởi chạy bất kỳ worker nào**, không phân biệt công cụ đó có phát sinh chi phí gọi API đám mây hay không.
> Trước khi kích hoạt bất kỳ worker nào, hệ thống phải kết xuất thông tin **Swarm Manifest** bao gồm danh sách chi tiết các worker, vai trò và phạm vi hoạt động để người dùng kiểm tra và duyệt.

### Luồng phê duyệt chi tiết

```
orchestrator: minder_swarm_plan()      → Phân rã công việc (DAG)
orchestrator: minder_swarm_propose()   → Sinh thông tin Swarm Manifest ─┐
                                                                        ▼
                               ┌──────── Dashboard / CLI hiển thị thông tin Manifest ──────┐
Người dùng:                    │  Duyệt từng worker: Approve / Edit / Reject               │
                               │  Chỉnh sửa: runtime, workspace, bộ công cụ, giới hạn...    │
                               └───────────────────────────────────────────────────────────┘
                                                                        │ Đã phê duyệt (Approved)
orchestrator: spawn  ◀── BỊ CHẶN cho đến khi trạng thái manifest chuyển sang "approved" ─┘
```

Bộ chạy (`AgentRunner.spawn`) sẽ **từ chối thực thi** nếu swarm liên quan chưa được chuyển sang trạng thái `approved`. Ràng buộc cứng này được đặt ở tầng Runner của hệ thống để đảm bảo tính an toàn.

### Mô hình cấu trúc Swarm Manifest

```python
# domain/entities/swarm_manifest.py
class SwarmManifest:
    swarm_id: str
    goal: str
    workflow_id: str
    status: str                  # Trạng thái: "pending_approval" | "approved" | "rejected"
    workers: list[WorkerSpec]
    estimated_cost_note: str     # Cảnh báo nếu sử dụng các runtime đám mây có tính phí
    approved_by: str
    approved_at: datetime
    
class WorkerSpec:
    label: str                   # Nhãn: "scanner", "patcher", ...
    runtime: str                 # Loại bộ chạy: "claude" | "codex" | "antigravity" | ...
    role: str                    # Vai trò: "worker" | "orchestrator"
    function: str                # Mô tả công việc cụ thể worker sẽ làm
    task_ids: list[str]          # Danh sách ID công việc liên kết
    workspace: str               # Thư mục làm việc thực thi
    toolsets: list[str]          # Danh sách công cụ được cấp quyền sử dụng
    max_iterations: int          # Giới hạn số bước chạy an toàn
    budget: float                # Ngân sách chạy tối đa
    editable: bool = True        # Cho phép người dùng chỉnh sửa thông số trước khi duyệt
```

Người dùng có toàn quyền chỉnh sửa các thông số của `WorkerSpec` (chuyển đổi runtime, giới hạn công cụ, siết chặt ngân sách chạy) trực tiếp trước khi nhấn duyệt.

### Giao diện quản trị tương ứng

- **Dashboard**: Trang quản lý tại `/dashboard/swarm/` hiển thị bảng danh sách các worker với các cột cấu hình chi tiết, đi kèm nút duyệt nhanh **Approve all / Reject / Edit từng dòng**.
- **Giao diện dòng lệnh CLI**: Sử dụng lệnh `minder swarm propose <id>` để xuất manifest và lệnh `minder swarm approve <id> [--edit ...]` để duyệt.

---

## 7. Cơ chế chặn ảo tưởng (Anti-Hallucination)

Các điểm chặn kỹ thuật được thiết kế trong hệ thống:

1. **Đọc thông tin thực tế trước**: Trước khi thực hiện hành động, worker bắt buộc phải gọi `minder_swarm_who` và `minder_workflow_guard`. Nếu công việc đã được nhận hoặc chưa đến tiến trình cho phép, hành động sẽ bị từ chối ngay lập tức.
2. **Thông tin bàn giao phải có truy vết nguồn gốc**: Trường `Handoff.facts` bắt buộc phải đi kèm thông tin ID tham chiếu `artifact_refs`. Mọi khẳng định không có liên kết nguồn gốc sẽ bị coi là không hợp lệ.
3. **Presence có hạn dùng**: Nếu heartbeat quá hạn ping, trạng thái node chuyển sang `dead` và công việc bị thu hồi ngay lập tức, tránh việc hệ thống giả định worker vẫn đang chạy bình thường.
4. **Workflow Guard**: Kiểm soát chặt chẽ tiến trình, không cho phép nhảy bước và yêu cầu xác thực tệp tin đầu ra (artifacts) trước khi chuyển bước.
5. **Graph làm bộ nhớ chung**: Mọi kết quả trung gian được cập nhật trực tiếp vào cơ sở dữ liệu graph/document chung giúp các agent kế thừa có thể truy vấn dữ liệu chuẩn xác qua `minder_search_graph` hoặc `minder_find_impact`.

---

## 8. Mở rộng Tập lệnh CLI Swarm

Bổ sung nhóm lệnh `minder swarm` phục vụ giám sát và điều phối thủ công từ terminal:

```bash
minder swarm create --workflow <id> --goal "..."   # Khởi tạo một swarm mới
minder swarm who <swarm_id>                        # Kiểm tra ai đang hoạt động ở đâu
minder swarm board <swarm_id>                      # Hiển thị bảng trạng thái công việc chi tiết
minder swarm approve <swarm_id>                    # Duyệt/từ chối/chỉnh sửa manifest
minder swarm board <swarm_id> --json               # Xuất cấu trúc trạng thái dạng JSON phục vụ scripting
```

---

## 9. Lộ trình Triển khai đã thực hiện

- **S-0**: Xây dựng thực thể `SwarmNode`, các công cụ kiểm tra hiện diện (`join`/`heartbeat`/`who`) kết hợp cơ sở dữ liệu độc lập `swarm.db`.
- **S-1**: Xây dựng bảng công việc `SwarmTask`, cơ chế nhận việc atomic, liên kết đồ thị DAG và báo cáo kết quả qua thực thể con trỏ `Handoff`.
- **S-2**: Kết nối bảng công việc với hệ thống workflow nghiệp vụ hiện có của Minder (phân rã workflow thành các DAG tasks).
- **S-2b**: Triển khai cổng phê duyệt: API `swarm_propose`, cấu trúc thực thể `SwarmManifest` và logic chặn cứng tiến trình tại tầng bộ chạy Runner.
- **S-3**: Xây dựng bộ đăng ký Runner Adapter và hai bộ chạy đầu tiên `ClaudeRunner`, `CodexRunner` (hỗ trợ pull-spawn).
- **S-4**: Phát triển bộ điều phối chạy ngầm `Dispatcher` tự động phân phối công việc theo gợi ý `runtime_hint`, dọn dẹp node chết và xử lý lỗi chạy.
- **S-5**: Phát triển bộ chạy `AcpRunner` (ACP client) hỗ trợ giao thức ACP và tiến hành thử nghiệm kết nối với Antigravity IDE & Claude Code.
- **HƯỚNG DẪN**: Viết tài liệu hướng dẫn chi tiết từng bước cấu hình tại tệp tin `docs/guides/swarm-setup-claude-antigravity.md`.
- **CLI/OBS**: Hoàn thiện bộ lệnh CLI `minder swarm` và thiết kế các trang giám sát Swarm trên Dashboard.
