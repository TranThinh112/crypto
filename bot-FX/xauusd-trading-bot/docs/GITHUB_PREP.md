# GitHub Preparation

## Do Not Push

- `.env`: may contain MT5/XM login, password, server, terminal path, live mode flags.
- `data/trading_bot.db`: live SQLite database with trades, broker tickets, signals, cooldowns, and runtime state.
- `logs/`: runtime logs can contain broker responses, tickets, local paths, and operational history.
- `data/backups/` and ad-hoc monitor files: local operational artifacts.

## Safe To Push

- `.env.example`: template variables only.
- `app/config/*.yaml`: strategy/risk settings, as long as they do not contain account credentials.
- `data/learning_seed.jsonl`: sanitized learning history generated from `learning_export.jsonl`.

## Clone Setup

```powershell
Copy-Item .env.example .env
python scripts/init_db.py
python scripts/import_learning_seed.py
```

For XM/MT5, fill these locally in `.env`:

```env
MT5_LOGIN=
MT5_PASSWORD=
MT5_SERVER=XMGlobal-MT5 9
MT5_TERMINAL_PATH=C:\Program Files\XM Global MT5\terminal64.exe
```

Keep `ENABLE_LIVE_TRADING=false` until the new machine is verified in PAPER/demo mode.
