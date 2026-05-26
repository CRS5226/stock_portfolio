#!/bin/bash
# Startup script for stock_portfolio Streamlit app
cd /root/chitraksh/stock_portfolio
exec /root/chitraksh/stock_market_breakout_8/venv_market/bin/streamlit run main.py \
  --server.port 8502 \
  --server.address 0.0.0.0 \
  --server.headless true
