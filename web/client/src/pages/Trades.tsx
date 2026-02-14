import { useEffect, useState, useMemo } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { fetchTelegramBots } from '@/lib/api';
import { TrendingUp, TrendingDown, Filter, RefreshCw } from 'lucide-react';
import { useAuth } from '@/_core/hooks/useAuth';
import { useSocket } from '@/_core/hooks/useSocket';
import { useQueryClient, useQuery } from '@tanstack/react-query';

interface Trade {
  id: string;
  symbol: string;
  side: 'BUY' | 'SELL' | 'LONG' | 'SHORT';
  marketType: 'CEX' | 'DEX' | 'SPOT' | 'FUTURES';
  price: number;
  entryPrice?: number;
  currentPrice?: number;
  targetPrice?: number;
  amount: number;
  investment?: number;
  pnl?: number;
  roi?: number;
  status: string;
  isDemo: boolean;
  mode?: string;
  createdAt: string;
  executedAt?: string;
  takeProfits?: any[];
  position?: any;
}

export default function Trades() {
  const { user } = useAuth({ redirectOnUnauthenticated: true });
  const queryClient = useQueryClient();
  const { data: bots, isLoading, refetch } = useQuery({
    queryKey: ['telegram_trades', user?.openId],
    queryFn: () => fetchTelegramBots(),
    enabled: !!user?.openId
  });
  const [filterMarket, setFilterMarket] = useState<'all' | 'CEX' | 'DEX'>('all');
  const [filterSide, setFilterSide] = useState<'all' | 'BUY' | 'SELL'>('all');
  const [filterMode, setFilterMode] = useState<'all' | 'demo' | 'real'>('all');
  const [searchSymbol, setSearchSymbol] = useState('');

  const { lastMessage } = useSocket(user?.openId);

  // Escuchar actualizaciones de bots por socket
  useEffect(() => {
    if (lastMessage && (lastMessage.event === 'telegram_trade_new' || lastMessage.event === 'telegram_trade_update')) {
      const updatedData = lastMessage.data;

      queryClient.setQueryData(['telegram_trades', user?.openId], (oldData: any[] | undefined) => {
        if (!oldData) return [updatedData]; // Si es nuevo y no hay datos

        // Verificar si ya existe (por id o _id)
        const exists = oldData.find(bot => (bot.id === updatedData.id || bot._id === updatedData.id));
        
        if (exists) {
          return oldData.map(bot => {
            if (bot.id === updatedData.id || bot._id === updatedData.id) {
              return { ...bot, ...updatedData };
            }
            return bot;
          });
        } else {
          // Es un nuevo trade
          return [updatedData, ...oldData];
        }
      });
    }
  }, [lastMessage, queryClient, user?.openId]);

  const filteredBots = useMemo(() => {
    if (!bots) return [];
    return bots.filter((bot: any) => {
      const matchMarket = filterMarket === 'all' || (bot.marketType || '').includes(filterMarket);
      const matchSide = filterSide === 'all' || (bot.side || '').includes(filterSide === 'BUY' ? 'LONG' : 'SHORT') || (bot.side === filterSide);
      const isDemo = bot.mode === 'simulated' || bot.isDemo;
      const matchMode = filterMode === 'all' || (filterMode === 'demo' ? isDemo : !isDemo);
      const matchSymbol = searchSymbol === '' || (bot.symbol?.toLowerCase() || "").includes(searchSymbol.toLowerCase());
      return matchMarket && matchSide && matchMode && matchSymbol;
    });
  }, [bots, filterMarket, filterSide, filterMode, searchSymbol]);

  const stats = useMemo(() => {
    if (filteredBots.length === 0) {
      return { totalPnL: 0, winRate: 0, avgPnL: 0 };
    }
    // Calcular PnL total (sumando ROI o PnL absoluto si estuviera disponible)
    // Aquí asumimos que pnl es % ROI para simplificar la vista general
    const totalPnL = filteredBots.reduce((sum: number, t: any) => sum + (t.pnl || t.position?.pnl || 0), 0);
    const winningBots = filteredBots.filter((t: any) => (t.pnl || t.position?.pnl) > 0).length;
    const winRate = Math.round((winningBots / filteredBots.length) * 100);
    const avgPnL = totalPnL / filteredBots.length;
    return { totalPnL, winRate, avgPnL };
  }, [filteredBots]);

  return (
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-start">
        <div>
          <h2 className="text-3xl font-bold text-slate-100 mb-2">Trades Activos</h2>
          <p className="text-slate-400">
            Gestión de operaciones en tiempo real (Telegram, CEX y DEX)
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 px-3 py-1 bg-green-500/10 border border-green-500/20 rounded-full">
            <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
            <span className="text-[10px] font-bold text-green-400 uppercase tracking-wider">Live</span>
          </div>
          <Button
            variant="outline"
            size="icon"
            onClick={() => refetch()}
            disabled={isLoading}
            className="border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700"
          >
            <RefreshCw size={16} className={isLoading ? "animate-spin" : ""} />
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="p-4 bg-slate-800/50 border-slate-700">
          <p className="text-sm text-slate-400 mb-1">P&L Total (ROI)</p>
          <p className={`text-2xl font-bold ${stats.totalPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {stats.totalPnL.toFixed(2)}%
          </p>
        </Card>
        <Card className="p-4 bg-slate-800/50 border-slate-700">
          <p className="text-sm text-slate-400 mb-1">Win Rate</p>
          <p className="text-2xl font-bold text-blue-400">{stats.winRate}%</p>
        </Card>
        <Card className="p-4 bg-slate-800/50 border-slate-700">
          <p className="text-sm text-slate-400 mb-1">Promedio</p>
          <p className={`text-2xl font-bold ${stats.avgPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {stats.avgPnL.toFixed(2)}%
          </p>
        </Card>
      </div>

      {/* Filters */}
      <Card className="p-4 bg-slate-900 border-slate-800">
        <div className="flex items-center gap-2 mb-4">
          <Filter size={20} className="text-slate-400" />
          <h3 className="font-semibold text-slate-200">Filtros</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div>
            <label className="text-sm text-slate-500 mb-2 block">Símbolo</label>
            <input
              type="text"
              placeholder="BTC, ETH..."
              value={searchSymbol}
              onChange={(e) => setSearchSymbol(e.target.value)}
              className="w-full px-3 py-2 border border-slate-700 rounded-lg bg-slate-800 text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="text-sm text-slate-500 mb-2 block">Mercado</label>
            <select
              value={filterMarket}
              onChange={(e) => setFilterMarket(e.target.value as any)}
              className="w-full px-3 py-2 border border-slate-700 rounded-lg bg-slate-800 text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">Todos</option>
              <option value="CEX">CEX</option>
              <option value="DEX">DEX</option>
            </select>
          </div>
          {/* ... otros filtros ... */}
        </div>
      </Card>

      {/* Bots Table */}
      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-16 bg-slate-800 animate-pulse rounded-lg" />
          ))}
        </div>
      ) : filteredBots.length > 0 ? (
        <Card className="overflow-hidden border-slate-800 bg-slate-900">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-700 bg-slate-800/50">
                  <th className="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Símbolo</th>
                  <th className="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Lado</th>
                  <th className="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Tipo</th>
                  <th className="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Entrada</th>
                  <th className="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Actual</th>
                  <th className="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">TPs</th>
                  <th className="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Inv.</th>
                  <th className="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">ROI</th>
                  <th className="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Modo</th>
                  <th className="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Estado</th>
                  <th className="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Actividad</th>
                  <th className="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Fecha</th>
                </tr>
              </thead>
              <tbody>
                {filteredBots.map((bot: any) => (
                  <tr key={bot.id || bot._id} className="border-b border-slate-800 hover:bg-slate-800/30 transition-colors">
                    <td className="px-6 py-4 text-sm font-bold text-white">{bot.symbol}</td>
                    <td className="px-6 py-4 text-sm">
                      {bot.side ? (
                        <div className="flex items-center gap-2">
                          {bot.side === 'LONG' ? <TrendingUp className="text-green-500" size={16} /> : <TrendingDown className="text-red-500" size={16} />}
                          <span className={bot.side === 'LONG' ? 'text-green-500' : 'text-red-500'}>{bot.side}</span>
                        </div>
                      ) : (
                        <span className="text-slate-500">—</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-300">{bot.marketType}</td>
                    <td className="px-6 py-4 text-sm text-slate-300 font-mono">${(bot.entryPrice ?? 0).toFixed(4)}</td>
                    <td className="px-6 py-4 text-sm font-mono text-slate-300">
                       ${(bot.position?.currentPrice ?? bot.currentPrice ?? 0).toFixed(4)}
                    </td>
                    <td className="px-6 py-4 text-sm text-blue-400 text-xs">
                        {bot.takeProfits?.length} Niveles
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-300">${(bot.investment ?? bot.amount ?? 0).toFixed(0)}</td>
                    <td className="px-6 py-4 text-sm font-bold">
                        <span className={(bot.roi ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}>
                            {(bot.roi ?? 0).toFixed(2)}%
                        </span>
                    </td>
                    <td className="px-6 py-4 text-sm">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                            (bot.mode === 'simulated' || bot.isDemo) ? 'bg-yellow-500/10 text-yellow-500 border border-yellow-500/20' : 'bg-red-500/10 text-red-500 border border-red-500/20'
                        }`}>
                            {(bot.mode === 'simulated' || bot.isDemo) ? 'DEMO' : 'REAL'}
                        </span>
                    </td>
                    <td className="px-6 py-4 text-sm">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                            bot.status === 'active' ? 'bg-green-500/10 text-green-500' : 
                            bot.status === 'waiting_entry' ? 'bg-blue-500/10 text-blue-500' :
                            bot.status === 'paused' ? 'bg-slate-700 text-slate-300' :
                            'bg-slate-800 text-slate-400'
                        }`}>
                            {bot.status === 'waiting_entry' ? 'ESPERANDO ENTRADA' : (bot.status?.replace('_', ' ') || '—')}
                        </span>
                    </td>
                    <td className="px-6 py-4 text-sm">
                      {(() => {
                        const status = (bot.status || '').toString();

                        const active = (status === 'active' || status === 'waiting_entry');

                        return (
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${
                            active
                              ? 'bg-green-500/10 text-green-500 border-green-500/20'
                              : 'bg-slate-700/40 text-slate-400 border-slate-600/30'
                          }`}>
                            {active ? 'ACTIVO' : 'INACTIVO'}
                          </span>
                        );
                      })()}
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-500">
                        {new Date(bot.createdAt).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : (
        <Card className="p-12 text-center bg-slate-900 border-slate-800">
          <p className="text-lg text-slate-500">
            No hay trades activos.
          </p>
        </Card>
      )}
    </div>
  );
}
