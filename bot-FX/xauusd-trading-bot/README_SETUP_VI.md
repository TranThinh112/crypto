# Hướng Dẫn Clone Và Chạy Bot

File này ghi rõ những thứ cần điền/cài để clone repo về máy mới và dùng được bot.

## 1. Cần Cài Trước

- Windows.
- Python 3.11 x64.
- MetaTrader 5 của broker đang dùng, ví dụ XM Global MT5.
- Tài khoản MT5 demo đã đăng nhập trong terminal.
- Bật nút Algo Trading trong MT5.

## 2. Cài Dependency

```powershell
cd "xauusd-trading-bot"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

## 3. File Cần Điền

Chỉ điền file này:

```text
.env
```

Không commit/push file `.env` lên GitHub.

## 4. Nội Dung `.env` Mẫu

```env
DATABASE_URL=sqlite:///data/trading_bot.db
TRADING_CONFIG_PATH=app/config/trading_config_btc.yaml

MT5_LOGIN=
MT5_PASSWORD=
MT5_SERVER=XMGlobal-MT5 9
MT5_TERMINAL_PATH=C:\Program Files\XM Global MT5\terminal64.exe

TRADING_MODE=PAPER
ENABLE_LIVE_TRADING=false
REQUIRE_DEMO_ACCOUNT=true
BROKER_STARTUP_ENABLED=true
AUTO_START_BOT=false

API_HOST=127.0.0.1
API_PORT=8000
LOG_LEVEL=INFO

LEARNING_SEED_PATH=data/learning_seed.jsonl
```

## 5. Giải Thích Các Biến Quan Trọng

`DATABASE_URL`: nơi lưu database local. Mặc định dùng SQLite trong `data/trading_bot.db`.

`TRADING_CONFIG_PATH`: chọn cấu hình bot:

- `app/config/trading_config_btc.yaml`: profile BTCUSD.
- `app/config/trading_config_gold.yaml`: profile GOLD/XAUUSD.
- `app/config/trading_config.yaml`: profile mặc định.

`MT5_LOGIN`: số tài khoản MT5. Có thể để trống nếu MT5 đã login sẵn.

`MT5_PASSWORD`: mật khẩu MT5. Có thể để trống nếu MT5 đã login sẵn.

`MT5_SERVER`: server broker, ví dụ `XMGlobal-MT5 9`.

`MT5_TERMINAL_PATH`: đường dẫn file `terminal64.exe` trên máy mới.

`TRADING_MODE`: để `PAPER` khi mới clone/test. Chỉ đổi `LIVE` khi đã kiểm tra kỹ.

`ENABLE_LIVE_TRADING`: chốt an toàn cho lệnh thật. Khi test để `false`.

`REQUIRE_DEMO_ACCOUNT`: nên để `true`, bot chỉ gửi lệnh nếu tài khoản là demo.

`AUTO_START_BOT`: nếu `true`, bot tự chạy khi server khởi động. Khi mới clone nên để `false`.

`LEARNING_SEED_PATH`: file dữ liệu học đã được làm sạch để nạp vào DB mới.

## 6. Khởi Tạo Database Và Nạp Dữ Liệu Học

```powershell
python scripts/init_db.py
python scripts/import_learning_seed.py
```

File `data/learning_seed.jsonl` là dữ liệu học đã bỏ thông tin nhạy cảm như broker ticket và idempotency thật.

Không dùng để push:

- `data/trading_bot.db`
- `data/learning_export.jsonl`
- `logs/`
- `.env`

## 7. Chạy Dashboard

Cách nhanh trên Windows:

```powershell
.\RUN_BOT_DASHBOARD.bat
```

Hoặc chạy thủ công:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Mở dashboard:

```text
http://127.0.0.1:8000
```

## 8. Quy Trình An Toàn Khi Muốn LIVE

1. Chạy `PAPER` trước.
2. Kiểm tra dashboard có `RUNNING / RECONCILIATION_OK`.
3. Kiểm tra MT5 đã login đúng tài khoản demo.
4. Kiểm tra symbol broker nhận đúng, ví dụ `BTCUSD`, `GOLD`, hoặc alias tương ứng.
5. Sau khi ổn mới đổi:

```env
TRADING_MODE=LIVE
ENABLE_LIVE_TRADING=true
AUTO_START_BOT=true
```

Nếu dùng tài khoản thật, tự chịu rủi ro. Bot không đảm bảo lợi nhuận.

## 9. Push GitHub An Toàn

Được push:

- Code trong `app/`, `scripts/`, `tests/`, `docs/`.
- `.env.example`.
- `data/learning_seed.jsonl`.

Không push:

- `.env`.
- `data/trading_bot.db`.
- `data/learning_export.jsonl`.
- `logs/`.
- File backup local trong `data/backups/`.
