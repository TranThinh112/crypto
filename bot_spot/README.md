# 🟢 Crypto Spot AI Trading Bot

Hệ thống bot giao dịch Crypto Spot tự động hóa toàn diện, kết hợp giữa mô hình **Trí tuệ nhân tạo (OpenAI GPT Advisor)**, **Động cơ phân tích định lượng theo quy tắc (Rule Strategy)**, **Hệ thống chốt chặn rủi ro đa tầng (Risk Guards)** và giao diện điều hành trực quan **Web Dashboard**.

Bot được thiết kế tối ưu hóa cho sàn **OKX** (hỗ trợ mở rộng Binance, Bybit qua CCXT), cung cấp cơ chế bảo vệ vốn nghiêm ngặt, cho phép chạy mô phỏng an toàn (Paper Trading) trước khi kích hoạt giao dịch thực tế (Live Execution).

---

## 🖼️ Giao Diện Điều Hành (Operator Web Dashboard)

Giao diện Web Dashboard được xây dựng tối giản, trực quan và hiện đại, giúp người vận hành theo dõi toàn bộ trạng thái tài khoản, luồng phân tích AI và các đề xuất vào lệnh theo thời gian thực:

![Crypto Spot AI Dashboard](docs/images/dashboard.png)

### Các Khu Vực Chức Năng Trên Giao Diện:
1. **Header & Status Bar**:
   - **Exchange Status**: Trạng thái kết nối trực tiếp tới sàn OKX (Live Account Verification, Private API handshake).
   - **AI Advisor Engine**: Hiển thị mô hình AI đang điều phối (ví dụ: OpenAI GPT-5.4-mini hoặc Fallback Rule Engine).
   - **Risk Thresholds**: Các thông số trần rủi ro tối đa (Max Single Trade USD, Max Allocation).
2. **Auto Scan & Watchlist Care Controls**:
   - Nút kích hoạt quét thị trường tức thì (Run Scan Now) hoặc chạy toàn bộ chu kỳ (Run Full Cycle).
   - Tùy chỉnh danh mục theo dõi ưu tiên (Watchlist Care) và chu kỳ tự động của Scheduler.
3. **Market Scoring Table (Ma trận chấm điểm thị trường)**:
   - Hiển thị danh sách các cặp coin theo dõi (BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, XRP/USDT, AVAX/USDT, DOGE/USDT...).
   - **Trend Score**: Điểm số xu hướng tính toán từ chuỗi nến OHLCV (Moving Average, quán tính nến).
   - **Liquidity Score**: Điểm số thanh khoản tính từ 24h Orderbook Depth và Volume.
   - **Volatility Score & Spread**: Biên độ biến động và chênh lệch giá mua/bán nhằm loại bỏ các cặp coin có rủi ro trượt giá cao.
4. **AI Market Thesis Panel (Luận điểm thị trường AI)**:
   - Tóm tắt góc nhìn vĩ mô về toàn thị trường tiền mã hóa từ AI Advisor.
   - Luận điểm phân bổ danh mục (Allocation Thesis) cho từng coin tiềm năng.
5. **Risk Gates & Execution Proposal**:
   - Bảng kiểm tra điều kiện an toàn: Tỷ trọng phân bổ ngành, hạn mức rủi ro tối đa, trạng thái số dư ví Spot USDT.
   - Danh sách các Trade Proposals được phê duyệt và lịch sử giao dịch mô phỏng/thực tế.

---

## 🚀 Các Tính Năng Cốt Lõi (Core Features)

### 1. Market Scanner & Scoring Engine
- Kết nối trực tiếp qua thư viện ccxt và REST API v5 của sàn OKX.
- Quét tự động danh sách các cặp coin cấu hình trong MARKET_SYMBOLS.
- Thu thập đồng thời Ticker giá hiện tại, sổ lệnh (Orderbook) và nến lịch sử OHLCV đa khung thời gian.
- Thuật toán định lượng tự động chấm điểm 3 chiều:
  - **Trend**: Xác định xu hướng tăng/giảm và sức mạnh xu hướng.
  - **Liquidity**: Đảm bảo khối lượng giao dịch đủ lớn để hấp thụ lệnh mà không tạo trượt giá.
  - **Volatility**: Đo lường ATR và biên độ dao động giá để tối ưu khoảng dừng lỗ (SL).

### 2. AI Market Thesis & Dynamic Allocation Advisor
- Sử dụng mô hình ngôn ngữ lớn (OpenAI GPT-5.4-mini / GPT-4o-mini) đóng vai trò Chuyên gia Phân Bổ Vốn (Portfolio Allocation Advisor).
- AI tiếp nhận dữ liệu thị trường nén, đưa ra nhận định vĩ mô sắc bén (Macro Market Thesis) và đề xuất tỷ lệ vốn tối ưu cho từng đồng coin.
- **Cơ chế Fallback thông minh**: Nếu thiếu OPENAI_API_KEY hoặc gặp sự cố mạng, hệ thống tự động chuyển sang bộ quy tắc Fallback Rule Advisor xác định, đảm bảo chu kỳ quét không bao giờ bị gián đoạn.

### 3. Rule-Based Strategy Engine
- Chiến lược vào lệnh mua (BUY Proposal) dựa trên sự đồng thuận giữa Điểm Kỹ Thuật (Trend & Liquidity Scores) và Đề xuất từ AI Advisor.
- Tự động xác định điểm vào lệnh (Entry), ngưỡng dừng lỗ (Stop Loss) theo ATR và các mục tiêu chốt lời (Take Profit) phân tầng.

### 4. Hệ Thống Chốt Chặn Rủi Ro Đa Tầng (Risk Engine)
- **Portfolio Allocation Cap**: Giới hạn tỷ trọng tối đa phân bổ cho một đồng coin hoặc một nhóm coin liên quan.
- **Liquidity Guard**: Từ chối vào lệnh nếu độ sâu thanh khoản sổ lệnh dưới ngưỡng an toàn.
- **Volatility Filter**: Tự động phong tỏa vào lệnh khi thị trường biến động giật cục hoặc spread giãn nở bất thường.
- **Max USD Guard**: Khống chế số tiền tối đa cho một lệnh đơn lẻ (MAX_LIVE_TRADE_USD).

### 5. Quản Lý Vị Thế & Chăm Sóc Danh Mục (Position Manager & Watchlist Care)
- position_manager.py: Theo dõi liên tục các vị thế mở, cập nhật trailing stop và kích hoạt tín hiệu đóng vị thế khi chạm mục tiêu.
- watchlist_care.py: Tiến trình định kỳ đánh giá lại danh sách theo dõi, loại bỏ các token suy yếu thanh khoản và bổ sung các cơ hội mới.
- position_backtest.py: Hỗ trợ mô phỏng kiểm thử lại lịch sử các vị thế đã khớp.

### 6. Hai Chế Độ Vận Hành: Paper & Live Execution
- **Paper Trading (Mặc định)**: Toàn bộ quá trình tạo proposal, tính lot, kiểm tra risk và khớp lệnh được mô phỏng ảo chính xác từng micro-cent, bảo toàn tuyệt đối 100% vốn thật.
- **Live Trading Guardrail**: Chế độ Live yêu cầu đồng thời 3 chốt chặn:
  1. LIVE_TRADING_ENABLED=true trong cấu hình.
  2. Khóa API OKX có quyền Trade hợp lệ.
  3. Cung cấp chính xác cụm từ an toàn bí mật (SAFETY_PHRASE).

### 7. Tích Hợp Cơ Sở Dữ Liệu & Thông Báo Tức Thời
- **MongoDB Atlas**: Lưu trữ toàn bộ lịch sử quét thị trường, luận điểm AI, đề xuất phân bổ vốn và nhật ký khớp lệnh để phục vụ kiểm toán và báo cáo hiệu suất.
- **Telegram Notifier**: Tự động gửi tin nhắn báo động tức thời khi phát hiện cơ hội giao dịch mới, khớp lệnh, chạm SL/TP hoặc phát sinh lỗi hệ thống.

---

## 🏛️ Kiến Trúc Module Mã Nguồn

`	ext
bot_spot/
├── config/
│   ├── allocation.yaml         # Quy tắc phân bổ vốn và tỷ trọng tối đa
│   ├── risk.yaml               # Các ngưỡng chốt chặn rủi ro (spread, slippage, max loss)
│   └── telegram.yaml           # Cấu hình mẫu tin nhắn thông báo Telegram
├── docs/
│   └── images/
│       └── dashboard.png       # Ảnh chụp Web UI Dashboard
├── spot_ai_bot/
│   ├── ai.py                   # Module AI Advisor (OpenAI integration & Fallback rule)
│   ├── candles.py              # Xử lý nến OHLCV và tính toán chỉ báo kỹ thuật
│   ├── config.py               # Quản lý cấu hình Pydantic Settings
│   ├── db.py                   # Kết nối MongoDB Atlas và các thao tác CRUD
│   ├── exchange.py             # Adapter CCXT kết nối sàn giao dịch
│   ├── execution.py            # Động cơ khớp lệnh Paper Execution & Live Execution
│   ├── main.py                 # FastAPI Application, Web routes và background tasks
│   ├── market_data.py          # Thu thập Ticker, Orderbook và quét toàn thị trường
│   ├── okx_market.py           # Tiện ích API công khai sàn OKX
│   ├── okx_private.py          # Quản lý số dư, vị thế và tài khoản Private OKX
│   ├── portfolio.py            # Tính toán phân bổ danh mục và tài sản khả dụng
│   ├── position_backtest.py    # Backtest kiểm định vị thế giao dịch
│   ├── position_manager.py     # Giám sát và quản lý vị thế đang mở
│   ├── risk.py                 # Risk Engine kiểm tra điều kiện an toàn
│   ├── scheduler.py            # Bộ điều phối tác vụ nền (APScheduler)
│   ├── strategy.py             # Chiến lược định lượng Rule Strategy
│   ├── telegram.py             # Gửi thông báo Telegram Bot
│   ├── trade_thesis.py         # Tổng hợp dữ liệu xây dựng luận điểm AI
│   ├── watchlist_care.py       # Quản lý và làm mới danh mục theo dõi
│   └── static/                 # Giao diện Web Dashboard (HTML5, CSS3, Modern JS)
├── requirements.txt            # Danh sách thư viện phụ thuộc Python
└── README.md                   # Tài liệu hướng dẫn chi tiết
`

---

## ⚙️ Hướng Dẫn Cài Đặt & Cấu Hình

### 1. Yêu Cầu Môi Trường
- Python 3.11+ (khuyến nghị Python 3.11.9)
- Tài khoản sàn OKX (API Key với quyền Read + Trade)
- OpenAI API Key (tùy chọn; nếu không có bot sẽ tự động dùng Fallback Rule)
- MongoDB Atlas Connection String (tùy chọn để lưu trữ lịch sử)

### 2. Cài Đặt Môi Trường Ảo
`powershell
cd C:\Users\Admin\Documents\crypto\bot_spot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
`

### 3. Thiết Lập Biến Môi Trường (.env)
Tạo file .env từ file mẫu .env.example:

`ini
# Cấu hình sàn giao dịch
EXCHANGE_NAME=okx
OKX_API_KEY=your_okx_api_key_here
OKX_API_SECRET=your_okx_api_secret_here
OKX_API_PASSPHRASE=your_okx_passphrase_here

# Chế độ giao dịch
LIVE_TRADING_ENABLED=false
SAFETY_PHRASE=I_UNDERSTAND_THE_RISKS
MAX_LIVE_TRADE_USD=50.0

# Trí tuệ nhân tạo (OpenAI)
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-5.4-mini

# Cơ sở dữ liệu & Thông báo (Tùy chọn)
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/crypto_spot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
`

---

## 🚦 Hướng Dẫn Khởi Chạy

### 1. Khởi Động Web Dashboard & REST API
`powershell
cd C:\Users\Admin\Documents\crypto\bot_spot
.\.venv\Scripts\Activate.ps1
python -m uvicorn spot_ai_bot.main:app --host 0.0.0.0 --port 8000 --reload
`

Truy cập trên trình duyệt:
- **Web Dashboard**: http://localhost:8000
- **Tài liệu Swagger API**: http://localhost:8000/docs

### 2. Các Endpoint REST API Quan Trọng
- GET /health: Kiểm tra sức khỏe hệ thống, trạng thái kết nối sàn và chế độ giao dịch.
- GET /config/summary: Xem tóm tắt toàn bộ tham số cấu hình đang kích hoạt.
- GET /market/scan: Quét toàn bộ thị trường và trả về danh sách ứng viên đạt chuẩn.
- POST /run-once: Thực thi một chu kỳ hoàn chỉnh (Thu thập dữ liệu -> AI Market Thesis -> Rule Strategy -> Risk Evaluation -> Execution).
- GET /positions/active: Liệt kê các vị thế đang được theo dõi và quản lý.

---

## 🛡️ Khuyến Cáo An Toàn Vốn
- Luôn chạy thử nghiệm ở chế độ **Paper Trading** ít nhất 7 - 14 ngày trước khi cân nhắc chuyển sang Live.
- Khi chuyển sang Live, chỉ cấp mức vốn nhỏ (MAX_LIVE_TRADE_USD <= 50 USD) để kiểm tra độ trễ mạng và cơ chế khớp lệnh thực tế của broker.\n