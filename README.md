# SignalKey Platform

Plataforma completa de trading automatizado que integra CEX, DEX y análisis de IA.

## Estructura

- **api/** - API Python con FastAPI para recibir señales, análisis con Gemini y ejecución en exchanges
- **web/** - Interfaz web React con dashboard, backtesting y configuración

## Inicio Rápido

### API
```bash
cd api
pip install -r requirements.txt
cp .env.example .env
# Configura tus API Keys en .env
python main.py
```

### Web
```bash
cd web
pnpm install
pnpm dev
```

## Características

- ✅ Recepción de señales vía Telegram/Webhooks
- ✅ Análisis con Gemini AI
- ✅ Ejecución en CEX (CCXT) y DEX (GMGN)
- ✅ Modo Demo para pruebas sin riesgo
- ✅ Backtesting con datos históricos
- ✅ Dashboard profesional
- ✅ Historial de trades
- ✅ Configuración segura de API Keys

## Requisitos

- Python 3.11+
- Node.js 22+
- pnpm
