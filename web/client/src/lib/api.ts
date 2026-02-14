import axios from 'axios';

export const API_BASE = '/api';

export const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
});

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, { ...options, credentials: 'include' });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new ApiError(`API Error: ${res.status} ${res.statusText} - ${text}`, res.status);
  }
  return res.json();
}

// Auth
export async function fetchUser() {
  try {
    const data = await fetchJson<{ user: any }>(`${API_BASE}/auth/me`);
    return data.user;
  } catch (e) {
    return null;
  }
}

export async function logout() {
  await fetch(`${API_BASE}/auth/logout`, { method: 'POST' });
}

// Trading
export async function fetchTelegramLogs() {
  try {
    return await fetchJson<any[]>(`${API_BASE}/telegram/logs?limit=200`);
  } catch (e) {
    console.error("Error fetching telegram logs:", e);
    return [];
  }
}

export async function fetchConfig(openId: string) {
  // openId not required for URL as it relies on session cookie
  // Keeping openId param for compatibility if used elsewhere, but not using in URL
  try {
    const data = await fetchJson<{ config: any }>(`${API_BASE}/config/`);
    return data.config;
  } catch (e) {
    console.error("Error fetching config:", e);
    return null;
  }
}

export async function updateConfig(openId: string, config: any) {
  // openId not required for URL as it relies on session cookie
  return fetchJson(`${API_BASE}/config/`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config)
  });
}

export async function fetchSignals(openId: string) {
  // openId deprecated, using cookie
  try {
    return await fetchJson<any[]>(`${API_BASE}/signals?limit=50`);
  } catch (e) {
    console.error("Error fetching signals:", e);
    return [];
  }
}

export async function fetchTrades(openId: string) {
  // openId deprecated, using cookie
  try {
    return await fetchJson<any[]>(`${API_BASE}/trades?limit=100`);
  } catch (e) {
    console.error("Error fetching trades:", e);
    return [];
  }
}

// Telegram bots (1 doc per signal/bot)
export async function fetchTelegramBots(limit = 100) {
  try {
    return await fetchJson<any[]>(`${API_BASE}/telegram/bots?limit=${limit}`);
  } catch (e) {
    console.error('Error fetching telegram bots:', e);
    return [];
  }
}

// Telegram trades (TP/SL docs) for a given bot
export async function fetchTelegramTradesByBot(botId: string, limit = 200) {
  try {
    const qs = new URLSearchParams({ botId, limit: String(limit) }).toString();
    return await fetchJson<any[]>(`${API_BASE}/telegram/trades?${qs}`);
  } catch (e) {
    console.error('Error fetching telegram trades:', e);
    return [];
  }
}

// Strategy bot instances
export async function fetchBots() {
  try {
    return await fetchJson<any[]>(`${API_BASE}/bots/`);
  } catch (e) {
    console.error("Error fetching bots:", e);
    return [];
  }
}

// Unified view for Trades page (telegram trades + strategy bots)
export async function fetchTradeInstancesUnified() {
  const [telegramTrades, bots] = await Promise.all([
    fetchTelegramBots(),
    fetchBots(),
  ]);

  // Normalize fields so Trades.tsx can render consistently.
  const taggedTelegram = (telegramTrades || []).map((t: any) => ({
    ...t,
    __kind: 'telegram_bot',
    marketType: (t.marketType || t.market_type || '').toString().toUpperCase() || 'CEX',
    mode: t.mode,
    isDemo: t.mode === 'simulated' || t.isDemo === true,
  }));

  const taggedBots = (bots || []).map((b: any) => ({
    ...b,
    __kind: 'strategy_bot',
    // align naming
    id: b.id || b._id,
    marketType: (b.market_type || b.marketType || 'CEX').toString().toUpperCase(),
    investment: b.investment ?? b.amount,
    mode: b.mode,
    isDemo: b.mode === 'simulated' || b.isDemo === true,
    // bots use active_position in API
    position: b.position ?? b.active_position,
    createdAt: b.createdAt || b.created_at || b.updatedAt || b.updated_at || new Date().toISOString(),
  }));

  return [...taggedTelegram, ...taggedBots];
}

export async function fetchBalances(openId: string) {
  // openId deprecated, using cookie
  try {
    return await fetchJson<any[]>(`${API_BASE}/balances`);
  } catch (e) {
    console.error("Error fetching balances:", e);
    return [];
  }
}

// Backtest
export async function fetchExchanges() {
  try {
    const ids = await fetchJson<string[]>(`${API_BASE}/market/exchanges`);
    return ids.map(id => ({ exchangeId: id, isActive: true }));
  } catch (e) {
    console.error("Error fetching exchanges:", e);
    return [];
  }
}

export async function fetchMarkets(exchangeId: string) {
  if (!exchangeId) return { markets: [] };
  try {
    return await fetchJson<{ markets: any[] }>(`${API_BASE}/backtest/markets/${exchangeId}`);
  } catch (e) {
    console.error("Error fetching markets:", e);
    return { markets: [] };
  }
}

export async function fetchSymbols(exchangeId: string, marketType: string) {
  if (!exchangeId || !marketType) return { symbols: [] };
  try {
    return await fetchJson<{ symbols: any[] }>(`${API_BASE}/backtest/symbols/${exchangeId}?market_type=${marketType}`);
  } catch (e) {
    console.error("Error fetching symbols:", e);
    return { symbols: [] };
  }
}
