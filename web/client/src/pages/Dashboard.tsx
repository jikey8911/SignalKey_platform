import React from 'react';
import { SignalsKeiLayout } from '@/components/SignalsKeiLayout';
import { Card } from '@/components/ui/card';
import { trpc } from '@/lib/trpc';
import { useTrading } from '@/contexts/TradingContext';
import { TrendingUp, TrendingDown, DollarSign, Zap } from 'lucide-react';

export default function Dashboard() {
  const { demoMode } = useTrading();
  const { data: balances, isLoading: balancesLoading } = trpc.trading.getBalances.useQuery();
  const { data: trades, isLoading: tradesLoading } = trpc.trading.getTrades.useQuery();

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
              className={`text-xs mt-2 ${
                change >= 0 ? 'text-green-600' : 'text-red-600'
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

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card className="p-6 border-2 border-primary/20">
            <h3 className="text-lg font-semibold text-foreground mb-4">Balance CEX</h3>
            {balancesLoading ? (
              <div className="h-12 bg-muted animate-pulse rounded" />
            ) : (
              <div>
                <p className="text-3xl font-bold text-primary">
                  ${balances?.find((b: any) => b.marketType === 'CEX')?.amount.toFixed(2) || '0.00'}
                </p>
                <p className="text-sm text-muted-foreground mt-2">
                  {demoMode ? 'Balance Virtual' : 'Balance Real'}
                </p>
              </div>
            )}
          </Card>

          <Card className="p-6 border-2 border-primary/20">
            <h3 className="text-lg font-semibold text-foreground mb-4">Balance DEX</h3>
            {balancesLoading ? (
              <div className="h-12 bg-muted animate-pulse rounded" />
            ) : (
              <div>
                <p className="text-3xl font-bold text-primary">
                  {balances?.find((b: any) => b.marketType === 'DEX')?.amount.toFixed(4) || '0.0000'} SOL
                </p>
                <p className="text-sm text-muted-foreground mt-2">
                  {demoMode ? 'Balance Virtual' : 'Balance Real'}
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
                      className={`font-semibold ${
                        trade.pnl && trade.pnl > 0
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
