import React, { useEffect, useState, useMemo } from 'react';
import { SignalsKeiLayout } from '@/components/SignalsKeiLayout';
import { Card } from '@/components/ui/card';
import { trpc } from '@/lib/trpc';
import { useTrading } from '@/contexts/TradingContext';
import { useAuth } from '@/_core/hooks/useAuth';
import { TrendingUp, TrendingDown, DollarSign, Zap } from 'lucide-react';
import { useSocket } from '@/_core/hooks/useSocket';
import { useQueryClient } from '@tanstack/react-query';
import { CONFIG } from '@/config';

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
    <Card className="p-6 border-l-4 border-l-purple-500 shadow-sm">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 gap-4">
        <div>
          <h3 className="text-lg font-bold flex items-center gap-2">
            <Zap className="text-purple-500" />
            Meta-Selector AI
          </h3>
          <p className="text-xs text-muted-foreground">
            Predice la MEJOR estrategia para el mercado actual usando LSTM.
          </p>
        </div>
        <div className="flex gap-2 w-full md:w-auto">
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            className="bg-background border border-input rounded px-3 py-1 text-sm w-full md:w-32"
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
          <div className="flex items-center justify-between p-4 bg-muted/40 rounded-lg border border-border">
            <div>
              <span className="text-xs font-semibold uppercase text-muted-foreground block mb-1">Estrategia Ganadora</span>
              <span className="text-xl font-bold text-foreground">
                {result.strategy_selected || 'HOLD'}
              </span>
            </div>
            <div className="text-right">
              <span className="text-xs font-semibold uppercase text-muted-foreground block mb-1">Confianza</span>
              <span className="text-2xl font-bold text-purple-500">
                {Number(result.confidence).toFixed(1)}%
              </span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className={`p-3 rounded-lg border text-center ${result.decision === 'BUY' ? 'bg-green-500/10 border-green-500/30 text-green-600' :
                result.decision === 'SELL' ? 'bg-red-500/10 border-red-500/30 text-red-600' :
                  'bg-gray-500/10 border-gray-500/30 text-gray-400'
              }`}>
              <div className="text-xs font-semibold uppercase mb-1">Señal Final</div>
              <div className="font-black text-lg">{result.decision}</div>
            </div>
            <div className="p-3 bg-muted/20 rounded-lg border border-border text-xs">
              <div className="font-semibold mb-2 text-muted-foreground">Probabilidades:</div>
              {result.class_probabilities && result.class_probabilities.map((p: number, i: number) => {
                const labels = ['HOLD', 'RSI', 'EMA', 'BREAKOUT'];
                return (
                  <div key={i} className="flex justify-between items-center mb-1">
                    <span>{labels[i]}</span>
                    <span className="font-mono text-foreground">{(p * 100).toFixed(0)}%</span>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      ) : (
        <div className="text-center py-8 text-muted-foreground bg-muted/10 rounded-lg border border-dashed border-border/50">
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
  const { data: balances, isLoading: balancesLoading } = trpc.trading.getBalances.useQuery();
  const { data: trades, isLoading: tradesLoading } = trpc.trading.getTrades.useQuery();
  const [connectionStatus, setConnectionStatus] = useState<any>(null);
  const { lastMessage } = useSocket(user?.openId);

  // Initial status fetch
  useEffect(() => {
    const fetchStatus = async () => {
      if (!user?.openId) return;
      try {
        const res = await fetch(`${CONFIG.API_BASE_URL}/status/${user.openId}`);
        const data = await res.json();
        setConnectionStatus(data);
      } catch (e) {
        console.error('Error fetching initial status:', e);
      }
    };
    fetchStatus();
  }, [user?.openId]);

  // Listen for socket updates
  useEffect(() => {
    if (!lastMessage) return;

    const { event, data } = lastMessage;

    if (event === 'status_update') {
      setConnectionStatus(data);
    } else if (event === 'balance_update') {
      // Update balances cache
      queryClient.setQueryData(['trading.getBalances'], (oldData: any[] | undefined) => {
        if (!oldData) return [data];
        const exists = oldData.find(b => b.marketType === data.marketType && b.asset === data.asset);
        if (exists) {
          return oldData.map(b => b.marketType === data.marketType && b.asset === data.asset ? { ...b, amount: data.amount } : b);
        } else {
          return [...oldData, data];
        }
      });
    } else if (event === 'bot_update') {
      // Update trades cache
      queryClient.setQueryData(['trading.getTrades'], (oldData: any[] | undefined) => {
        if (!oldData) return [data];
        const exists = oldData.find(t => t.id === data.id);
        if (exists) {
          return oldData.map(t => t.id === data.id ? { ...t, ...data } : t);
        } else {
          return [data, ...oldData];
        }
      });
    }
  }, [lastMessage, queryClient]);

  const stats = useMemo(() => {
    if (!trades || trades.length === 0) {
      return {
        totalTrades: 0,
        winRate: 0,
        totalPnL: 0,
        avgPnL: 0,
      };
    }

    const winningTrades = trades.filter((t: any) => t.pnl && t.pnl > 0).length;
    const totalPnL = trades.reduce((sum: number, t: any) => sum + (t.pnl || 0), 0);
    const avgPnL = totalPnL / trades.length;

    return {
      totalTrades: trades.length,
      winRate: Math.round((winningTrades / trades.length) * 100),
      totalPnL,
      avgPnL,
    };
  }, [trades]);

  const StatCard = ({ icon: Icon, label, value, change }: any) => (
    <Card className="p-6">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-muted-foreground mb-2">{label}</p>
          <p className="text-2xl font-bold text-foreground">{value}</p>
          {change !== undefined && (
            <p
              className={`text-xs mt-2 ${change >= 0 ? 'text-green-600' : 'text-red-600'
                }`}
            >
              {change >= 0 ? '↑' : '↓'} {Math.abs(change)}%
            </p>
          )}
        </div>
        <div className="p-3 bg-primary/10 rounded-lg">
          <Icon className="text-primary" size={24} />
        </div>
      </div>
    </Card>
  );

  return (
    <SignalsKeiLayout currentPage="/">
      <div className="space-y-6">
        {demoMode && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
            <p className="text-sm text-yellow-800">
              <strong>🧪 Modo Demo Activo:</strong> Las operaciones se simulan con balance virtual. No se ejecutarán órdenes reales.
            </p>
          </div>
        )}

        {/* Connection Status */}
        {connectionStatus && (
          <Card className="p-4 bg-muted/30">
            <h3 className="text-sm font-semibold mb-3 text-foreground">Estado de Conexiones</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${connectionStatus.gemini ? 'bg-green-500' : 'bg-red-500'}`} />
                <span className="text-xs text-muted-foreground">Gemini AI</span>
              </div>
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${connectionStatus.exchange ? 'bg-green-500' : 'bg-red-500'}`} />
                <span className="text-xs text-muted-foreground">Exchange</span>
              </div>
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${connectionStatus.telegram ? 'bg-green-500' : 'bg-red-500'}`} />
                <span className="text-xs text-muted-foreground">Telegram</span>
              </div>
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${connectionStatus.gmgn ? 'bg-green-500' : 'bg-red-500'}`} />
                <span className="text-xs text-muted-foreground">GMGN</span>
              </div>
            </div>
          </Card>
        )}

        {/* META-SELECTOR WIDGET (Sprint 4) */}
        <MetaSelectorWidget user={user} />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card className="p-6 border-2 border-primary/20">
            <h3 className="text-lg font-semibold text-foreground mb-4">Balance CEX</h3>
            {balancesLoading ? (
              <div className="h-12 bg-muted animate-pulse rounded" />
            ) : (
              <div className="space-y-3">
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Virtual (Simulación)</p>
                  <p className="text-2xl font-bold text-primary">
                    ${(balances?.find((b: any) => b.marketType === 'CEX')?.amount || 0).toFixed(2)}
                  </p>
                </div>

                {balances?.find((b: any) => b.marketType === 'CEX')?.realBalance !== undefined && (
                  <div className="pt-3 border-t border-border">
                    <p className="text-xs text-muted-foreground mb-1">Real (Exchange)</p>
                    <p className="text-2xl font-bold text-green-600">
                      ${(balances.find((b: any) => b.marketType === 'CEX').realBalance || 0).toFixed(2)}
                    </p>
                    <p className="text-[10px] text-muted-foreground mt-1">USDT</p>
                  </div>
                )}
              </div>
            )}
          </Card>

          <Card className="p-6 border-2 border-primary/20">
            <h3 className="text-lg font-semibold text-foreground mb-4">Balance DEX</h3>
            {balancesLoading ? (
              <div className="h-12 bg-muted animate-pulse rounded" />
            ) : (
              <div>
                <p className="text-xs text-muted-foreground mb-1">Virtual (Simulación)</p>
                <p className="text-2xl font-bold text-primary">
                  {(balances?.find((b: any) => b.marketType === 'DEX')?.amount || 0).toFixed(4)} USDT
                </p>
              </div>
            )}
          </Card>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <StatCard
            icon={Zap}
            label="Total de Bots"
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

        <Card className="p-6">
          <h3 className="text-lg font-semibold text-foreground mb-4">Bots Recientes</h3>
          {tradesLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-12 bg-muted animate-pulse rounded" />
              ))}
            </div>
          ) : trades && trades.length > 0 ? (
            <div className="space-y-2">
              {trades.slice(0, 5).map((trade: any) => (
                <div
                  key={trade.id}
                  className="flex items-center justify-between p-3 bg-muted rounded-lg"
                >
                  <div>
                    <p className="font-semibold text-foreground">{trade.symbol}</p>
                    <p className="text-xs text-muted-foreground">
                      {trade.side} • {trade.marketType}
                    </p>
                  </div>
                  <div className="text-right">
                    <p
                      className={`font-semibold ${trade.pnl && trade.pnl > 0
                        ? 'text-green-600'
                        : 'text-red-600'
                        }`}
                    >
                      {trade.pnl?.toFixed(2) || '0.00'}{trade.pnl !== undefined ? '%' : ''}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {new Date(trade.createdAt).toLocaleTimeString()}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-center text-muted-foreground py-8">
              No hay bots activos aún. ¡Espera las primeras señales!
            </p>
          )}
        </Card>
      </div>
    </SignalsKeiLayout>
  );
}
