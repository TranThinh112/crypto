# 🟣 Future V2 - High-Safety Crypto Futures Multi-Agent Trading Desk

Hệ thống bot giao dịch tự động phái sinh (**Crypto Futures / Perpetual Swaps**) và giao ngay cấp độ doanh nghiệp trên sàn **OKX**, được thiết kế theo triết lý **An Toàn Là Trên Hết (Safety-First Architecture)**. Hệ thống tập trung tối ưu cho các cặp tài sản hàng đầu thị trường: **BTC-USDT** và **ETH-USDT**.

Future V2 kết hợp sức mạnh phân tích chuyên sâu của **Bàn Điều Hành Đa Tác Tử AI (Multi-Agent Consensus Desk)** với sự kỷ luật tuyệt đối của **Bộ Chốt Chặn Rủi Ro Xác Định (Deterministic Risk Guard)**: AI đóng vai trò phân tích và đề xuất luận điểm, nhưng quyền quyết định vào lệnh cuối cùng hoàn toàn thuộc về bộ quy tắc toán học không thể bị ghi đè.

---

## 🖼️ Giao Diện Điều Hành (Operator Web Dashboard)

Future V2 tích hợp bảng điều khiển vận hành thời gian thực chuyên nghiệp trên cổng **8014**, cung cấp góc nhìn toàn cảnh về chu trình phân tích tác tử, trạng thái worker loop và cơ chế ngắt khẩn cấp tức thời:

![Future V2 Operator Dashboard](docs/images/dashboard.png)

### Các Khu Vực Chức Năng Trên Giao Diện:
1. **System Bar & Trading Mode Indicator**:
   - **Phiên bản & Trạng thái**: Hiển thị phiên bản phần mềm, trạng thái kết nối sàn OKX và cổng API.
   - **Chế độ giao dịch**: Mặc định là Paper Mode (giao dịch mô phỏng an toàn tuyệt đối). Chế độ Live Mode được khóa chặt và chỉ mở khi thỏa mãn đầy đủ các điều kiện xác thực.
2. **Worker Loop Status (Bộ giám sát tiến trình nền)**:
   - Theo dõi chu kỳ quét tự động: Khung thời gian nến (15 phút / 1 giờ).
   - Thanh đếm ngược thời gian đóng nến tiếp theo (Next Candle Countdown).
   - Trạng thái vòng lặp Paper Trading Engine: Đang chạy, tạm dừng, hoặc đang xử lý tín hiệu.
3. **Multi-Agent Consensus Desk (Bàn điều hành đồng thuận đa tác tử)**:
   - Hiển thị trực quan điểm số đánh giá và khuyến nghị từ 4 tác tử AI độc lập:
     - **Technical Agent**: Phân tích hành động giá (Price Action), hỗ trợ/kháng cự và cấu trúc nến.
     - **Momentum Agent**: Đo lường gia tốc xung lực (RSI, MACD, Stochastic).
     - **Risk Agent**: Đo lường độ sâu thanh khoản, khoảng cách giá thanh lý và tỷ lệ đòn bẩy an toàn.
     - **News & Sentiment Agent**: Phân tích tin tức vĩ mô và chỉ số tâm lý thị trường (Fear & Greed Index).
   - Điểm số đồng thuận chung (**Consensus Decision**): BUY, SELL hoặc HOLD.
4. **Emergency Kill Switch (Nút ngắt khẩn cấp)**:
   - Nút điều khiển màu đỏ nổi bật cho phép người vận hành can thiệp lập tức:
     - Dừng toàn bộ tiến trình quét và vào lệnh mới.
     - Tự động gửi lệnh thị trường (Market Order) đóng sạch toàn bộ vị thế đang mở trên sàn.
     - Hủy tất cả các lệnh chờ (Limit/Stop orders) để bảo toàn số dư tài khoản khi thị trường xuất hiện sự kiện thiên nga đen (Black Swan).
5. **Trade Events & Audit Log Stream (Nhật ký sự kiện kiểm toán)**:
   - Bảng theo dõi chi tiết từng sự kiện theo thời gian thực: Thời điểm (Timestamp), Cặp giao dịch (Pair), Hành động (Action), Điểm số rủi ro (Risk Score), Ký quỹ sử dụng (Margin), và Lý do ra quyết định hoặc lý do bị Risk Guard từ chối.

---

## 🚀 Các Tính Năng Cốt Lõi (Core Features)

### 1. Bàn Điều Hành Đa Tác Tử (Multi-Agent Consensus Architecture)
- Thay vì sử dụng một mô hình AI duy nhất dễ bị thiên kiến hoặc ảo giác (hallucination), Future V2 phân tách nhiệm vụ cho 4 tác tử chuyên biệt:
  - Tác tử Kỹ thuật (Technical).
  - Tác tử Động lượng (Momentum).
  - Tác tử Quản trị Rủi ro (Risk).
  - Tác tử Tin tức & Tâm lý (News/Sentiment).
- Các tác tử đưa ra đánh giá độc lập kèm trọng số biểu quyết. Chỉ khi các tác tử đạt được sự đồng thuận cao (Consensus Threshold), đề xuất giao dịch mới được chuyển tới lớp thẩm định rủi ro.

### 2. Bộ Chốt Chặn Rủi Ro Toán Học Xác Định (Deterministic Risk Guard)
- **AI không có quyền quyết định cuối cùng**: Dù tất cả tác tử AI đều đề xuất mở vị thế, lệnh vẫn bị hủy bỏ ngay lập tức nếu vi phạm bất kỳ quy tắc nào trong bộ quy tắc toán học cố định:
  - **Max Position Sizing**: Giới hạn tối đa quy mô một vị thế tính theo % vốn ròng.
  - **Max Account Leverage**: Khống chế đòn bẩy tối đa (ví dụ: tối đa 2x - 3x cho Futures).
  - **Liquidation Buffer**: Khoảng cách từ giá vào lệnh tới giá thanh lý ước tính bắt buộc phải vượt qua ngưỡng an toàn tối thiểu (ví dụ: >= 25%).
  - **Daily Loss Ceiling**: Tự động phong tỏa giao dịch nếu mức thua lỗ trong ngày chạm ngưỡng trần thiết lập.

### 3. Worker Loop Tự Động Định Kỳ (15m / 1H Cadence)
- Tiến trình nền paper_worker.py đồng bộ nến đã đóng từ OKX API, ngăn chặn hoàn toàn lỗi tín hiệu giả khi nến chưa kết thúc.
- Quản lý trạng thái vị thế liên tục, tự động dời trailing stop và kiểm tra điều kiện chốt lời/cắt lỗ theo thời gian thực.

### 4. Backtest Engine Tích Hợp (Không Look-Ahead Bias)
- Mô phỏng kiểm thử chiến lược trên dữ liệu lịch sử chuẩn xác:
  - Tính toán phí giao dịch Maker/Taker thực tế của OKX.
  - Mô phỏng phí cấp vốn (Funding Rate) định kỳ 8 tiếng/lần của hợp đồng vĩnh viễn (Perpetual Swap).
  - Mô phỏng độ trượt giá (Slippage) và khớp lệnh từng phần (Partial Fills).
  - Báo cáo chi tiết các chỉ số định lượng: Sharpe Ratio, Sortino Ratio, Max Drawdown, Win Rate, Profit Factor.

### 5. Kiến Trúc Microservices Sẵn Sàng Doanh Nghiệp
- Hỗ trợ lưu trữ bền vững với **PostgreSQL** (lưu trữ audit trail, lịch sử lệnh, trạng thái giao dịch) và **Redis** (hàng đợi tác vụ và cache dữ liệu thị trường tốc độ cao).
- Tích hợp file cấu hình docker-compose.yml giúp triển khai nhanh chóng toàn bộ hạ tầng chỉ với một câu lệnh.

---

## 🏛️ Cấu Trúc Thư Mục Dự Án

`	ext
Future_V2/
├── app/
│   ├── agents/                 # Các tác tử AI: Technical, Momentum, Risk, News, OpenAI adapter
│   ├── alerts/                 # Hệ thống cảnh báo Webhook & Telegram
│   ├── api/                    # FastAPI endpoints (Dashboard UI, Metrics, Control)
│   ├── consensus/              # Động cơ tổng hợp biểu quyết đồng thuận (Consensus Engine)
│   ├── execution/              # Động cơ khớp lệnh: Paper, Demo, Live, Reconcile, Guards
│   ├── features/               # Tính toán các chỉ báo kỹ thuật định lượng
│   ├── market_data/            # Kết nối OKX REST API, WebSocket, Orderbook L2
│   ├── news/                   # Thu thập và chuẩn hóa dữ liệu tin tức thị trường
│   ├── risk/                   # Deterministic Risk Engine & Quản lý trạng thái rủi ro
│   ├── storage/                # SQLAlchemy models, PostgreSQL repository, Migrations
│   ├── config.py               # Cấu hình hệ thống Pydantic Settings
│   ├── orchestrator.py         # Bộ điều phối luồng xử lý toàn cục
│   ├── paper_worker.py         # Tiến trình nền Worker chạy chu kỳ nến
│   ├── pipeline.py             # Pipeline xử lý dữ liệu và luân chuyển tín hiệu
│   └── strategy.py             # Chiến lược giao dịch cấp cao
├── backtests/                  # Động cơ Backtesting và phân tích hiệu suất
├── docs/                       # Tài liệu kiến trúc, bảo mật và hướng dẫn vận hành chi tiết
│   └── images/
│       └── dashboard.png       # Ảnh chụp Web UI Operator Dashboard
├── migrations/                 # Script khởi tạo cơ sở dữ liệu SQL (001_init.sql)
├── docker-compose.yml          # Hạ tầng container (PostgreSQL + Redis)
├── pyproject.toml              # Cấu hình dự án và dependencies
├── requirements.txt            # Danh sách thư viện Python
└── README.md                   # Tài liệu chi tiết dự án
`

---

## ⚙️ Hướng Dẫn Cài Đặt & Cấu Hình

### 1. Chuẩn Bị Môi Trường
`powershell
cd C:\Users\Admin\Documents\crypto\Future_V2
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
`

### 2. Khởi Động Hạ Tầng Cơ Sở Dữ Liệu (Docker Compose - Tùy chọn)
Nếu muốn sử dụng PostgreSQL và Redis để lưu trữ toàn bộ audit log:
`powershell
docker compose up -d postgres redis
python -m app.storage.migrate
`
*(Nếu không dùng Docker, hệ thống tự động lưu trạng thái vào file JSON cục bộ paper_state.json và cơ sở dữ liệu SQLite).*

### 3. Thiết Lập Biến Môi Trường (.env)
Tạo file .env từ .env.example:

`ini
# Chế độ giao dịch: paper hoặc live
TRADING_MODE=paper
ENABLE_LIVE_TRADING=false

# Cặp giao dịch hỗ trợ
SUPPORTED_SYMBOLS=BTC-USDT,ETH-USDT

# Khóa API sàn OKX
OKX_API_KEY=your_okx_api_key
OKX_API_SECRET=your_okx_api_secret
OKX_API_PASSPHRASE=your_okx_passphrase

# Trí tuệ nhân tạo (OpenAI API)
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4o-mini

# Cấu hình Cổng Web Dashboard
PORT=8014
HOST=0.0.0.0
`

---

## 🚦 Hướng Dẫn Vận Hành

### 1. Khởi Động Web Dashboard (Port 8014)
`powershell
cd C:\Users\Admin\Documents\crypto\Future_V2
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.api.main:app --host 0.0.0.0 --port 8014 --reload
`
Mở trình duyệt tại: **http://localhost:8014/dashboard** để truy cập Operator Dashboard.

### 2. Khởi Động Paper Trading Worker Loop
Để bot tự động quét và phân tích theo chu kỳ nến M15/H1 trong nền:
`powershell
python -m app.paper_worker
`

### 3. Chạy Kiểm Thử Toàn Diện (Test Suite & Backtest)
`powershell
pytest
`
Hoặc chạy riêng kiểm thử Backtest engine:
`powershell
pytest tests/test_backtest.py -v
`

---

## 🛡️ Chốt Chặn Kích Hoạt Chế Độ Live (Live Trading Safeguards)
Chế độ giao dịch tiền thật (TRADING_MODE=live) được bảo vệ bằng cơ chế xác thực kép:
1. File .env phải có đồng thời TRADING_MODE=live và ENABLE_LIVE_TRADING=true.
2. Khóa API OKX phải hợp lệ và chỉ có quyền Trade (tuyệt đối không cấp quyền Withdraw).
3. Ứng dụng tự động kiểm tra tính hợp lệ lúc khởi động; nếu phát hiện bất kỳ thông số nào không an toàn, bot sẽ từ chối khởi chạy và lập tức dừng tiến trình.\n