# 💰 WalletBot

> **Your Telegram crypto & money wallet** — check balances, track prices, and manage your digital money without leaving Telegram.

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot_API-2CA5E0.svg)](https://core.telegram.org/bots/api)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 📖 About

**WalletBot** is a Telegram bot for managing digital wallets and tracking cryptocurrency. Keep an eye on your balances, get live price alerts, and handle your money with simple chat commands.

> 🛠️ **Note:** This repository is under active development. Features below describe the planned roadmap — star ⭐ the repo to follow progress!

---

## ✨ Key Features (Roadmap)

### 💼 Wallet Management
- **Multi-wallet support** — track multiple wallets in one place
- **Balance overview** — see all your balances with one command
- **Transaction history** — browse recent activity per wallet

### 📈 Crypto Tracking
- **Live prices** for major cryptocurrencies (BTC, ETH, USDT, …)
- **Price alerts** — get notified when a coin hits your target
- **Portfolio value** — total worth calculated in USD / IQD

### 🔔 Smart Notifications
- **Balance change alerts** for incoming/outgoing transactions
- **Daily summary** of your portfolio performance

### 🔐 Security First
- **No private keys stored** — the bot only tracks public addresses
- **Secrets via environment variables** — nothing hardcoded

---

## 🛠️ Tech Stack

| Component      | Technology                 |
|----------------|----------------------------|
| Language       | Python 3.11+               |
| Bot Framework  | `pyTelegramBotAPI`         |
| Price Data     | CoinGecko / Binance API    |
| Database       | SQLite                     |

---

## 🚀 Installation

### Prerequisites
- Python 3.11+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/tahagamer712-beep/WalletBot.git
cd WalletBot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env and fill in:
#   BOT_TOKEN=your_telegram_bot_token
#   ADMIN_ID=your_telegram_user_id

# 4. Run the bot
python main.py
```

---

## ⚙️ Configuration

| Variable     | Required | Description                       |
|--------------|----------|-----------------------------------|
| `BOT_TOKEN`  | ✅       | Telegram bot token from BotFather |
| `ADMIN_ID`   | ✅       | Telegram user ID of the admin     |

See `.env.example` for the full list.

---

## 📁 Project Structure

```
WalletBot/
├── main.py            # Entry point
├── handlers.py        # Command & message handlers
├── wallet.py          # Wallet management logic
├── prices.py          # Crypto price fetching
├── db.py              # Database layer
├── config.py          # Configuration
├── .env.example       # Environment template
└── requirements.txt   # Dependencies
```

---

## 💡 Usage Examples

**Check your portfolio:**
> `/balance` — shows all wallets and total value.

**Set a price alert:**
> `/alert BTC 100000` — notifies you when BTC hits $100,000.

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## 📬 Contact

- **Developer:** [@tahagamer712-beep](https://github.com/tahagamer712-beep)
- **Issues:** [GitHub Issues](https://github.com/tahagamer712-beep/WalletBot/issues)

---

<p align="center">Your money, one message away 💰</p>
