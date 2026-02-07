export const API_BASE = '/api';

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
  if (!openId) return [];
  try {
    return await fetchJson<any[]>(`${API_BASE}/signals?user_id=${openId}&limit=50`);
  } catch (e) {
    console.error("Error fetching signals:", e);
    return [];
  }
}

export async function fetchTrades(openId: string) {
  if (!openId) return [];
  try {
    return await fetchJson<any[]>(`${API_BASE}/trades?user_id=${openId}&limit=100`);
  } catch (e) {
    console.error("Error fetching trades:", e);
    return [];
  }
}

export async function fetchBalances(openId: string) {
  if (!openId) return [];
  try {
    return await fetchJson<any[]>(`${API_BASE}/balances/${openId}`);
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
