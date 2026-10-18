# 🔵 Crypto Bunny - Advanced Multi-Agent Signal & Trading Desk for OKX

Hệ thống bot phát tín hiệu và giao dịch tự động thế hệ mới trên sàn **OKX**, tích hợp **Mô hình Đa Tác Tử Đồng Thuận (Multi-Agent Consensus System)**, **Động cơ Nhận diện Mô hình Thị trường Độc lập (Market Pattern Engine)**, **Quy trình Quản lý Dòng Vốn Thích Ứng (LC Pipeline)** và **Cơ chế Tự Phục Hồi Tài Khoản (Account Recovery)**.

Mục tiêu cốt lõi của Crypto Bunny là phân tích sâu toàn bộ thị trường, sàng lọc hàng chục cặp coin tiềm năng và chỉ lựa chọn **tối đa 1 lệnh giao dịch chất lượng cao nhất (Highest Confluence Setup)** trong mỗi chu kỳ quét, giúp tối đa hóa tỷ lệ thắng và bảo toàn nguồn vốn dài hạn.

---

## 🖼️ Giao Diện Điều Hành (Advanced Operator Web Dashboard)

Crypto Bunny sở hữu giao diện bảng điều khiển hiện đại, hoạt động độc lập trên cổng **8013**, cho phép người vận hành quan sát toàn diện tình trạng bot và tùy biến tham số trực tiếp:

![Crypto Bunny Operator Dashboard](docs/images/dashboard.png)

### Các Khu Vực Chức Năng Trên Giao Diện:
1. **Header & Financial Overview Bar**:
   - **Tài sản khả dụng (Available Equity)**: Cập nhật trực tiếp số dư ví Trading USDT từ API sàn OKX.
   - **OKX API Handshake**: Đèn báo trạng thái kết nối và độ trễ WebSocket/REST API.
   - **Trading Mode**: Chuyển đổi linh hoạt giữa các chế độ: Dry-run (mô phỏng), Demo (sàn ảo OKX), hoặc Live (tiền thật).
   - **Đòn bẩy hiện tại (Current Leverage)**: Tỷ lệ đòn bẩy ký quỹ đang áp dụng.
2. **Strategy Configuration Panel (Bảng điều khiển chiến lược tương tác)**:
   - Cho phép người vận hành thay đổi trực tiếp trên UI mà không cần chỉnh sửa file YAML:
     - **Strategy Mode**: Chọn phong cách giao dịch (Conservative, Balanced, Aggressive).
     - **Risk Tolerance**: Ngưỡng chịu đựng rủi ro (% vốn phân bổ).
     - **Take Profit / Stop Loss Multipliers**: Hệ số chốt lời và cắt lỗ linh hoạt.
     - **Max Concurrent Positions**: Số vị thế tối đa được phép mở đồng thời (mặc định = 1 để an toàn tuyệt đối).
3. **OKX Positions & Orders Monitor**:
   - Theo dõi chi tiết vị thế đang mở trên sàn OKX: Cặp coin, hướng lệnh (Long/Short), Khối lượng, Giá vào (Entry), Giá đánh dấu (Mark Price), Lãi/Lỗ chưa chốt (Unrealized PnL), Tỷ lệ ký quỹ (Margin Ratio) và Giá thanh lý dự kiến (Liquidation Price).
4. **AI Decision & Signal Feed (Dòng nhận định AI thời gian thực)**:
   - Hiển thị kết quả biểu quyết từ bàn điều hành đa tác tử.
   - Bảng xếp hạng điểm số cơ hội của các cặp coin vừa quét kèm luận điểm chi tiết: Lý do chọn hoặc lý do từ chối.
5. **System Diagnostics & Health Status**:
   - Kiểm tra trạng thái các tiến trình nền: LC Pipeline State, Market Pattern Detector Health, Database Syncer và Telegram Notification Hook.

---

## 🚀 Các Tính Năng Cốt Lõi (Core Features)

### 1. Multi-Agent Consensus System (Hệ Thống Đa Tác Tử Đồng Thuận)
Crypto Bunny không phụ thuộc vào một chỉ báo đơn lẻ mà phối hợp 4 tác tử chuyên biệt:
- **Trend Agent**: Phân tích cấu trúc sóng, đường trung bình động và chỉ báo xu hướng.
- **Volatility Scout**: Đo lường biên độ biến động Bollinger Bands và ATR để xác định độ nén giá.
- **Sentiment & News Agent**: Quét tin tức và dữ liệu tâm lý thị trường để phát hiện rủi ro vĩ mô.
- **Risk Guardian Agent**: Đóng vai trò chốt chặn cuối cùng, đánh giá rủi ro danh mục và tỷ lệ ký quỹ trước khi cấp quyền mở lệnh.
- Quyết định vào lệnh chỉ được thông qua khi đạt được điểm số đồng thuận (**Consensus Score**) vượt ngưỡng quy định.

### 2. Market Pattern Engine Độc Lập (SMC & Pattern Recognition)
Thư viện con market_pattern_engine tích hợp sẵn khả năng nhận diện các mô hình kỹ thuật cao cấp:
- **Smart Money Concepts (SMC)**:
  - Khối lệnh tổ chức (**Order Blocks - OB**).
  - Vùng mất cân bằng giá (**Fair Value Gaps - FVG**).
  - Phá vỡ cấu trúc (**Break of Structure - BOS**) và Thay đổi tính chất thị trường (**Change of Character - CHoCH**).
  - Quét thanh khoản đỉnh/đáy (**Liquidity Sweeps**).
- **Mô hình nến & Biểu đồ cổ điển**: Engulfing, Hammer, Morning/Evening Star, Double Top/Bottom, Triangles, Wedges.

### 3. LC Pipeline & Account Recovery (Tự Phục Hồi Tài Khoản)
- **Cơ chế phân bổ vốn thích ứng**: Tự động tính toán khối lượng lệnh dựa trên chuỗi lệnh thắng/thua gần nhất.
- **Account Recovery Mode**: Nếu tài khoản gặp phải chuỗi sụt giảm (Drawdown), thuật toán tự động giảm quy mô vị thế, thắt chặt điều kiện vào lệnh và ưu tiên bảo toàn vốn cho đến khi tài khoản hồi phục về mức cân bằng.

### 4. Nguyên Tắc Tập Trung Nguồn Lực (Max 1 Trade Rule)
- Bot quét đồng thời hàng chục cặp coin nhưng chỉ lựa chọn duy nhất **1 cặp coin có điểm số cao nhất** để giải ngân vốn.
- Loại bỏ hoàn toàn rủi ro phân tán vốn, tránh tình trạng thị trường đảo chiều đồng loạt làm cháy nhiều vị thế cùng lúc.

### 5. Đa Chế Độ Khớp Lệnh
- **dry_run**: Chỉ phân tích thị trường, chấm điểm và ghi log báo cáo vào file 
eports/latest_decision.json, không tương tác với sàn.
- **demo**: Kết nối với tài khoản Demo Paper của sàn OKX qua API v5 để kiểm chứng lệnh với giá thị trường thực tế.
- **live**: Gửi lệnh trực tiếp vào sổ lệnh thật của OKX khi có đầy đủ quyền xác thực an toàn.

---

## 🏛️ Cấu Trúc Thư Mục Dự Án

`	ext
Crypto_Bunny/
├── config.demo.yaml            # Cấu hình chuẩn cho môi trường Demo OKX
├── config.example.yaml         # Mẫu cấu hình tham khảo đầy đủ
├── docs/
│   └── images/
│       └── dashboard.png       # Ảnh chụp Web UI Operator Dashboard
├── crypto_trader/
│   ├── active_position_manager.py # Giám sát và quản lý vị thế chủ động
│   ├── ai_coordinator.py       # Điều phối các tác tử AI và tổng hợp quyết định
│   ├── candles.py              # Xử lý và tính toán dữ liệu nến OHLCV
│   ├── capital.py              # Quản lý dòng vốn và phân bổ ký quỹ
│   ├── cli.py                  # Giao diện dòng lệnh CLI (analyze, trade, ui)
│   ├── engine.py               # Động cơ giao dịch trung tâm
│   ├── executor.py             # Khớp lệnh OKX REST V5 / WebSocket
│   ├── indicators.py           # Tính toán chỉ báo kỹ thuật cơ bản
│   ├── lc_pipeline.py          # Quy trình quản lý vốn thích ứng LC Pipeline
│   ├── market.py               # Kết nối API thị trường sàn OKX
│   ├── market_guard.py         # Các chốt chặn an toàn thị trường
│   ├── notifier.py             # Gửi thông báo Telegram
│   ├── sizing.py               # Tính toán khối lượng lệnh và đòn bẩy
│   ├── strategy.py             # Chiến lược tổng hợp đa tác tử
│   ├── ui.py                   # FastAPI Web Server phục vụ Operator Dashboard
│   └── static/                 # Giao diện Web HTML5, CSS3, JavaScript
├── market_pattern_engine/      # Module độc lập nhận diện mô hình kỹ thuật & SMC
│   ├── detectors/              # Bộ nhận diện nến, chart pattern, Smart Money Concepts
│   ├── services/               # Dịch vụ phân tích hợp lưu (confluence) và độ tin cậy
│   └── README.md               # Tài liệu chi tiết market_pattern_engine
├── requirements.txt            # Danh sách thư viện Python
└── README.md                   # Tài liệu chi tiết dự án
`

---

## ⚙️ Hướng Dẫn Cài Đặt & Cấu Hình

### 1. Chuẩn Bị Môi Trường
`powershell
cd C:\Users\Admin\Documents\crypto\Crypto_Bunny
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
`

### 2. Thiết Lập Biến Môi Trường (.env)
Tạo file .env từ .env.example:

`ini
# OKX API Credentials (Demo hoặc Live)
OKX_API_KEY=your_okx_api_key
OKX_API_SECRET=your_okx_api_secret
OKX_API_PASSPHRASE=your_okx_passphrase

# Telegram Notifications (Tùy chọn)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
`

### 3. Cấu Hình Chiến Lược (config.demo.yaml)
Sao chép từ config.example.yaml:
- Đặt nvironment: demo để chạy trên sàn OKX Demo ảo.
- Tinh chỉnh danh sách coin quét (symbols: [BTC-USDT, ETH-USDT, SOL-USDT, DOGE-USDT...]).
- Thiết lập giới hạn đòn bẩy (max_leverage: 3 hoặc 5).

---

## 🚦 Hướng Dẫn Vận Hành

### 1. Khởi Động Web Dashboard UI (Port 8013)
`powershell
cd C:\Users\Admin\Documents\crypto\Crypto_Bunny
.\.venv\Scripts\Activate.ps1
python -m crypto_trader ui --config config.demo.yaml --host 127.0.0.1 --port 8013
`
Mở trình duyệt tại: **http://localhost:8013** để tương tác với Dashboard.

### 2. Chạy Phân Tích Thủ Công (Không Đặt Lệnh)
`powershell
python -m crypto_trader analyze --config config.demo.yaml
`
Kết quả phân tích chi tiết sẽ được xuất ra màn hình console và lưu vào 
eports/latest_decision.json.

### 3. Chạy Một Chu Kỳ Giao Dịch Đầy Đủ
`powershell
python -m crypto_trader trade --config config.demo.yaml
`

---

## 🛡️ Khuyến Cáo An Toàn
- Luôn kiểm tra chế độ hiển thị trên Dashboard là **Demo/Dry-run** trước khi bật tự động quét.
- Không cấp quyền Rút tiền (Withdraw) cho bất kỳ API Key nào dùng cho bot giao dịch.\n