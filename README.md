# Portfolio Manager — Kotak Neo

A Streamlit-based stock portfolio dashboard for Kotak Neo accounts.  
Supports CNC (Delivery), MTF (Margin), MIS (Intraday), and F&O order placement with OTP confirmation via Telegram.

---

## Features

- Live portfolio dashboard (CNC holdings + MTF + F&O positions)
- Place orders — Market, Limit, Stop-Loss Limit
- OTP-based order confirmation delivered via Telegram bot
- Auto-sync every 3 minutes in the background
- F&O (Futures & Options) trading panel
- Order history with CSV export

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.10 or higher |
| Redis | 6.x or higher |
| Node.js + npm | For PM2 (optional, only for server deployment) |

---

## 1. Clone the Repository

```bash
git clone https://github.com/CRS5226/stock_portfolio.git
cd stock_portfolio
```

---

## 2. Create a Python Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate        # Linux / macOS
# venv\Scripts\activate         # Windows
```

---

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 4. Install and Start Redis

**Ubuntu / Debian:**
```bash
sudo apt update && sudo apt install -y redis-server
sudo systemctl enable redis-server
sudo systemctl start redis-server
```

**macOS (Homebrew):**
```bash
brew install redis
brew services start redis
```

**Verify Redis is running:**
```bash
redis-cli ping   # should return PONG
```

---

## 5. Kotak Neo API Credentials

You need a Kotak Neo trading account with API access enabled.

1. Log in to [Kotak Neo API portal](https://neoapi.kotaksecurities.com/)
2. Create an application and copy your **Consumer Key**
3. Enable **TOTP** in your Kotak Neo app and note the **TOTP Secret**
4. Note your registered **Mobile number**, **MPIN**, and **UCC** (client code)

---

## 6. Telegram Bot for OTP Delivery

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts — copy the **Bot Token**
3. Start a chat with your new bot, then visit:
   ```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
   ```
4. Send any message to the bot and refresh the URL above — copy your **Chat ID** from the `"id"` field

---

## 7. Configure Environment Variables

Create a `.env` file in the project root:

```bash
cp .env.example .env   # if example exists, otherwise create manually
```

Edit `.env` with your actual credentials:

```env
# Kotak Neo API
KOTAK_CONSUMER_KEY=your_consumer_key_here
KOTAK_MOBILE=+91XXXXXXXXXX
KOTAK_MPIN=your_mpin
KOTAK_UCC=your_ucc_code
KOTAK_TOTP_SECRET=your_totp_secret_base32

# Telegram Bot
TELEGRAM_BOT_TOKEN_400a=your_telegram_bot_token

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

> ⚠️ **Never commit your `.env` file.** It is already in `.gitignore`.

---

## 8. Run Locally

```bash
source venv/bin/activate
streamlit run main.py --server.port 8502 --server.address 0.0.0.0
```

Open your browser at: **http://localhost:8502**

---

## 9. Deploy on a Cloud Server (Ubuntu VPS / EC2 / GCP)

### Step 1 — Set Up the Server

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.11+
sudo apt install -y python3 python3-pip python3-venv

# Install Redis
sudo apt install -y redis-server
sudo systemctl enable redis-server && sudo systemctl start redis-server

# Install Node.js (for PM2)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Install PM2 globally
sudo npm install -g pm2
```

### Step 2 — Clone and Install

```bash
git clone https://github.com/CRS5226/stock_portfolio.git
cd stock_portfolio
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 3 — Create `.env` file

```bash
nano .env   # paste your credentials and save
```

### Step 4 — Open Firewall Port (if needed)

```bash
# Ubuntu UFW
sudo ufw allow 8502/tcp

# AWS EC2 — add inbound rule for port 8502 in Security Group via AWS Console
# GCP — add firewall rule for port 8502 via GCP Console
```

### Step 5 — Start with PM2

```bash
pm2 start run.sh --name portfolio --interpreter bash
pm2 save
pm2 startup   # follow the printed command to auto-start on reboot
```

**Check status and logs:**
```bash
pm2 status
pm2 logs portfolio --lines 50
```

**Restart after a code update:**
```bash
git pull
pm2 restart portfolio
```

Access the app at: **http://YOUR_SERVER_IP:8502**

---

## 10. Optional — Serve via Nginx with a Domain

Install Nginx and set up a reverse proxy so you can access the app on port 80/443:

```bash
sudo apt install -y nginx
sudo nano /etc/nginx/sites-available/portfolio
```

Paste this config (replace `yourdomain.com`):

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass         http://127.0.0.1:8502;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
        proxy_read_timeout 86400;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/portfolio /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

For HTTPS, use **Certbot**:
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

---

## Project Structure

```
stock_portfolio/
├── main.py                  # App entry point, navigation, header
├── config.py                # Environment variables, constants
├── requirements.txt         # Python dependencies
├── run.sh                   # PM2 startup script
├── .env                     # Credentials (not committed)
├── auth/
│   └── kotak_client.py      # Kotak Neo API client, Redis, stock loaders
├── data/
│   ├── sync.py              # Portfolio sync (CNC, MTF, F&O)
│   └── prices.py            # Live price fetching
├── orders/
│   ├── place_order.py       # Order placement logic
│   └── otp.py               # OTP generation and verification
├── ui/
│   ├── dashboard.py         # Portfolio dashboard page
│   ├── place_order_ui.py    # Place order page
│   ├── order_history.py     # Order history page
│   └── theme.py             # UI colour theme
├── fo/
│   └── fo_ui_helper.py      # F&O trading page
├── utils/
│   └── telegram.py          # Telegram OTP delivery
└── config_kotak_nse.json    # NSE instrument master
```

---

## Common Issues

| Problem | Fix |
|---|---|
| `Kotak Neo login failed` | Check all `KOTAK_*` values in `.env`, ensure TOTP secret is correct |
| `Redis connection refused` | Run `sudo systemctl start redis-server` |
| `No stocks found` | Ensure `config_kotak_nse.json` / `config_kotak_bse.json` are present |
| OTP not received on Telegram | Start a conversation with your bot first; check `TELEGRAM_BOT_TOKEN_400a` |
| Port 8502 not accessible | Open the port in your server's firewall / security group |

---

## License

Private repository — for personal use only.
