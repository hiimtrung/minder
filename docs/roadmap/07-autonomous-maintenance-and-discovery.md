# 07. Tự động Bảo trì & Tự động Khám phá Công cụ/Kỹ năng

> **Trạng thái:** KẾ HOẠCH (chưa triển khai) · **Ngày:** 2026-06-18
> **Mục tiêu:** Tích hợp cơ chế tự động khám phá công cụ/kỹ năng/plugin thông minh của Hermes Agent vào **LLM agent chạy cục bộ Qwen** của Minder, đồng thời bổ sung một **trình lập lịch tự dọn dẹp và tối ưu dữ liệu theo chu kỳ khi người dùng không sử dụng** (Minder hiện chưa có tính năng này, Hermes có qua thư mục `cron/`).

Tài liệu này trình bày kế hoạch gồm hai phần độc lập nhưng bổ trợ cho nhau:

- **Phần A — Trí tuệ Tự động Khám phá cho Qwen (Auto-Discovery Intelligence)**: Kế thừa từ Hermes cơ chế tự khám phá (registry discovery), vòng lặp tự cải tiến (curator self-improving loop) và khám phá trì hoãn (deferred discovery).
- **Phần B — Trình lập lịch Bảo trì khi máy rảnh (Idle Maintenance Scheduler)**: Kế thừa ý tưởng từ `hermes/cron/` (jobs.json, vòng lặp tick(), khóa tệp tin), nhưng được tối giản hóa cho phù hợp với 1 tiến trình chạy native và bổ sung cơ chế kích hoạt khi rảnh (idle-trigger).

---

## 0. Bối cảnh — Minder đã có gì, thiếu gì

Đối chiếu nhanh với Hermes để tránh phát triển lại những gì đã có:

| Năng lực | Hermes | Minder (hiện tại) | Khoảng trống cần bù đắp |
| :--- | :--- | :--- | :--- |
| **Đăng ký công cụ (Single source of truth)** | `tools/registry.py` + auto-`register()` | `domain/value_objects.py` (`ALL_TOOLS`, `TOOL_DESCRIPTIONS`, `TOOL_USAGE_PATTERNS`, `tool_capability_manifest()`) | Đã có — chỉ cần chuyển sang cơ chế tự khám phá thay vì danh sách tĩnh |
| **Công cụ trì hoãn / Luôn sẵn sàng** | `always_available`, deferred discovery | `ALWAYS_AVAILABLE_FOR_CLIENTS`, `minder_session_boot` | Đã có (xem chi tiết tại cải tiến LLM UX) |
| **Vòng lặp tự cải tiến kỹ năng (Self-improving skill loop)** | `agent/curator.py` (vòng đời kỹ năng) | `learning/skill_synthesizer.py`, `error_learner.py`, `pattern_extractor.py`, `quality_optimizer.py` | Đã có **các thành phần cốt lõi** — thiếu **lớp điều phối (curator)** gọi chúng định kỳ |
| **Hệ thống Plugin** | `plugins/` (quản lý bộ nhớ/mẫu LLM...) | `llm/factory.py`, `store/*` dựa trên nhà cung cấp (provider-based) | Đã có mô hình nhà cung cấp, chưa có cơ chế tự động nạp plugin |
| **Trình lập lịch (Cron / Scheduler)** | `cron/scheduler.py` (`tick()` mỗi 60 giây) | **KHÔNG CÓ** | **Phần B xây mới** |
| **Bảo trì khi máy rảnh (Idle-time maintenance)** | Chạy trong cổng kết nối (gateway) | Có `context_compactor`, `memory_compact`, `admin prune` nhưng đang gọi thủ công | Thiếu cơ chế tự động kích hoạt |

**Kết luận:** Minder đã có gần đầy đủ "nguyên liệu". Việc cần làm là:
1. Xây dựng một **lớp điều phối (Curator)** để liên kết các thành phần học máy rời rạc thành một vòng tự cải tiến.
2. Xây dựng một **trình lập lịch (Scheduler)** kích hoạt vòng cải tiến đó cùng các tác vụ dọn dẹp khi hệ thống ở trạng thái rảnh. Chúng ta không cần mang nguyên tệp tin `cron/scheduler.py` nặng 95KB của Hermes sang (vì nó chứa nhiều logic phân tán/đa tiến trình không cần thiết cho Minder).

---

## Phần A — Trí tuệ Tự động Khám phá cho Qwen (Auto-Discovery)

### A1. Vấn đề cần giải quyết

Qwen chạy cục bộ (local qua llama.cpp với ngữ cảnh ngắn hơn các mô hình đám mây) dễ gặp hai lỗi lớn mà Hermes đã giải quyết:

1. **Tool blindness (Mù công cụ)**: Agent không biết công cụ nào tồn tại hoặc khi nào cần dùng. (Đã được cải thiện một phần nhờ `minder_session_boot` và gợi ý `_next_steps`).
2. **Không học từ kinh nghiệm**: Các mô-đun trong thư mục `learning/` đã có sẵn nhưng **chưa được tự động kích hoạt**.

### A2. Thiết kế — Ba lớp thông minh

```
┌─ Lớp Khám phá (Discovery Layer) ───────────────────────────┐
│  tool_capability_manifest()  +  TOOL_USAGE_PATTERNS         │  ← Đã có sẵn
│  → Đưa vào system prompt của Qwen như một "bản đồ năng lực" │
│  → Trì hoãn: Chỉ phơi bày ALWAYS_AVAILABLE, phần còn lại    │
│    sẽ hiển thị dần theo ngữ cảnh                            │
└────────────────────────────────────────────────────────────┘
            ↓ (Tự động kích hoạt sau mỗi phiên làm việc phức tạp)
┌─ Lớp Điều phối (Curator Layer) (MỚI: application/curator/service.py) ─┐
│  Điều phối các mô-đun học máy (learning/) sẵn có:          │
│   pattern_extractor → skill_synthesizer → quality_optimizer │
│   error_learner (rút ra luật sửa đổi từ các lỗi lặp lại)    │
│  Quyết định: Tạo kỹ năng mới? Cập nhật kỹ năng cũ? Loại bỏ? │
└────────────────────────────────────────────────────────────┘
            ↓ (Định kỳ, được Phần B kích hoạt)
┌─ Lớp Phản hồi (Reflection Layer) (Qwen tự đánh giá) ──────┐
│  Sử dụng chính Qwen (llm/factory) để đánh giá chất lượng   │
│  kỹ năng, gắn nhãn, viết lại mô tả giúp việc tìm kiếm      │
│  dễ dàng hơn ở các phiên làm việc sau                       │
└────────────────────────────────────────────────────────────┘
```

### A3. Các tác vụ triển khai cụ thể (Cấp độ tệp tin)

1. **Tạo tệp mới `application/curator/service.py`** — Lớp `SkillCurator`:
   - `async def curate_after_session(session_id)`: Gọi `PatternExtractor` → nếu phát hiện mẫu đủ mạnh → thực thi `SkillSynthesizer.synthesize()` → tối ưu hóa qua `QualityOptimizer`.
     **Quan trọng**: Kỹ năng mới sinh ra **KHÔNG** chuyển sang trạng thái hoạt động (`active`) ngay. Nó được lưu ở trạng thái **`pending_review`** (chờ duyệt) kèm theo một đề xuất đánh giá chi tiết (xem phần A5) để người dùng duyệt.
   - `async def reap()`: Quét các kỹ năng tự động tổng hợp (`auto_synthesized`) ít sử dụng hoặc có điểm đánh giá thấp → đề xuất lưu trữ (archive). (Cần sự đồng ý của người dùng nếu kỹ năng đang ở trạng thái `active`; tự động lưu trữ các kỹ năng ở trạng thái `pending_review` nếu quá hạn duyệt).
   - Tái sử dụng `IOperationalStore` (tham số đã có của `SkillSynthesizer`).
2. **Cập nhật `tools/skills.py`**:
   - Bổ sung công cụ `minder_skill_curate` (dành cho quản trị viên/nội bộ, cấu hình `always_available=False`) phục vụ kích hoạt thủ công và gọi từ scheduler.
   - Bổ sung công cụ `minder_skill_review(action="approve|reject|edit", skill_id, ...)` để quản lý luồng duyệt kỹ năng.
   - **Các kỹ năng chờ duyệt (`pending_review`) sẽ không hiển thị cho agent** qua `minder_skill_recall` — chỉ những kỹ năng đã được duyệt (`approved` hoặc `active`) mới có thể được agent sử dụng.
3. **Cơ chế Khám phá (Discovery) cho Qwen** (trong lớp xây dựng system prompt của agent):
   - Chèn kết quả từ `tool_capability_manifest()` cùng top-N kỹ năng liên quan nhất (thông qua `skill_recall`).
   - Đối với Qwen có ngữ cảnh ngắn: Ưu tiên cơ chế **trì hoãn (deferred)** — chỉ liệt kê các công cụ luôn sẵn sàng (`always-available`) và các kỹ năng liên quan trực tiếp, kèm theo thông báo: "Gọi `minder_session_boot` để kích hoạt các công cụ còn lại".
4. **Đăng ký tự động khám phá nhẹ (Registry auto-discovery)**:
   - Giữ nguyên `value_objects.ALL_TOOLS` làm nguồn cấu hình chính.
   - Bổ sung tệp `tools/__init__.py` để tự động quét các mô-đun trong thư mục `tools/*.py`, từ đó đưa ra cảnh báo nếu có sự sai lệch giữa handler thực tế và thông tin khai báo (tương tự như `register()` của Hermes nhưng ở dạng kiểm tra tĩnh thay vì thay đổi động lúc runtime).

### A4. Ràng buộc đối với Qwen chạy cục bộ (Local Qwen)

- **Ngân sách mã nguồn (Token budget)**: Mô tả của manifest và kỹ năng phải ngắn gọn để phù hợp với giới hạn ngữ cảnh nhỏ của Qwen. Đặt ngưỡng ký tự và cắt giảm nội dung dựa trên điểm số liên quan.
- **Quá trình đánh giá (Reflection) chạy nền**: Các tác vụ gọi LLM phục vụ cải tiến kỹ năng sẽ được đưa vào hàng đợi của Scheduler chạy ngầm (Phần B), đảm bảo không ảnh hưởng đến tốc độ phản hồi của người dùng.
- **Ưu tiên offline (Offline-first)**: Hoàn toàn không phụ thuộc vào kết nối API bên ngoài, sử dụng chính trình khởi tạo `llm/factory.create_llm()` hiện có.

### A5. Cơ chế Phê duyệt Kỹ năng (Human-in-the-loop)

> **Quyết định chốt:** Các kỹ năng được tự động tổng hợp **bắt buộc phải được người dùng phê duyệt trước khi đưa vào sử dụng**, hệ thống sẽ cung cấp một **Thẻ Đánh giá (Review Card)** đi kèm các chỉ số đề xuất để người dùng có thể ra quyết định nhanh chóng mà không cần đọc toàn bộ mã nguồn.

Vòng đời của kỹ năng có thêm các trạng thái phê duyệt như sau:

```
tổng hợp → [pending_review] ──duyệt (approve)────────▶ [active]   ← Agent bắt đầu sử dụng qua recall
                    │            ──chỉnh sửa (edit)──────▶ [active] (Lưu phiên bản đã chỉnh sửa)
                    │            ──từ chối (reject)──────▶ [rejected] (Lưu lại để học máy, không sử dụng)
                    └── quá hạn N ngày không duyệt ──────▶ Tự động lưu trữ (archive)
```

Mỗi kỹ năng ở trạng thái `pending_review` sẽ đi kèm một **Review Card** (được tạo bởi `QualityOptimizer` kết hợp gọi LLM chạy nền):

```python
# domain/entities/skill_review.py (MỚI)
class SkillReviewProposal:
    skill_id: str
    title: str
    proposed_content: str
    source_pattern: str          # Trích xuất từ phiên làm việc/quy trình nào để dễ truy vết
    evidence: list[str]          # Danh sách session_id/run tạo ra mẫu này
    scores: dict                 # Điểm số đề xuất: {"reuse_potential": .., "novelty": .., "risk": ..} (từ 0..1)
    near_duplicates: list[str]   # Các kỹ năng tương đồng đã tồn tại nhằm tránh trùng lặp
    recommendation: str          # Khuyến nghị: "approve" | "edit" | "reject" kèm lý do (1-2 câu)
```

- **Khuyến nghị (Recommendation)**: Tóm tắt nhanh từ LLM "Nên duyệt vì..." hoặc "Rủi ro nằm ở...".
- **Điểm số (Scores)**: Điểm số về khả năng tái sử dụng / tính mới mẻ / mức độ rủi ro giúp người dùng đánh giá nhanh.
- **Truy vết nguồn gốc (Evidence)**: Liên kết trực tiếp tới phiên làm việc/quy trình gốc để người dùng kiểm chứng thông tin khi cần.

**Giao diện người dùng (UI)**: Thêm một hàng đợi duyệt tại Dashboard (`src/dashboard/src/pages/skills/` — trang quản lý kỹ năng hiện có) hiển thị Review Card cùng các nút hành động **Approve / Edit / Reject**. Công cụ `minder_skill_review` sẽ là cổng giao tiếp chung cho cả Dashboard lẫn CLI quản trị.

---

## Phần B — Trình lập lịch Bảo trì khi máy rảnh (Idle Maintenance Scheduler)

### B1. Yêu cầu hệ thống

Hệ thống cần tự động lập lịch dọn dẹp, tối ưu hóa dữ liệu định kỳ khi máy ở trạng thái rảnh (người dùng không thực hiện thao tác nào).
Ba yếu tố cốt lõi: **(a) Chạy định kỳ**, **(b) Chỉ chạy khi rảnh (idle)**, và **(c) Thực hiện tối ưu/dọn dẹp dữ liệu**.

### B2. Kiến trúc hệ thống — Tối giản từ `hermes/cron`

Hermes sử dụng cơ chế gọi `tick()` mỗi 60 giây chạy trên một tiến trình ngầm riêng của gateway kết hợp khóa tệp tin (file-lock).
Do Minder chạy hoàn toàn trên một tiến trình FastAPI duy nhất, chúng ta có thể thiết kế đơn giản hơn: Sử dụng một tác vụ ngầm chạy bất tuần tự (`asyncio.create_task`) được đăng ký trong sự kiện khởi động (`lifespan`) của `server.py` (tương tự như pattern `_watch_parent_process()` hiện tại).

```
server.py  _async_run()
    └─ asyncio.create_task(MaintenanceScheduler(store, llm, config).run())
                                    │
        ┌──────────────────────────┴───────────────────────────┐
        │  Vòng lặp kiểm tra định kỳ (mặc định mỗi 60 giây):    │
        │   1. Cập nhật last_activity (qua middleware HTTP/MCP) │
        │   2. Nếu (now - last_activity) > idle_threshold:      │
        │        Tìm các tác vụ đến hạn chạy (cron biểu thức)    │
        │        → Thực thi TUẦN TỰ, mỗi tác vụ có giới hạn time │
        │   3. Ghi kết quả chạy vào bảng maintenance_runs       │
        └──────────────────────────────────────────────────────┘
```

### B3. Mô hình Tác vụ (Job Model)

Lịch trình và trạng thái các tác vụ bảo trì được lưu trực tiếp trong cơ sở dữ liệu **SQLite** (relational store hiện có) thay vì tệp cấu hình tĩnh `jobs.json` như Hermes, giúp dễ dàng truy vấn và quản lý trực tiếp từ Dashboard.

```python
# domain/entities/maintenance_job.py (MỚI)
class MaintenanceJob:
    id: str
    name: str                 # Tên tác vụ: "vector_compaction", "memory_dedupe", ...
    schedule: str             # Biểu thức cron (croniter) hoặc định dạng ngắn "every 6h"
    enabled: bool             # Trạng thái kích hoạt
    require_idle: bool = True  # Chỉ chạy khi người dùng rảnh
    max_runtime_s: int        # Ngân sách thời gian tối đa để tránh treo hệ thống
    last_run_at: datetime
    last_status: str
    last_summary: str
```

### B4. Các tác vụ khởi điểm (Tái sử dụng mã nguồn có sẵn — không viết mới logic dọn dẹp)

Chúng ta bọc các hàm chức năng dọn dẹp đã tồn tại trong hệ thống thành các adapter tác vụ để giảm thiểu rủi ro:

| Tác vụ (Job) | Gọi vào đâu (Hàm đã tồn tại) | Tác dụng |
| :--- | :--- | :--- |
| `memory_dedupe` | `application/memory/service.py::minder_memory_compact` | Tìm kiếm và hợp nhất các mảnh ký ức trùng lặp hoặc tương đồng |
| `chat_history_compact` | `application/context_compactor.py::compact` | Rút gọn lịch sử hội thoại cũ để giảm tải kích thước ngữ cảnh |
| `vector_optimize` | `store/turbovec/*` (rebuild/quantize index `vectors.tvim`) | Nén và tối ưu chỉ mục tìm kiếm vector Turbovec, tăng tốc độ truy vấn |
| `sqlite_vacuum` | `PRAGMA wal_checkpoint(TRUNCATE)` + `VACUUM` qua `store/relational.py` | Thu hồi dung lượng ổ đĩa trống từ SQLite, dọn dẹp tệp nhật ký ghi trước (WAL) |
| `graph_prune` | `application/admin/use_cases.py` (hàm dọn dẹp node mồ côi dòng ~1080) | Loại bỏ các nút liên kết bị hỏng do tệp tin đã đổi tên hoặc bị xóa |
| `skill_curate` | **Phần A** `SkillCurator.curate/reap` | Tổng hợp kỹ năng mới từ lịch sử hoạt động và tự động lưu trữ các kỹ năng rác |
| `error_rules_refresh` | `learning/error_learner.py` | Phân tích và rút ra các quy tắc sửa lỗi tự động từ lịch sử lỗi của hệ thống |

### B5. Phát hiện trạng thái rảnh (Idle Detection)

- Một middleware (được đăng ký song song với middleware xác thực) sẽ gọi hàm `scheduler.touch()` để cập nhật thời điểm hoạt động cuối cùng của người dùng khi có bất kỳ yêu cầu MCP/HTTP nào được gửi đến.
- Ngưỡng rảnh mặc định được chốt là **10 phút** (`idle_threshold_seconds = 600`). Tham số này có thể tùy chỉnh dễ dàng qua tệp cấu hình `minder.toml` hoặc giao diện Dashboard.
- Cơ chế bảo vệ phiên làm việc (`active-session guard`) đảm bảo hệ thống không bao giờ thực thi tác vụ dọn dẹp khi đang có một phiên tương tác LLM hoạt động chạy ngầm.

### B6. Thiết kế an toàn & Chuyển đổi chế độ hoạt động (Report → Active)

- **Mọi tác vụ phải có tính lũy đẳng (Idempotent)** và được giám sát thời gian chạy nghiêm ngặt thông qua cấu hình `max_runtime_s`; nếu quá hạn sẽ tự động hủy tác vụ và ghi nhận log `timeout`.
- **Khóa tuần tự (Sequential lock)**: Đảm bảo các tác vụ chạy nối tiếp nhau, không có hai tác vụ cùng truy cập hoặc thay đổi cơ sở dữ liệu một lúc.
- **Chế độ hoạt động cấu hình qua `minder.toml` (`mode = "report" | "active"`)**:
  - `report` (Mặc định khi bắt đầu cài đặt): Chỉ chạy thử nghiệm và ghi nhận báo cáo "Hệ thống dự kiến sẽ tối ưu/xóa những gì" vào bảng lịch sử chạy, **hoàn toàn không đụng vào dữ liệu thực tế**.
  - `active`: Thực thi dọn dẹp dữ liệu thực tế.
- **Tự động chuyển chế độ khi rảnh lâu (Auto-active)**: Khi hệ thống ở trạng thái rảnh liên tục trong **3 giờ trở lên**, Scheduler sẽ tự động nâng chế độ từ `report` lên `active` duy nhất cho chu kỳ bảo trì đó để dọn dẹp dữ liệu lúc người dùng chắc chắn không ngồi máy làm việc. Hết chu kỳ hoặc ngay khi người dùng hoạt động trở lại, chế độ sẽ được trả về `report`. Người dùng có thể tắt tính năng này bằng cách cấu hình tham số `auto_active_after_idle_hours = 0` (luôn chạy thủ công).
- **Sao lưu an toàn**: Tự động sao lưu các tệp chỉ mục vector hoặc tệp SQLite trước khi thực hiện các tác vụ tối ưu hóa chuyên sâu như `vacuum` hoặc `rebuild index`.

### B7. Cấu hình Tham chiếu (`minder.toml` + `config.py`)

```toml
[maintenance]
enabled = true
mode = "report"                  # report | active (chế độ chạy thử nghiệm/chạy thật)
tick_seconds = 60
idle_threshold_seconds = 600     # 10 phút không thao tác được coi là rảnh
auto_active_after_idle_hours = 3 # Rảnh liên tục >= 3 giờ sẽ tự động chạy thật; 0 để tắt
dashboard_editable = true        # Cho phép chỉnh sửa lịch tác vụ trực tiếp từ Dashboard

[[maintenance.jobs]]
name = "sqlite_vacuum"
schedule = "0 4 * * *"           # Chạy lúc 4 giờ sáng hàng ngày
require_idle = true
max_runtime_s = 120
```

Các tham số này sẽ được ánh xạ vào lớp cấu hình `MaintenanceConfig` tương ứng trong mã nguồn `src/minder/config.py`.

### B8. Quan sát & Điều khiển từ Dashboard

- Xây dựng trang quản lý mới tại **`src/dashboard/src/pages/maintenance/`**: Hiển thị danh sách các tác vụ kèm thông tin lịch chạy (`schedule`), trạng thái kích hoạt (`enabled`), yêu cầu rảnh (`require_idle`), ngân sách thời gian (`max_runtime_s`), cùng các nút hành động nhanh như **Run now / Pause / Edit schedule**.
- Bảng lịch sử chạy `maintenance_runs` hiển thị chi tiết kết quả chạy gần nhất của các tác vụ: Thời gian thực thi, kết quả, dung lượng đĩa thu hồi được, các kỹ năng mới được tạo ra và chế độ lúc chạy thực tế (`report` hay `active`).
- Xây dựng cổng API backend hỗ trợ hai công cụ `minder_maintenance_status` và `minder_maintenance_config` để agent hoặc dashboard có thể đọc/ghi cấu hình tác vụ dễ dàng.

---

## Lộ trình triển khai (Đề xuất)

| Phase | Nội dung công việc | Điều kiện trước | Rủi ro & Lưu ý |
| :--- | :--- | :--- | :--- |
| **B-0** | Khung sườn `MaintenanceScheduler` + Middleware phát hiện trạng thái rảnh (10 phút) + active-session guard + vòng lặp tick, chạy ở chế độ `mode=report` | — | Thấp |
| **B-1** | Triển khai 2 tác vụ dọn dẹp an toàn nhất: `sqlite_vacuum` và `chat_history_compact` (bọc mã nguồn đã có) | B-0 | Thấp |
| **DASH**| Xây dựng trang Dashboard `maintenance/` quản lý cấu hình lịch chạy tác vụ + tích hợp API `minder_maintenance_config` (Làm sớm song song B-1) | B-0 | Thấp |
| **B-2** | Tích hợp các tác vụ: `vector_optimize`, `memory_dedupe`, `graph_prune` + cơ chế tự động sao lưu dự phòng + tự chuyển đổi active sau 3h rảnh liên tục | B-1 | Trung bình (cần kiểm tra kỹ cơ chế nén vector) |
| **A-1** | Phát triển bộ điều phối `SkillCurator` kết hợp các mô-đun học máy sẵn có; các kỹ năng mới tạo sẽ chuyển vào hàng chờ duyệt `pending_review` | — | Thấp |
| **A-1b**| Luồng phê duyệt kỹ năng: Phát triển thực thể `SkillReviewProposal` + API duyệt `minder_skill_review` + giao diện hàng chờ duyệt trên Dashboard | A-1 | Thấp |
| **A-2** | Cập nhật hệ thống prompt bổ trợ cho Qwen (giới hạn ngữ cảnh, chỉ recall các kỹ năng đã ở trạng thái `active`) | A-1 | Thấp |
| **B-3** | Tích hợp tác vụ `skill_curate` và `error_rules_refresh` vào Scheduler để tự động quét định kỳ (chỉ tạo đề xuất, không tự động duyệt kỹ năng) | A-1, B-1 | Thấp |
| **OBS** | Hoàn thiện trang Dashboard giám sát lịch sử chạy của các tác vụ bảo trì (`maintenance_runs`) | B-2 | — |

**Nguyên tắc triển khai**: Chỉ bọc ngoài các mã nguồn dọn dẹp sẵn có, chạy thử nghiệm báo cáo (`report`) trước khi chạy thực tế (`active`), giới hạn thời gian thực thi chặt chẽ, **kỹ năng mới luôn cần con người phê duyệt**, không sao chép nguyên khối phức tạp của Hermes mà chỉ học tập ý tưởng để xây dựng kiến trúc native chạy trên tiến trình đơn của Minder.

---

## Quyết định đã thống nhất (2026-06-18)

| # | Câu hỏi khảo sát | Quyết định chốt | Tài liệu thiết kế |
| :--- | :--- | :--- | :--- |
| 1 | Ngưỡng rảnh (Idle threshold) | **10 phút** không thao tác (có thể tùy chỉnh) | Mục B5, B7 |
| 2 | Kích hoạt chạy thật tự động | **Tự nâng lên chạy thật (active) nếu rảnh liên tục >= 3 giờ**; tắt bằng cách đặt `auto_active_after_idle_hours = 0` | Mục B6, B7 |
| 3 | Duyệt kỹ năng tự động | **Bắt buộc người duyệt.** Đi kèm **Review Card** (đề xuất + điểm số) để duyệt nhanh. Kỹ năng chưa duyệt sẽ bị ẩn với agent | Mục A3, A5 |
| 4 | Quản lý tác vụ từ Dashboard | **Cho phép chỉnh lịch và kích hoạt từ Dashboard ngay từ Phase đầu** (Phase `DASH` song song với Phase B-1) | Mục B7, B8 |
