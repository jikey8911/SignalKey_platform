import { useEffect, useState, useMemo } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { trpc } from '@/lib/trpc';
import { TrendingUp, TrendingDown, Filter, RefreshCw } from 'lucide-react';
import { useAuth } from '@/_core/hooks/useAuth';
import { useSocket } from '@/_core/hooks/useSocket';
import { useQueryClient } from '@tanstack/react-query';

interface Trade {
  id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  marketType: 'CEX' | 'DEX';
  price: number;
  currentPrice?: number;
  targetPrice?: number;
  amount: number;
  pnl?: number;
  status: string;
  isDemo: boolean;
  createdAt: string;
  executedAt?: string;
}

export default function Trades() {
  const { user } = useAuth({ redirectOnUnauthenticated: true });
  const queryClient = useQueryClient();
  const { data: bots, isLoading, refetch } = trpc.trading.getTrades.useQuery();
  const [filterMarket, setFilterMarket] = useState<'all' | 'CEX' | 'DEX'>('all');
  const [filterSide, setFilterSide] = useState<'all' | 'BUY' | 'SELL'>('all');
  const [filterMode, setFilterMode] = useState<'all' | 'demo' | 'real'>('all');
  const [searchSymbol, setSearchSymbol] = useState('');

  const { lastMessage } = useSocket(user?.openId);

  // Escuchar actualizaciones de bots por socket
  useEffect(() => {
    if (lastMessage && (lastMessage.event === 'bot_update' || lastMessage.event === 'trade_update')) {
      const updatedData = lastMessage.data;

      queryClient.setQueryData(['trading.getTrades'], (oldData: any[] | undefined) => {
        if (!oldData) return [];

        return oldData.map(bot => {
          if (bot.id === updatedData.id || bot._id === updatedData.id) {
            return {
              ...bot,
              ...updatedData
            };
          }
          return bot;
        });
      });
    }
  }, [lastMessage, queryClient]);

  const filteredBots = useMemo(() => {
    if (!bots) return [];
    return bots.filter((bot: any) => {
      const matchMarket = filterMarket === 'all' || bot.marketType === filterMarket;
      const matchSide = filterSide === 'all' || bot.side === filterSide;
      const matchMode = filterMode === 'all' || (filterMode === 'demo' ? bot.isDemo : !bot.isDemo);
      const matchSymbol = searchSymbol === '' || (bot.symbol?.toLowerCase() || "").includes(searchSymbol.toLowerCase());
      return matchMarket && matchSide && matchMode && matchSymbol;
    });
  }, [bots, filterMarket, filterSide, filterMode, searchSymbol]);

  const stats = useMemo(() => {
    if (filteredBots.length === 0) {
      return { totalPnL: 0, winRate: 0, avgPnL: 0 };
    }
    const totalPnL = filteredBots.reduce((sum: number, t: any) => sum + (t.pnl || 0), 0);
    const winningBots = filteredBots.filter((t: any) => t.pnl && t.pnl > 0).length;
    const winRate = Math.round((winningBots / filteredBots.length) * 100);
    const avgPnL = totalPnL / filteredBots.length;
    return { totalPnL, winRate, avgPnL };
  }, [filteredBots]);

  return (
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-start">
        <div>
          <h2 className="text-3xl font-bold text-foreground mb-2">Bots Activos</h2>
          <p className="text-muted-foreground">
            Gestión de bots de trading en tiempo real (CEX y DEX)
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 px-3 py-1 bg-green-500/10 border border-green-500/20 rounded-full">
            <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
            <span className="text-[10px] font-bold text-green-600 uppercase tracking-wider">Live</span>
          </div>
          <Button
            variant="outline"
            size="icon"
            onClick={() => refetch()}
            disabled={isLoading}
          >
            <RefreshCw size={16} className={isLoading ? "animate-spin" : ""} />
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="p-4 bg-gradient-to-br from-blue-500/10 to-transparent border-white/5">
          <p className="text-sm text-slate-400 mb-1">P&L Total</p>
          <p className={`text-2xl font-bold ${stats.totalPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            ${(stats.totalPnL ?? 0).toFixed(2)}
          </p>
        </Card>
        <Card className="p-4 bg-gradient-to-br from-blue-500/10 to-transparent border-white/5">
          <p className="text-sm text-slate-400 mb-1">Win Rate</p>
          <p className="text-2xl font-bold text-blue-400">{stats.winRate}%</p>
        </Card>
        <Card className="p-4 bg-gradient-to-br from-blue-500/10 to-transparent border-white/5">
          <p className="text-sm text-slate-400 mb-1">P&L Promedio</p>
          <p className={`text-2xl font-bold ${stats.avgPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            ${(stats.avgPnL ?? 0).toFixed(2)}
          </p>
        </Card>
      </div>

      {/* Filters */}
      <Card className="p-4 bg-slate-900/40 border-white/5">
        <div className="flex items-center gap-2 mb-4">
          <Filter size={20} />
          <h3 className="font-semibold text-foreground">Filtros</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div>
            <label className="text-sm text-slate-400 mb-2 block font-bold uppercase tracking-wider text-[10px]">Símbolo</label>
            <input
              type="text"
              placeholder="BTC, ETH, SOL..."
              value={searchSymbol}
              onChange={(e) => setSearchSymbol(e.target.value)}
              className="w-full px-3 py-2 border border-white/10 rounded-lg bg-slate-950/50 backdrop-blur-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="text-sm text-slate-400 mb-2 block font-bold uppercase tracking-wider text-[10px]">Mercado</label>
            <select
              value={filterMarket}
              onChange={(e) => setFilterMarket(e.target.value as any)}
              className="w-full px-3 py-2 border border-white/10 rounded-lg bg-slate-950/50 backdrop-blur-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">Todos</option>
              <option value="CEX">CEX</option>
              <option value="DEX">DEX</option>
            </select>
          </div>
          <div>
            <label className="text-sm text-slate-400 mb-2 block font-bold uppercase tracking-wider text-[10px]">Tipo</label>
            <select
              value={filterSide}
              onChange={(e) => setFilterSide(e.target.value as any)}
              className="w-full px-3 py-2 border border-white/10 rounded-lg bg-slate-950/50 backdrop-blur-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">Todos</option>
              <option value="BUY">Compra</option>
              <option value="SELL">Venta</option>
            </select>
          </div>
          <div>
            <label className="text-sm text-slate-400 mb-2 block font-bold uppercase tracking-wider text-[10px]">Modo</label>
            <select
              value={filterMode}
              onChange={(e) => setFilterMode(e.target.value as any)}
              className="w-full px-3 py-2 border border-white/10 rounded-lg bg-slate-950/50 backdrop-blur-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">Todos</option>
              <option value="demo">Demo</option>
              <option value="real">Real</option>
            </select>
          </div>
        </div>
      </Card>

      {/* Bots Table */}
      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-16 bg-muted animate-pulse rounded-lg" />
          ))}
        </div>
      ) : filteredBots.length > 0 ? (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Bot (Símbolo)</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Acción</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Mercado</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Entrada</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">P. Actual</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Tails / TP</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Inversión</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">PnL %</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Modo</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Estado</th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-foreground">Inicio</th>
                </tr>
              </thead>
              <tbody>
                {filteredBots.map((bot: any) => (
                  <tr key={bot.id || bot._id} className="border-b border-border hover:bg-muted/50 transition-colors">
                    <td className="px-6 py-4 text-sm font-semibold text-foreground">{bot.symbol}</td>
                    <td className="px-6 py-4 text-sm">
                      <div className="flex items-center gap-2">
                        {bot.side === 'BUY' ? (
                          <TrendingUp className="text-green-400" size={16} />
                        ) : (
                          <TrendingDown className="text-red-400" size={16} />
                        )}
                        <span className={bot.side === 'BUY' ? 'text-green-400' : 'text-red-400'}>
                          {bot.side}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-300">{bot.marketType}</td>
                    <td className="px-6 py-4 text-sm text-slate-300 font-mono">${(bot.entryPrice ?? bot.price ?? 0).toFixed(6)}</td>
                    <td className="px-6 py-4 text-sm font-mono">
                      <span className={
                        bot.currentPrice && (bot.entryPrice || bot.price)
                          ? (bot.side === 'BUY'
                            ? (bot.currentPrice >= (bot.entryPrice || bot.price) ? 'text-green-400' : 'text-red-400')
                            : (bot.currentPrice <= (bot.entryPrice || bot.price) ? 'text-green-400' : 'text-red-400'))
                          : 'text-white'
                      }>
                        ${(bot.currentPrice ?? bot.entryPrice ?? bot.price ?? 0).toFixed(6)}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-blue-400 font-mono">
                      {bot.takeProfits ? (
                        <div className="flex flex-col gap-1">
                          {bot.takeProfits.map((tp: any) => (
                            <span key={tp.level} className={tp.status === 'hit' ? 'line-through text-slate-500' : ''}>
                              TP{tp.level}: ${tp.price?.toFixed(6)}
                            </span>
                          ))}
                        </div>
                      ) : `$${(bot.targetPrice ?? 0).toFixed(6)}`}
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-300">{(bot.amount ?? 0).toFixed(4)}</td>
                    <td className="px-6 py-4 text-sm font-semibold font-mono">
                      <span className={bot.pnl && bot.pnl > 0 ? 'text-green-400' : 'text-red-400'}>
                        {bot.pnl?.toFixed(2)}%
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm">
                      <span className={`px-2 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider border ${bot.isDemo ? 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20' : 'bg-red-500/10 text-red-500 border-red-500/20'
                        }`}>
                        {bot.isDemo ? 'Demo' : 'Real'}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm">
                      <span className={`px-2 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider border ${bot.status === 'active' || bot.status === 'filled'
                        ? 'bg-green-500/10 text-green-500 border-green-500/20'
                        : bot.status === 'pending'
                          ? 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20'
                          : 'bg-red-500/10 text-red-500 border-red-500/20'
                        }`}>
                        {bot.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-muted-foreground">
                      {new Date(bot.createdAt).toLocaleTimeString()}
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
  );
}
