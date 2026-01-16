import React, { useState, useMemo } from 'react';
import { SignalsKeiLayout } from '@/components/SignalsKeiLayout';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { trpc } from '@/lib/trpc';
import { TrendingUp, TrendingDown, Filter } from 'lucide-react';

export default function Trades() {
  const { data: trades, isLoading } = trpc.trading.getTrades.useQuery();
  const [filterMarket, setFilterMarket] = useState<'all' | 'CEX' | 'DEX'>('all');
  const [filterSide, setFilterSide] = useState<'all' | 'BUY' | 'SELL'>('all');
  const [filterMode, setFilterMode] = useState<'all' | 'demo' | 'real'>('all');
  const [searchSymbol, setSearchSymbol] = useState('');

  const filteredTrades = useMemo(() => {
    if (!trades) return [];
    return trades.filter((trade: any) => {
      const matchMarket = filterMarket === 'all' || trade.marketType === filterMarket;
      const matchSide = filterSide === 'all' || trade.side === filterSide;
      const matchMode = filterMode === 'all' || (filterMode === 'demo' ? trade.isDemo : !trade.isDemo);
      const matchSymbol = searchSymbol === '' || trade.symbol.toLowerCase().includes(searchSymbol.toLowerCase());
      return matchMarket && matchSide && matchMode && matchSymbol;
    });
  }, [trades, filterMarket, filterSide, filterMode, searchSymbol]);

  const stats = useMemo(() => {
    if (filteredTrades.length === 0) {
      return { totalPnL: 0, winRate: 0, avgPnL: 0 };
    }
    const totalPnL = filteredTrades.reduce((sum: number, t: any) => sum + (t.pnl || 0), 0);
    const winningTrades = filteredTrades.filter((t: any) => t.pnl && t.pnl > 0).length;
    const winRate = Math.round((winningTrades / filteredTrades.length) * 100);
    const avgPnL = totalPnL / filteredTrades.length;
    return { totalPnL, winRate, avgPnL };
  }, [filteredTrades]);

  return (
    <SignalsKeiLayout currentPage="/trades">
      <div className="space-y-6">
        <div>
          <h2 className="text-3xl font-bold text-foreground mb-2">Historial de Trades</h2>
          <p className="text-muted-foreground">
            Todos los trades ejecutados en modo demo y real
          </p>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card className="p-4 bg-gradient-to-br from-primary/10 to-primary/5">
            <p className="text-sm text-muted-foreground mb-1">P&L Total</p>
            <p className={`text-2xl font-bold ${stats.totalPnL >= 0 ? 'text-green-600' : 'text-red-600'}`}>
              ${stats.totalPnL.toFixed(2)}
            </p>
          </Card>
          <Card className="p-4 bg-gradient-to-br from-primary/10 to-primary/5">
            <p className="text-sm text-muted-foreground mb-1">Win Rate</p>
            <p className="text-2xl font-bold text-primary">{stats.winRate}%</p>
          </Card>
          <Card className="p-4 bg-gradient-to-br from-primary/10 to-primary/5">
            <p className="text-sm text-muted-foreground mb-1">P&L Promedio</p>
            <p className={`text-2xl font-bold ${stats.avgPnL >= 0 ? 'text-green-600' : 'text-red-600'}`}>
              ${stats.avgPnL.toFixed(2)}
            </p>
          </Card>
        </div>

        {/* Filters */}
        <Card className="p-4">
          <div className="flex items-center gap-2 mb-4">
            <Filter size={20} />
            <h3 className="font-semibold text-foreground">Filtros</h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <label className="text-sm text-muted-foreground mb-2 block">Símbolo</label>
              <input
                type="text"
                placeholder="BTC, ETH, SOL..."
                value={searchSymbol}
                onChange={(e) => setSearchSymbol(e.target.value)}
                className="w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div>
              <label className="text-sm text-muted-foreground mb-2 block">Mercado</label>
              <select
                value={filterMarket}
                onChange={(e) => setFilterMarket(e.target.value as any)}
                className="w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="all">Todos</option>
                <option value="CEX">CEX</option>
                <option value="DEX">DEX</option>
              </select>
            </div>
            <div>
              <label className="text-sm text-muted-foreground mb-2 block">Tipo</label>
              <select
                value={filterSide}
                onChange={(e) => setFilterSide(e.target.value as any)}
                className="w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="all">Todos</option>
                <option value="BUY">Compra</option>
                <option value="SELL">Venta</option>
              </select>
            </div>
            <div>
              <label className="text-sm text-muted-foreground mb-2 block">Modo</label>
              <select
                value={filterMode}
                onChange={(e) => setFilterMode(e.target.value as any)}
                className="w-full px-3 py-2 border border-border rounded-lg bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="all">Todos</option>
                <option value="demo">Demo</option>
                <option value="real">Real</option>
              </select>
            </div>
          </div>
        </Card>

        {/* Trades Table */}
        {isLoading ? (
          <div className="space-y-2">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-16 bg-muted animate-pulse rounded-lg" />
            ))}
          </div>
        ) : filteredTrades.length > 0 ? (
          <Card className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border bg-muted/50">
                    <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Símbolo</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Tipo</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Mercado</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Precio</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Cantidad</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">P&L</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Modo</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Estado</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Fecha</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTrades.map((trade: any) => (
                    <tr key={trade.id} className="border-b border-border hover:bg-muted/50 transition-colors">
                      <td className="px-6 py-4 text-sm font-semibold text-foreground">{trade.symbol}</td>
                      <td className="px-6 py-4 text-sm">
                        <div className="flex items-center gap-2">
                          {trade.side === 'BUY' ? (
                            <TrendingUp className="text-green-600" size={16} />
                          ) : (
                            <TrendingDown className="text-red-600" size={16} />
                          )}
                          <span className={trade.side === 'BUY' ? 'text-green-600' : 'text-red-600'}>
                            {trade.side}
                          </span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-sm text-foreground">{trade.marketType}</td>
                      <td className="px-6 py-4 text-sm text-foreground">${trade.price.toFixed(2)}</td>
                      <td className="px-6 py-4 text-sm text-foreground">{trade.amount.toFixed(4)}</td>
                      <td className="px-6 py-4 text-sm font-semibold">
                        <span className={trade.pnl && trade.pnl > 0 ? 'text-green-600' : 'text-red-600'}>
                          ${(trade.pnl || 0).toFixed(2)}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-sm">
                        <span className={`px-2 py-1 rounded-full text-xs font-semibold ${
                          trade.isDemo ? 'bg-yellow-100 text-yellow-800' : 'bg-red-100 text-red-800'
                        }`}>
                          {trade.isDemo ? '🧪 Demo' : '⚠️ Real'}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-sm">
                        <span className={`px-2 py-1 rounded-full text-xs font-semibold ${
                          trade.status === 'filled'
                            ? 'bg-green-100 text-green-800'
                            : trade.status === 'pending'
                            ? 'bg-yellow-100 text-yellow-800'
                            : 'bg-red-100 text-red-800'
                        }`}>
                          {trade.status}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-sm text-muted-foreground">
                        {new Date(trade.createdAt).toLocaleDateString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        ) : (
          <Card className="p-12 text-center">
            <p className="text-lg text-muted-foreground">
              No hay trades que coincidan con los filtros seleccionados.
            </p>
          </Card>
        )}
      </div>
    </SignalsKeiLayout>
  );
}
