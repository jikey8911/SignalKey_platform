import React from 'react';
import { SignalsKeiLayout } from '@/components/SignalsKeiLayout';
import { Card } from '@/components/ui/card';
import { trpc } from '@/lib/trpc';
import { useTrading } from '@/contexts/TradingContext';
import { useAuth } from '@/_core/hooks/useAuth';
import { TrendingUp, TrendingDown, DollarSign, Zap } from 'lucide-react';

export default function Dashboard() {
  const { user } = useAuth({ redirectOnUnauthenticated: true });
  const { demoMode } = useTrading();
  const { data: balances, isLoading: balancesLoading, refetch: refetchBalances } = trpc.trading.getBalances.useQuery();
  const { data: trades, isLoading: tradesLoading } = trpc.trading.getTrades.useQuery();
  const [connectionStatus, setConnectionStatus] = React.useState<any>(null);

  // Fetch connection status
  React.useEffect(() => {
    const fetchStatus = async () => {
      if (!user?.openId) return;
      try {
        const res = await fetch(`http://localhost:8000/status/${user.openId}`);
        const data = await res.json();
        setConnectionStatus(data);
      } catch (e) {
        console.error('Error fetching status:', e);
      }
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 10000); // Update every 10s
    return () => clearInterval(interval);
  }, [user?.openId]);

  // Refetch balances every 30s
  React.useEffect(() => {
    const interval = setInterval(() => {
      refetchBalances();
    }, 30000);
    return () => clearInterval(interval);
  }, [refetchBalances]);

  const stats = React.useMemo(() => {
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
                  {(balances?.find((b: any) => b.marketType === 'DEX')?.amount || 0).toFixed(4)} SOL
                </p>
              </div>
            )}
          </Card>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <StatCard
            icon={Zap}
            label="Total de Trades"
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
          <h3 className="text-lg font-semibold text-foreground mb-4">Trades Recientes</h3>
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
                      ${trade.pnl?.toFixed(2) || '0.00'}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {new Date(trade.createdAt).toLocaleDateString()}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-center text-muted-foreground py-8">
              No hay trades aún. ¡Espera las primeras señales!
            </p>
          )}
        </Card>
      </div>
    </SignalsKeiLayout>
  );
}
