import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

// Use 10.0.2.2 for Android Emulator, localhost for iOS/Web
const DEV_API_URL = Platform.OS === 'android'
  ? 'http://10.0.2.2:8000/api'
  : 'http://localhost:8000/api';

// You can replace this with your actual production URL when deploying
export const API_BASE = DEV_API_URL;

export const TOKEN_KEY = 'auth_token';

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function getHeaders() {
  const token = await SecureStore.getItemAsync(TOKEN_KEY);
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

export async function fetchJson<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const headers = await getHeaders();
  const url = `${API_BASE}${endpoint}`;

  const config = {
    ...options,
    headers: {
      ...headers,
      ...options?.headers,
    },
  };

  try {
    const res = await fetch(url, config);

    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new ApiError(`API Error: ${res.status} ${res.statusText} - ${text}`, res.status);
    }

    // Handle 204 No Content
    if (res.status === 204) {
      return {} as T;
    }

    return res.json();
  } catch (error) {
    console.error(`Fetch error for ${url}:`, error);
    throw error;
  }
}

// Auth API
export async function login(data: any) {
  return fetchJson<{ token: string; user: any }>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function register(data: any) {
  return fetchJson<{ token: string; user: any }>('/auth/register', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function fetchUser() {
  try {
    const data = await fetchJson<{ user: any }>('/auth/me');
    return data.user;
  } catch (e) {
    return null;
  }
}

export async function logout() {
    await SecureStore.deleteItemAsync(TOKEN_KEY);
}

// Data API
export async function fetchSignals(openId: string) {
  if (!openId) return [];
  return fetchJson<any[]>(`/signals?user_id=${openId}&limit=50`);
}

export async function approveSignal(signalId: string) {
  return fetchJson<{ success: boolean; message: string; details?: any }>(`/signals/${signalId}/approve`, {
    method: 'POST'
  });
}

export async function fetchTrades(openId: string) {
  if (!openId) return [];
  return fetchJson<any[]>(`/trades?user_id=${openId}&limit=100`);
}

export async function fetchBots(openId: string) {
  // Assuming there is a bots endpoint, though web might fetch differently.
  // Let's check web logic later. For now, standard fetch.
  return fetchJson<any[]>(`/bot/status/${openId}`);
}

export async function stopBot(botId: string) {
  return fetchJson<{ success: boolean }>(`/bot/${botId}`, {
    method: 'DELETE'
  });
}

export async function fetchConfig() {
  return fetchJson<{ config: any }>('/config/');
}

export async function updateConfig(config: any) {
  return fetchJson('/config/', {
    method: 'PUT',
    body: JSON.stringify(config)
  });
}

// Backtest
export async function fetchExchanges() {
  const ids = await fetchJson<string[]>('/market/exchanges');
  return ids.map(id => ({ exchangeId: id, isActive: true }));
}

export async function fetchMarkets(exchangeId: string) {
  if (!exchangeId) return { markets: [] };
  return fetchJson<{ markets: any[] }>(`/backtest/markets/${exchangeId}`);
}

export async function fetchSymbols(exchangeId: string, marketType: string) {
  if (!exchangeId || !marketType) return { symbols: [] };
  return fetchJson<{ symbols: any[] }>(`/backtest/symbols/${exchangeId}?market_type=${marketType}`);
}

export async function runBacktest(params: any) {
    return fetchJson<any>('/backtest/run', {
        method: 'POST',
        body: JSON.stringify(params)
    });
}

// ML
export async function startTraining(params: any) {
    return fetchJson<{ success: boolean; message: string }>('/ml/train', {
        method: 'POST',
        body: JSON.stringify(params)
    });
}
