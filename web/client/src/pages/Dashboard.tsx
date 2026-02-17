import React, { useEffect, useState, useMemo } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Switch } from '@/components/ui/switch';
import { useTrading } from '@/contexts/TradingContext';
import { useAuth } from '@/_core/hooks/useAuth';
import { TrendingUp, TrendingDown, DollarSign, Zap } from 'lucide-react';
import { useSocket } from '@/_core/hooks/useSocket';
import { useQueryClient, useQuery } from '@tanstack/react-query';
import { CONFIG } from '@/config';
import { Badge } from '@/components/ui/badge';
import { fetchBalances, fetchTrades } from '@/lib/api';

const MetaSelectorWidget = ({ user }: { user: any }) => {
  const [symbol, setSymbol] = useState('BTC/USDT');
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const handlePredict = async () => {
    if (!symbol) return;
    setLoading(true);
    try {
      const res = await fetch(`${CONFIG.API_BASE_URL}/ml/predict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: symbol.toUpperCase(),
          timeframe: '1h',
          limit: 100,
          user_id: user?.openId
        })
      });
      const data = await res.json();
      setResult(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="p-6 border-l-4 border-l-purple-500 shadow-sm bg-slate-900/40">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 gap-4">
        <div>
          <h3 className="text-lg font-bold flex items-center gap-2 text-white">
            <Zap className="text-purple-500" />
            Meta-Selector AI
          </h3>
          <p className="text-xs text-slate-400">
            Predice la MEJOR estrategia para el mercado actual usando LSTM.
          </p>
        </div>
        <div className="flex gap-2 w-full md:w-auto">
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            className="bg-slate-800 border border-slate-700 rounded px-3 py-1 text-sm w-full md:w-32 text-white placeholder-slate-500 focus:outline-none focus:border-purple-500 transition-colors"
            placeholder="BTC/USDT"
          />
          <button
            onClick={handlePredict}
            disabled={loading}
            className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-1.5 rounded text-sm font-medium transition-colors disabled:opacity-50"
          >
            {loading ? 'Analizando...' : 'Escanear'}
          </button>
        </div>
      </div>

      {result ? (
        <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-500">
          <div className="flex items-center justify-between p-4 bg-slate-800/50 rounded-lg border border-white/5">
            <div>
              <span className="text-xs font-semibold uppercase text-slate-400 block mb-1">Estrategia Ganadora</span>
              <span className="text-xl font-bold text-white">
                {result.strategy_selected || 'HOLD'}
              </span>
            </div>
            <div className="text-right">
              <span className="text-xs font-semibold uppercase text-slate-400 block mb-1">Confianza</span>
              <span className="text-2xl font-bold text-purple-500">
                {Number(result.confidence).toFixed(1)}%
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className={`p-3 rounded-lg border text-center ${result.decision === 'BUY' ? 'bg-green-500/10 border-green-500/30 text-green-400' :
              result.decision === 'SELL' ? 'bg-red-500/10 border-red-500/30 text-red-400' :
                'bg-slate-500/10 border-slate-500/30 text-slate-400'
              }`}>
              <div className="text-xs font-semibold uppercase mb-1">Señal Final</div>
              <div className="font-black text-lg">{result.decision}</div>
            </div>
            <div className="p-3 bg-slate-800/30 rounded-lg border border-white/5 text-xs">
              <div className="font-semibold mb-2 text-slate-400">Probabilidades:</div>
              {result.class_probabilities && result.class_probabilities.map((p: number, i: number) => {
                const labels = ['HOLD', 'RSI', 'EMA', 'BREAKOUT'];
                return (
                  <div key={i} className="flex justify-between items-center mb-1 text-slate-300">
                    <span>{labels[i]}</span>
                    <span className="font-mono text-white">{(p * 100).toFixed(0)}%</span>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      ) : (
        <div className="text-center py-8 text-slate-500 bg-slate-800/20 rounded-lg border border-dashed border-white/5">
          <Zap className="mx-auto mb-2 opacity-20" size={32} />
          <p className="text-sm">Ingresa un par y escanea para ver qué estrategia domina ahora.</p>
        </div>
      )}
    </Card>
  );
};

export default function Dashboard() {
  const { user } = useAuth({ redirectOnUnauthenticated: true });
  const { demoMode } = useTrading();
  const queryClient = useQueryClient();

  const { data: balances, isLoading: balancesLoading } = useQuery({
    queryKey: ['balances', user?.openId],
    queryFn: () => fetchBalances(user?.openId),
    enabled: !!user?.openId
  });

  const { data: trades, isLoading: tradesLoading } = useQuery({
    queryKey: ['trades', user?.openId],
    queryFn: () => fetchTrades(user?.openId),
    enabled: !!user?.openId
  });

  const [connectionStatus, setConnectionStatus] = useState<any>(null);
  const { lastMessage } = useSocket(user?.openId);

  // Initial status fetch
  useEffect(() => {
    const fetchStatus = async () => {
      if (!user?.openId) return;
      try {
        const token = localStorage.getItem('signalkey.auth.token');
        const res = await fetch(`${CONFIG.API_BASE_URL}/status/${user.openId}`, {
          credentials: 'include',
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        });
        const data = await res.json();
        setConnectionStatus(data);
      } catch (e) {
        console.error('Error fetching initial status:', e);
      }
    };
    fetchStatus();
  }, [user?.openId]);

  const handleToggleTelegram = async (checked: boolean) => {
    if (!user?.openId) return;

    setConnectionStatus((prev: any) => ({ ...prev, botTelegramActivate: checked }));

    try {
      const token = localStorage.getItem('signalkey.auth.token');
      const res = await fetch(`${CONFIG.API_BASE_URL}/config/telegram_activate?active=${checked}`, {
        method: 'POST',
        credentials: 'include',
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
      if (!res.ok) throw new Error('Failed to update config');

      const statusRes = await fetch(`${CONFIG.API_BASE_URL}/status/${user.openId}`, {
        credentials: 'include',
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
      const data = await statusRes.json();
      setConnectionStatus(data);
    } catch (e) {
      console.error("Error updating telegram status:", e);
      setConnectionStatus((prev: any) => ({ ...prev, botTelegramActivate: !checked }));
    }
  };

  // Listen for socket updates
  useEffect(() => {
    if (!lastMessage) return;

    const { event, data } = lastMessage;

    if (event === 'status_update') {
      setConnectionStatus(data);
    } else if (event === 'balance_update') {
      queryClient.setQueryData(['balances', user?.openId], (oldData: any[] | undefined) => {
        if (!oldData) return [data];
        const exists = oldData.find(b => b.marketType === data.marketType && b.asset === data.asset);
        if (exists) {
          return oldData.map(b => b.marketType === data.marketType && b.asset === data.asset ? { ...b, amount: data.amount } : b);
        } else {
          return [...oldData, data];
        }
      });
    } else if (event === 'bot_update' || event === 'telegram_trade_update') {
      queryClient.setQueryData(['trades', user?.openId], (oldData: any[] | undefined) => {
        if (!oldData) return [data];
        const exists = oldData.find(t => t.id === data.id);
        if (exists) {
          return oldData.map(t => t.id === data.id ? { ...t, ...data } : t);
        } else {
          return [data, ...oldData];
        }
      });
    }
  }, [lastMessage, queryClient, user?.openId]);

  const cexBalance = useMemo(() => {
    return balances?.find((b: any) => String(b.marketType || '').toUpperCase() === 'CEX');
  }, [balances]);

  const dexBalance = useMemo(() => {
    return balances?.find((b: any) => String(b.marketType || '').toUpperCase() === 'DEX');
  }, [balances]);

  const stats = useMemo(() => {
    if (!trades || trades.length === 0) {
      return {
        totalTrades: 0,
        winRate: 0,
        totalPnL: 0,
        avgPnL: 0,
      };
    }

    const winningTrades = trades.filter((t: any) => (t.pnl || t.position?.pnl) > 0).length;
    const totalPnL = trades.reduce((sum: number, t: any) => sum + (t.pnl || t.position?.pnl || 0), 0);
    const avgPnL = totalPnL / trades.length;

    return {
      totalTrades: trades.length,
      winRate: Math.round((winningTrades / trades.length) * 100),
      totalPnL,
      avgPnL,
    };
  }, [trades]);

  const StatCard = ({ icon: Icon, label, value, change }: any) => (
    <Card className="p-6 bg-slate-900 border-slate-800">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-slate-400 mb-2 font-medium uppercase tracking-wider">{label}</p>
          <p className="text-3xl font-black text-white">{value}</p>
          {change !== undefined && (
            <p
              className={`text-xs mt-2 font-bold ${change >= 0 ? 'text-green-400' : 'text-red-400'
                }`}
            >
              {change >= 0 ? '↑' : '↓'} {Math.abs(change)}%
            </p>
          )}
        </div>
        <div className="p-3 bg-blue-500/10 rounded-xl">
          <Icon className="text-blue-400" size={24} />
        </div>
      </div>
    </Card>
  );

  return (
    <div className="p-8 space-y-8 animate-in fade-in duration-700">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-4xl font-black text-white tracking-tighter uppercase italic">
            Dashboard <span className="text-blue-500">Overview</span>
          </h1>
          <p className="text-slate-400 text-sm mt-1">Resumen general de operaciones y estado del sistema.</p>
        </div>
        {demoMode && (
          <Badge variant="destructive" className="py-2 px-4 shadow-lg shadow-red-500/10 animate-pulse bg-red-900/50 text-red-200 border-red-800">
            🧪 MODO DEMO ACTIVO
          </Badge>
        )}
      </div>

      {/* Connection Status */}
      {connectionStatus && (
        <Card className="p-4 bg-slate-900/40 border-slate-800">
          <div className="flex flex-col md:flex-row justify-between items-center gap-4">
            <div className="flex gap-4">
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${connectionStatus.gemini ? 'bg-green-500 shadow-[0_0_10px_#22c55e]' : 'bg-red-500'}`} />
                <span className="text-xs font-bold text-slate-300">Gemini AI</span>
              </div>
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${connectionStatus.exchange ? 'bg-green-500 shadow-[0_0_10px_#22c55e]' : 'bg-red-500'}`} />
                <span className="text-xs font-bold text-slate-300">Exchange</span>
              </div>
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${connectionStatus.telegram ? 'bg-green-500 shadow-[0_0_10px_#22c55e]' : 'bg-red-500'}`} />
                <span className="text-xs font-bold text-slate-300">Telegram</span>
              </div>
            </div>

            <div className="flex items-center gap-3 bg-slate-800/50 px-3 py-1.5 rounded-full border border-white/5">
              <Switch
                checked={connectionStatus.botTelegramActivate || false}
                onCheckedChange={handleToggleTelegram}
                className="scale-75 data-[state=checked]:bg-green-500"
              />
              <span className="text-xs font-bold text-slate-300">Telegram Signals</span>
            </div>
          </div>
        </Card>
      )}

      {/* META-SELECTOR WIDGET */}
      <MetaSelectorWidget user={user} />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card className="p-6 border-l-4 border-l-blue-500 bg-slate-900 border-slate-800">
          <h3 className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-4">Balance CEX</h3>
          {balancesLoading ? (
            <div className="h-12 bg-slate-800/50 animate-pulse rounded" />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-3 rounded-lg border border-green-500/20 bg-green-500/5">
                <p className="text-xs text-slate-400 mb-1">Real (Exchange)</p>
                <p className="text-2xl font-black text-green-400">
                  ${Number(cexBalance?.realBalance || 0).toFixed(2)} <span className="text-sm text-slate-500">USDT</span>
                </p>
              </div>

              <div className="p-3 rounded-lg border border-white/10 bg-slate-800/30">
                <p className="text-xs text-slate-400 mb-1">Virtual (Simulación)</p>
                <p className="text-2xl font-black text-white">
                  ${Number(cexBalance?.amount || 0).toFixed(2)}
                </p>
              </div>
            </div>
          )}
        </Card>

        <Card className="p-6 border-l-4 border-l-pink-500 bg-slate-900 border-slate-800">
          <h3 className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-4">Balance DEX</h3>
          {balancesLoading ? (
            <div className="h-12 bg-slate-800/50 animate-pulse rounded" />
          ) : (
            <div>
              <p className="text-xs text-slate-500 mb-1">Virtual (Simulación)</p>
              <p className="text-3xl font-black text-white">
                {Number(dexBalance?.amount || 0).toFixed(4)} <span className="text-lg text-slate-500">SOL</span>
              </p>
            </div>
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard
          icon={Zap}
          label="Total Operaciones"
          value={stats.totalTrades}
        />
        <StatCard
          icon={TrendingUp}
          label="Win Rate"
          value={`${stats.winRate}%`}
        />
        <StatCard
          icon={DollarSign}
          label="P&L Total"
          value={`$${stats.totalPnL.toFixed(2)}`}
          change={stats.totalPnL >= 0 ? 5 : -3}
        />
        <StatCard
          icon={TrendingDown}
          label="P&L Promedio"
          value={`$${stats.avgPnL.toFixed(2)}`}
        />
      </div>

      <Card className="p-6 bg-slate-900 border-slate-800">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-sm font-bold text-white uppercase tracking-widest">Actividad Reciente</h3>
          <Badge variant="outline" className="text-slate-400 border-slate-700">Live Feed</Badge>
        </div>

        {tradesLoading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-12 bg-slate-800/50 animate-pulse rounded" />
            ))}
          </div>
        ) : trades && trades.length > 0 ? (
          <div className="space-y-2">
            {trades.slice(0, 5).map((trade: any) => (
              <div
                key={trade.id || trade._id}
                className="flex items-center justify-between p-3 bg-slate-800/30 rounded-lg border border-white/5 hover:bg-slate-800/50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className={`p-2 rounded-full ${(trade.side === 'LONG' || trade.side === 'BUY') ? 'bg-green-500/10 text-green-500' : 'bg-red-500/10 text-red-500'}`}>
                    {(trade.side === 'LONG' || trade.side === 'BUY') ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
                  </div>
                  <div>
                    <p className="font-bold text-white text-sm">{trade.symbol}</p>
                    <p className="text-[10px] text-slate-500 uppercase font-mono">
                      {trade.marketType || "SPOT"}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p
                    className={`font-black text-sm ${(trade.pnl || trade.position?.pnl) > 0
                      ? 'text-green-400'
                      : (trade.pnl || trade.position?.pnl) < 0 ? 'text-red-400' : 'text-slate-400'
                      }`}
                  >
                    {((trade.pnl || trade.position?.pnl) ?? 0).toFixed(2)}%
                  </p>
                  <p className="text-[10px] text-slate-600">
                    {trade.createdAt ? new Date(trade.createdAt).toLocaleString() : "-"}
                  </p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-12 text-slate-500">
            <Zap className="mx-auto mb-2 opacity-20" size={32} />
            <p className="text-sm">No hay actividad reciente.</p>
          </div>
        )}
      </Card>
    </div>
  );
}
