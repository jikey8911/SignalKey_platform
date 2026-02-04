import React, { useState, useEffect, useRef } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Play, BarChart3, TrendingUp, TrendingDown, Loader2, Trophy, BrainCircuit, ChevronRight, Search, RotateCcw } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/_core/hooks/useAuth';
import { Badge } from '@/components/ui/badge';
import { trpc } from '@/lib/trpc';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Progress } from '@/components/ui/progress';
import { CONFIG } from '@/config';

interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

interface Trade {
  time: number;
  price: number;
  side: 'BUY' | 'SELL';
  profit?: number;
  amount?: number;
  avg_price?: number;
  label?: string;
  pnl_percent?: number;
}

interface TournamentResult {
  strategy: string;
  profit_pct: number;
  total_trades: number;
  win_rate: number;
  final_balance: number;
}

interface BacktestResults {
  symbol: string;
  timeframe: string;
  days: number;
  totalTrades: number;
  winRate: number;
  profitFactor: string;
  maxDrawdown: string;
  totalReturn: string;
  sharpeRatio: string;
  candles: Candle[];
  trades: Trade[];
  botConfiguration?: any;
  metrics?: any;
  tournamentResults?: TournamentResult[];
  winner?: TournamentResult;
  strategy_name?: string;
  initial_balance?: number;
  final_balance?: number;
}

interface Exchange {
  exchangeId: string;
  isActive: boolean;
}

interface Symbol {
  symbol: string;
  baseAsset: string;
  quoteAsset: string;
  price: number;
  priceChange: number;
  priceChangePercent: number;
  volume: number;
}

export default function Backtest() {
  const { user } = useAuth();

  // Exchange, Market, Symbol selection
  const [selectedExchange, setSelectedExchange] = useState<string>('');
  const [selectedMarket, setSelectedMarket] = useState<string>('spot');
  const [selectedSymbol, setSelectedSymbol] = useState<string>('');

  // Backtest config
  const [symbol, setSymbol] = useState('BTC/USDT');
  const [timeframe, setTimeframe] = useState('1h');
  const [days, setDays] = useState(30);
  const [isRunning, setIsRunning] = useState(false);
  const [results, setResults] = useState<BacktestResults | null>(null);
  const [initialBalance, setInitialBalance] = useState<number>(10000); // Default 10000
  const [tradeAmount, setTradeAmount] = useState<number>(1000); // Default 1000 for DCA step

  // Symbol Search
  const [symbolSearch, setSymbolSearch] = useState('');

  // Keep legacy virtual balance if needed but prioritize inputs for simulation
  const [virtualBalance, setVirtualBalance] = useState<number>(10000);
  const [loadingBalance, setLoadingBalance] = useState(false);

  // Fetch Exchanges
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [loadingExchanges, setLoadingExchanges] = useState(false);

  useEffect(() => {
    setLoadingExchanges(true);
    fetch(`${CONFIG.API_BASE_URL}/market/exchanges`)
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) {
          // Map string[] to object structure expected by UI
          setExchanges(data.map(e => ({ exchangeId: e, isActive: true })));
        }
      })
      .catch(err => console.error("Error fetching exchanges:", err))
      .finally(() => setLoadingExchanges(false));
  }, []);

  // Fetch Markets
  const [markets, setMarkets] = useState<string[]>([]);
  const [loadingMarkets, setLoadingMarkets] = useState(false);

  useEffect(() => {
    if (!selectedExchange) {
      setMarkets([]);
      return;
    }
    setLoadingMarkets(true);
    fetch(`${CONFIG.API_BASE_URL}/market/exchanges/${selectedExchange}/markets`)
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) setMarkets(data);
      })
      .catch(err => console.error("Error fetching markets:", err))
      .finally(() => setLoadingMarkets(false));
  }, [selectedExchange]);

  // Fetch Symbols
  const [symbols, setSymbols] = useState<Symbol[]>([]);
  const [loadingSymbols, setLoadingSymbols] = useState(false);

  // --- Semi-Auto Access ---
  const [isScanning, setIsScanning] = useState(false);
  const [scanResults, setScanResults] = useState<BacktestResults[]>([]);
  const [scanProgress, setScanProgress] = useState({ current: 0, total: 0 });
  const [selectedResult, setSelectedResult] = useState<BacktestResults | null>(null);

  const handleStartScan = async () => {
    if (!user?.openId || !selectedExchange || !selectedMarket) {
      toast.error("Configuración incompleta");
      return;
    }

    setIsScanning(true);
    setScanResults([]);

    // Filter symbols to scan (e.g., exclude outliers if needed, currently taking all valid ones)
    // We limit to top 20 for Demo purposes or use pagination in real scenario? 
    // User asked for "ALL symbols", but browser might choke on 500 requests at once.
    // We'll execute them mostly strictly sequential to avoid rate limits/DoS.
    const targetSymbols = symbols.map(s => s.symbol).slice(0, 50); // LIMIT 50 for SAFETY during Dev
    setScanProgress({ current: 0, total: targetSymbols.length });

    for (let i = 0; i < targetSymbols.length; i++) {
      const sym = targetSymbols[i];
      try {
        // Call Backtest API
        const response = await fetch(
          `${CONFIG.API_BASE_URL}/backtest/run?` + new URLSearchParams({
            symbol: sym,
            exchange_id: selectedExchange,
            days: days.toString(),
            timeframe: timeframe,
            initial_balance: initialBalance.toString(),
            trade_amount: tradeAmount.toString()
          }), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include'
        }
        );

        if (response.ok) {
          const data = await response.json();

          // Transform Data (Reuse logic from single run)
          const transformedTrades: Trade[] = data.trades?.map((t: any) => ({
            time: (typeof t.time === 'string' ? new Date(t.time).getTime() : t.time * 1000),
            price: t.price,
            side: t.type as 'BUY' | 'SELL',
            profit: t.pnl,
            amount: t.amount,
            avg_price: t.avg_price,
            label: t.label,
            pnl_percent: t.pnl_percent
          })) || [];

          const candles: Candle[] = data.chart_data?.map((c: any) => ({
            time: c.time * 1000,
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close
          })) || [];

          const result: BacktestResults = {
            symbol: data.symbol || sym,
            timeframe,
            days,
            totalTrades: data.metrics?.total_trades || 0,
            winRate: data.metrics?.win_rate || 0,
            profitFactor: data.metrics?.profit_factor?.toString() || '0',
            maxDrawdown: data.metrics?.max_drawdown?.toFixed(2) || '0',
            totalReturn: data.metrics?.profit_pct?.toFixed(2) || '0',
            sharpeRatio: data.metrics?.sharpe_ratio?.toString() || '0',
            candles,
            trades: transformedTrades,
            botConfiguration: data.bot_configuration,
            metrics: data.metrics,
            tournamentResults: data.tournament_results,
            winner: data.winner,
            strategy_name: data.strategy_name || "Unknown",
            initial_balance: data.initial_balance,
            final_balance: data.final_balance
          };

          setScanResults(prev => {
            const newResults = [...prev, result];
            // Sort descending by Total Return
            return newResults.sort((a, b) => parseFloat(b.totalReturn) - parseFloat(a.totalReturn));
          });
        }

      } catch (e) {
        console.error(`Error scanning ${sym}`, e);
      } finally {
        setScanProgress(prev => ({ ...prev, current: prev.current + 1 }));
      }
    }

    setIsScanning(false);
    toast.success("Escaneo de mercado completado");
  };

  useEffect(() => {
    if (!selectedExchange || !selectedMarket) return;
    setLoadingSymbols(true);
    fetch(`${CONFIG.API_BASE_URL}/market/exchanges/${selectedExchange}/markets/${selectedMarket}/symbols`)
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) {
          // Map string[] to Symbol interface
          // Note: The API returns strings, so we mock price/change data or leave 0
          const mapped: Symbol[] = data.map(s => ({
            symbol: s,
            baseAsset: s.split('/')[0] || '',
            quoteAsset: s.split('/')[1] || '',
            price: 0,
            priceChange: 0,
            priceChangePercent: 0,
            volume: 0
          }));
          setSymbols(mapped);
        }
      })
      .catch(err => console.error("Error fetching symbols:", err))
      .finally(() => setLoadingSymbols(false));
  }, [selectedExchange, selectedMarket]);

  // Auto-select defaults
  useEffect(() => {
    if (exchanges.length > 0 && !selectedExchange) {
      setSelectedExchange(exchanges[0].exchangeId);
    }
  }, [exchanges]);

  // Reset/Default Market
  useEffect(() => {
    if (markets.length > 0 && (!selectedMarket || !markets.includes(selectedMarket))) {
      // Prefer 'spot' if available
      if (markets.includes('spot')) setSelectedMarket('spot');
      else setSelectedMarket(markets[0]);
    }
  }, [markets, selectedMarket]);


  // Fetch Virtual Balance
  useEffect(() => {
    const fetchBalance = async () => {
      if (!user?.openId) return;

      setLoadingBalance(true);
      try {
        const res = await fetch(
          `${CONFIG.API_BASE_URL}/backtest/virtual_balance?market_type=CEX&asset=USDT`
        );
        if (res.ok) {
          const data = await res.json();
          setVirtualBalance(data.balance || 10000);
        }
      } catch (e) {
        console.error('Error fetching virtual balance:', e);
      } finally {
        setLoadingBalance(false);
      }
    };

    if (user?.openId) {
      fetchBalance();
    }
  }, [user]);

  const handleRunBacktest = async () => {
    if (!user?.openId) {
      toast.error('Usuario no autenticado');
      return;
    }

    if (!selectedSymbol) {
      toast.error('Por favor selecciona un símbolo');
      return;
    }

    setIsRunning(true);
    const toastId = toast.loading(`Ejecutando Backtest Tournament...`);

    try {
      // Llamar al endpoint real de backtesting
      const response = await fetch(
        `${CONFIG.API_BASE_URL}/backtest/run?` + new URLSearchParams({
          symbol: selectedSymbol,
          exchange_id: selectedExchange || 'binance',
          days: days.toString(),
          timeframe: timeframe,
          initial_balance: initialBalance.toString(),
          trade_amount: tradeAmount.toString()
        }),
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          credentials: 'include'
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Error al ejecutar backtesting');
      }

      const data = await response.json();

      // Transformar datos del backend al formato del frontend
      const transformedTrades: Trade[] = data.trades?.map((t: any) => ({
        time: (typeof t.time === 'string' ? new Date(t.time).getTime() : t.time * 1000),
        price: t.price,
        side: t.type as 'BUY' | 'SELL',
        profit: t.pnl,
        amount: t.amount,
        avg_price: t.avg_price,
        label: t.label,
        pnl_percent: t.pnl_percent
      })) || [];

      // Sort trades: Newest first (Descending)
      // Tie-breaker: OPEN/DCA events are "Newer" than CLOSE events in the same tick.
      transformedTrades.sort((a, b) => {
        if (b.time !== a.time) {
          return b.time - a.time;
        }
        // Same time: Determine sequence
        // We want [OPEN, CLOSE] order in the table (Top to Bottom)
        // implying OPEN is newer than CLOSE.
        const isCloseA = a.label?.includes('CLOSE') || false;
        const isCloseB = b.label?.includes('CLOSE') || false;

        if (isCloseA && !isCloseB) return 1; // A (Close) is Older -> Move down (Positive index)
        if (!isCloseA && isCloseB) return -1; // B (Close) is Older -> Move down
        return 0;
      });

      const candles: Candle[] = data.chart_data?.map((c: any) => ({
        time: c.time * 1000,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close
      })) || [];

      const backtestResults: BacktestResults = {
        symbol: data.symbol || selectedSymbol,
        timeframe,
        days,
        totalTrades: data.metrics?.total_trades || 0,
        winRate: data.metrics?.win_rate || 0,
        profitFactor: data.metrics?.profit_factor?.toString() || '0',
        maxDrawdown: data.metrics?.max_drawdown?.toFixed(2) || '0',
        totalReturn: data.metrics?.profit_pct?.toFixed(2) || '0',
        sharpeRatio: data.metrics?.sharpe_ratio?.toString() || '0',
        candles,
        trades: transformedTrades,
        botConfiguration: data.bot_configuration,
        metrics: data.metrics,
        tournamentResults: data.tournament_results,
        winner: data.winner,
        strategy_name: data.strategy_name,
        initial_balance: data.initial_balance,
        final_balance: data.final_balance
      };

      setResults(backtestResults);
      toast.success(
        `Tournament completado. Ganador: ${data.strategy_name}`,
        { id: toastId }
      );
    } catch (error: any) {
      console.error('Error en backtesting:', error);
      toast.error(error.message || 'Error al ejecutar backtesting', { id: toastId });
    } finally {
      setIsRunning(false);
    }
  };

  const StatBox = ({ label, value, unit = '', valueColor = 'text-foreground' }: any) => (
    <Card className="p-4 bg-gradient-to-br from-primary/10 to-primary/5">
      <p className="text-sm text-muted-foreground mb-1">{label}</p>
      <p className={`text-2xl font-bold ${valueColor}`}>
        {value}{unit}
      </p>
    </Card>
  );

  // --- Enhanced Chart Logic ---
  const [zoom, setZoom] = useState(1);
  const [panIndex, setPanIndex] = useState(0);
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);

  // Reset zoom/pan when results change
  useEffect(() => {
    setZoom(1);
    setPanIndex(0);
    setSelectedTrade(null);
  }, [results]);

  const handleTradeClick = (trade: Trade) => {
    setSelectedTrade(trade);
    if (!results) return;

    // Auto-pan to the trade
    const tradeIndex = results.candles.findIndex(c => c.time === trade.time);
    if (tradeIndex !== -1) {
      // Center the trade in the current view
      const visibleCount = Math.floor(results.candles.length / zoom);
      let newPan = tradeIndex - Math.floor(visibleCount / 2);

      // Clamp
      newPan = Math.max(0, Math.min(newPan, results.candles.length - visibleCount));
      setPanIndex(newPan);
    }
  };

  const CandleChart = ({ candles, trades }: { candles: Candle[]; trades: Trade[] }) => {
    const visibleCount = Math.floor(candles.length / zoom);
    // Ensure panIndex is valid
    const safePanIndex = Math.max(0, Math.min(panIndex, candles.length - visibleCount));

    const visibleCandles = candles.slice(safePanIndex, safePanIndex + visibleCount);

    if (visibleCandles.length === 0) return <div>No data to display</div>;

    const minPrice = Math.min(...visibleCandles.map(c => c.low)) * 0.99;
    const maxPrice = Math.max(...visibleCandles.map(c => c.high)) * 1.01;
    const priceRange = maxPrice - minPrice || 1;

    const width = 1000;
    const height = 400;
    const candleWidth = width / visibleCandles.length;
    const padding = 40;

    const priceToY = (price: number) => {
      return height - ((price - minPrice) / priceRange) * (height - padding * 2) - padding;
    };

    const indexToX = (i: number) => {
      return (i / visibleCandles.length) * (width - padding * 2) + padding;
    };

    return (
      <div className="relative border border-border rounded-lg bg-background overflow-hidden">
        {/* Controls Overlay */}
        <div className="absolute top-2 right-2 flex gap-2 z-10">
          <Button variant="secondary" size="sm" onClick={() => setZoom(z => Math.max(1, z - 1))}>-</Button>
          <span className="bg-background/80 px-2 py-1 rounded text-xs flex items-center">x{zoom}</span>
          <Button variant="secondary" size="sm" onClick={() => setZoom(z => Math.min(20, z + 1))}>+</Button>
        </div>

        {/* Pan Slider */}
        {zoom > 1 && (
          <div className="absolute bottom-2 left-10 right-10 z-10">
            <input
              type="range"
              min={0}
              max={candles.length - visibleCount}
              value={safePanIndex}
              onChange={(e) => setPanIndex(parseInt(e.target.value))}
              className="w-full opacity-50 hover:opacity-100 transition-opacity"
            />
          </div>
        )}

        <svg width="100%" viewBox={`0 0 ${width} ${height}`} className="w-full h-auto">
          {/* Grid */}
          {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
            const y = height - (ratio * (height - padding * 2)) - padding;
            const price = minPrice + ratio * priceRange;
            return (
              <g key={`grid-${ratio}`}>
                <line x1={padding} y1={y} x2={width - padding} y2={y} stroke="currentColor" strokeOpacity="0.1" strokeDasharray="5,5" strokeWidth="1" />
                <text x={5} y={y + 4} fontSize="10" fill="currentColor" className="text-muted-foreground">
                  ${price.toFixed(price < 1 ? 4 : 2)}
                </text>
              </g>
            );
          })}

          {/* Candles */}
          {visibleCandles.map((candle, i) => {
            const x = indexToX(i) + candleWidth / 2;
            const openY = priceToY(candle.open);
            const closeY = priceToY(candle.close);
            const highY = priceToY(candle.high);
            const lowY = priceToY(candle.low);
            const isGreen = candle.close >= candle.open;
            const color = isGreen ? '#10b981' : '#ef4444';

            return (
              <g key={`candle-${i}`}>
                <line x1={x} y1={highY} x2={x} y2={lowY} stroke={color} strokeWidth="1" />
                <rect
                  x={x - (candleWidth * 0.4)}
                  y={Math.min(openY, closeY)}
                  width={candleWidth * 0.8}
                  height={Math.abs(closeY - openY) || 1}
                  fill={color}
                  stroke={color}
                  strokeWidth="1"
                />
              </g>
            );
          })}

          {/* Trade Markers (Filtered for visible range) */}
          {trades.map((trade, idx) => {
            // Find index in FULL array
            const realIndex = candles.findIndex(c => c.time === trade.time);
            if (realIndex === -1) return null;

            // Check if visible
            if (realIndex < safePanIndex || realIndex >= safePanIndex + visibleCount) return null;

            // Map to visible index
            const visibleIndex = realIndex - safePanIndex;

            const x = indexToX(visibleIndex) + candleWidth / 2;
            const y = priceToY(trade.price);
            const isBuy = trade.side === 'BUY';
            const markerColor = isBuy ? '#3b82f6' : '#f59e0b';
            const isSelected = selectedTrade === trade;

            return (
              <g
                key={`trade-${idx}`}
                onClick={() => setSelectedTrade(trade)}
                className="cursor-pointer hover:opacity-80"
                style={{ transition: 'all 0.2s' }}
              >
                {isSelected && (
                  <circle cx={x} cy={y} r={12} fill="none" stroke="currentColor" strokeWidth="2" strokeDasharray="2,2" className="animate-pulse text-white" />
                )}
                <circle cx={x} cy={y} r={isBuy ? 6 : 6} fill={markerColor} stroke="white" strokeWidth="1" />

                {/* Simplified Label on Chart to avoid clutter */}
                <text x={x} y={y - 12} fontSize="10" textAnchor="middle" fill={markerColor} fontWeight="bold">
                  {isBuy ? 'B' : 'S'}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    );
  };

  return (
    <div className="p-6 space-y-6">
      <Tabs defaultValue="backtest" className="w-full">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h2 className="text-3xl font-bold text-foreground mb-2">Backtesting & Semiauto</h2>
            <p className="text-muted-foreground">
              Prueba estrategias o ejecuta operaciones semiautomáticas
            </p>
          </div>
          <TabsList>
            <TabsTrigger value="backtest">Backtest (Symbol)</TabsTrigger>
            <TabsTrigger value="semiauto">Semi-Auto</TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="backtest" className="space-y-6">
          {/* Configuration */}
          <Card className="p-6">
            <h3 className="text-lg font-semibold text-foreground mb-4">⚙️ Configuración</h3>

            {/* Exchange and Market Selection */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <div>
                <label className="block text-sm font-semibold text-foreground mb-2">
                  Exchange
                </label>
                {loadingExchanges ? (
                  <div className="flex items-center gap-2 px-4 py-2 border border-border rounded-lg bg-background">
                    <Loader2 className="animate-spin" size={16} />
                    <span className="text-muted-foreground">Cargando...</span>
                  </div>
                ) : exchanges.length === 0 ? (
                  <div className="px-4 py-2 border border-border rounded-lg bg-background text-muted-foreground">
                    No hay exchanges configurados
                  </div>
                ) : (
                  <select
                    value={selectedExchange}
                    onChange={(e) => setSelectedExchange(e.target.value)}
                    className="w-full px-4 py-2 border border-white/10 rounded-lg bg-slate-900/50 backdrop-blur-sm text-white focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    <option value="">Seleccionar exchange</option>
                    {exchanges.map((ex: Exchange) => (
                      <option key={ex.exchangeId} value={ex.exchangeId}>
                        {ex.exchangeId.toUpperCase()}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              <div>
                <label className="block text-sm font-semibold text-foreground mb-2">
                  Mercado
                </label>
                {loadingMarkets ? (
                  <div className="flex items-center gap-2 px-4 py-2 border border-border rounded-lg bg-background">
                    <Loader2 className="animate-spin" size={16} />
                    <span className="text-muted-foreground">Cargando...</span>
                  </div>
                ) : (
                  <select
                    value={selectedMarket}
                    onChange={(e) => setSelectedMarket(e.target.value)}
                    disabled={!selectedExchange || markets.length === 0}
                    className="w-full px-4 py-2 border border-white/10 rounded-lg bg-slate-900/50 backdrop-blur-sm text-white focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
                  >
                    {markets.map((market: string) => (
                      <option key={market} value={market}>
                        {market.toUpperCase()}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              <div>
                <label className="block text-sm font-semibold text-foreground mb-2">
                  Timeframe
                </label>
                <select
                  value={timeframe}
                  onChange={(e) => setTimeframe(e.target.value)}
                  className="w-full px-4 py-2 border border-white/10 rounded-lg bg-slate-900/50 backdrop-blur-sm text-white focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="1m">1 minuto</option>
                  <option value="5m">5 minutos</option>
                  <option value="15m">15 minutos</option>
                  <option value="1h">1 hora</option>
                  <option value="4h">4 horas</option>
                  <option value="1d">1 día</option>
                </select>
              </div>
            </div>

            {/* Symbols List */}
            {selectedExchange && selectedMarket && (
              <div className="mb-6">
                <div className="flex justify-between items-center mb-2">
                  <label className="block text-sm font-semibold text-foreground">
                    Símbolos Disponibles
                  </label>
                  <div className="flex items-center space-x-2">
                    <Search size={16} className="text-muted-foreground" />
                    <input
                      type="text"
                      placeholder="Buscar símbolo..."
                      value={symbolSearch}
                      onChange={(e) => setSymbolSearch(e.target.value)}
                      className="px-3 py-1 text-sm border border-white/10 rounded-md bg-slate-900/50 backdrop-blur-sm text-white focus:outline-none focus:ring-2 focus:ring-primary w-40"
                    />
                  </div>
                </div>
                {loadingSymbols ? (
                  <div className="flex items-center justify-center gap-2 p-8 border border-border rounded-lg bg-background">
                    <Loader2 className="animate-spin" size={24} />
                    <span className="text-muted-foreground">Cargando símbolos...</span>
                  </div>
                ) : symbols.length === 0 ? (
                  <div className="p-4 border border-border rounded-lg bg-background text-muted-foreground text-center">
                    No hay símbolos disponibles
                  </div>
                ) : (
                  <div className="border border-border rounded-lg bg-background max-h-64 overflow-y-auto">
                    <table className="w-full text-sm">
                      <thead className="sticky top-0 bg-muted border-b border-border">
                        <tr>
                          <th className="text-left py-2 px-4 font-semibold">Símbolo</th>
                          <th className="text-right py-2 px-4 font-semibold">Precio</th>
                          <th className="text-right py-2 px-4 font-semibold">Cambio 24h</th>
                          <th className="text-center py-2 px-4 font-semibold">Acción</th>
                        </tr>
                      </thead>
                      <tbody>
                        {symbols.filter(s => s.symbol.toLowerCase().includes(symbolSearch.toLowerCase())).map((sym: Symbol) => (
                          <tr
                            key={sym.symbol}
                            className="border-b border-border hover:bg-muted/50 cursor-pointer text-foreground"
                            onClick={() => {
                              setSelectedSymbol(sym.symbol);
                              setSymbol(sym.symbol);
                            }}
                          >
                            <td className="py-3 px-4 font-medium">{sym.symbol}</td>
                            <td className="py-3 px-4 text-right">${sym.price.toFixed(2)}</td>
                            <td className={`py-3 px-4 text-right font-semibold ${sym.priceChangePercent >= 0 ? 'text-green-500' : 'text-red-500'
                              }`}>
                              {sym.priceChangePercent >= 0 ? '+' : ''}{sym.priceChangePercent.toFixed(2)}%
                            </td>
                            <td className="py-3 px-4 text-center">
                              {selectedSymbol === sym.symbol && (
                                <span className="text-xs bg-primary text-primary-foreground px-2 py-1 rounded">
                                  Seleccionado
                                </span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* Days Input */}
            <div className="mb-6">
              <label className="block text-sm font-semibold text-foreground mb-2">
                Días históricos
              </label>
              <input
                type="number"
                value={days}
                onChange={(e) => setDays(parseInt(e.target.value))}
                min="1"
                max="365"
                className="w-full px-4 py-2 border border-white/10 rounded-lg bg-slate-900/50 backdrop-blur-sm text-white focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>

            {/* Simulation Configuration */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
              <div>
                <label className="block text-sm font-semibold text-foreground mb-2">
                  Balance Inicial (USDT)
                </label>
                <input
                  type="number"
                  value={initialBalance}
                  onChange={(e) => setInitialBalance(parseFloat(e.target.value) || 0)}
                  className="w-full px-4 py-2 border border-white/10 rounded-lg bg-slate-900/50 backdrop-blur-sm text-white focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              <div>
                <label className="block text-sm font-semibold text-foreground mb-2">
                  Inversión por Entrada (DCA Step)
                </label>
                <input
                  type="number"
                  value={tradeAmount}
                  onChange={(e) => setTradeAmount(parseFloat(e.target.value) || 0)}
                  className="w-full px-4 py-2 border border-white/10 rounded-lg bg-slate-900/50 backdrop-blur-sm text-white focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
            </div>


            <Button
              onClick={handleRunBacktest}
              disabled={isRunning || !selectedSymbol}
              className="flex items-center gap-2 w-full md:w-auto"
            >
              <Play size={18} />
              {isRunning ? 'Ejecutando...' : 'Ejecutar Backtesting'}
            </Button>
          </Card>

          {/* Results */}
          {results ? (
            <>
              {/* Strategy Tournament Results */}
              {results.tournamentResults && (
                <Card className="p-6 mb-6">
                  <h3 className="text-xl font-bold text-foreground mb-4 flex items-center gap-2">
                    <Trophy size={20} className="text-yellow-500" /> Backtest Tournament (Multi-Strategy)
                  </h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="border-b border-border">
                        <tr>
                          <th className="text-left py-2 px-4 text-muted-foreground font-semibold">Estrategia</th>
                          <th className="text-right py-2 px-4 text-muted-foreground font-semibold">PnL %</th>
                          <th className="text-right py-2 px-4 text-muted-foreground font-semibold">Win Rate</th>
                          <th className="text-right py-2 px-4 text-muted-foreground font-semibold">Operaciones</th>
                          <th className="text-right py-2 px-4 text-muted-foreground font-semibold">Balance Final</th>
                        </tr>
                      </thead>
                      <tbody>
                        {results.tournamentResults.map((res, i) => (
                          <tr
                            key={i}
                            className={`border-b border-border transition-colors ${res.strategy === results.strategy_name ? 'bg-yellow-500/10' : 'hover:bg-muted/50'}`}
                          >
                            <td className="py-3 px-4 font-semibold flex items-center gap-2">
                              {res.strategy === results.strategy_name && <Badge className="bg-yellow-500 text-[10px] px-1 h-4">Ganador</Badge>}
                              {res.strategy}
                            </td>
                            <td className={`py-3 px-4 text-right font-bold ${res.profit_pct >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                              {res.profit_pct >= 0 ? '+' : ''}{res.profit_pct}%
                            </td>
                            <td className="py-3 px-4 text-right">{res.win_rate}%</td>
                            <td className="py-3 px-4 text-right">{res.total_trades}</td>
                            <td className="py-3 px-4 text-right font-mono">${res.final_balance.toLocaleString()}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              )}

              {/* Bot Configuration & Deploy Card */}
              {results.botConfiguration && (
                <Card className="p-6 bg-gradient-to-r from-cyan-500/20 to-blue-500/20 border-cyan-500/40 shadow-lg mb-6 animate-in zoom-in-95 duration-300">
                  <div className="flex flex-col md:flex-row justify-between gap-6">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-3">
                        <div className="p-2 bg-cyan-500 rounded-lg">
                          <BrainCircuit size={20} className="text-white" />
                        </div>
                        <div>
                          <h3 className="text-xl font-bold text-foreground">Configuración de Bot Recomendada</h3>
                          <p className="text-xs text-muted-foreground italic">Basada en el mejor desempeño del torneo</p>
                        </div>
                      </div>
                      <div className="bg-background/80 p-4 rounded-xl border border-cyan-500/20 text-sm font-mono space-y-2 shadow-inner">
                        <p><span className="text-cyan-600 dark:text-cyan-400 font-bold">Estrategia:</span> {results.strategy_name}</p>
                        <p><span className="text-muted-foreground">Modelo ID:</span> {results.botConfiguration.model_id}</p>
                        <div className="pt-2">
                          <p className="text-[10px] text-muted-foreground uppercase font-bold mb-1">Parámetros</p>
                          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
                            {Object.entries(results.botConfiguration.parameters || {}).map(([k, v]) => (
                              <div key={k} className="flex justify-between border-b border-border/50 pb-1">
                                <span className="text-muted-foreground">{k}:</span>
                                <span className="text-foreground">{String(v)}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="flex flex-col justify-center items-end gap-4 min-w-[200px]">
                      <div className="text-right">
                        <p className="text-sm text-muted-foreground uppercase font-bold">Rendimiento Tournament</p>
                        <p className="text-4xl font-black text-green-500">+{results.totalReturn}%</p>
                        <p className="text-xs text-muted-foreground">Win Rate: {results.winRate}%</p>
                      </div>
                      <Button
                        onClick={async () => {
                          const toastId = toast.loading("Desplegando bot inteligente...");
                          try {
                            const res = await fetch(`${CONFIG.API_BASE_URL}/backtest/deploy_bot?` + new URLSearchParams({
                              symbol: results.symbol,
                              strategy: results.strategy_name || '',
                              initial_balance: virtualBalance.toString()
                            }), { method: 'POST' });

                            if (!res.ok) throw new Error("Fallo en la conexión");
                            toast.success(`¡Bot ${results.strategy_name} desplegado con éxito!`, { id: toastId });
                          } catch (e: any) {
                            toast.error("Error al desplegar bot: " + e.message, { id: toastId });
                          }
                        }}
                        className="bg-cyan-600 hover:bg-cyan-700 text-white font-bold h-12 px-8 rounded-xl shadow-cyan-500/20 shadow-lg w-full md:w-auto text-lg group"
                      >
                        🚀 Desplegar Bot Ahora
                        <ChevronRight size={18} className="ml-2 group-hover:translate-x-1 transition-transform" />
                      </Button>
                    </div>
                  </div>
                </Card>
              )}

              {/* Results Summary Metrics */}
              <Card className="p-6 mb-6">
                <div className="flex items-center gap-2 mb-6">
                  <BarChart3 className="text-primary" size={24} />
                  <h3 className="text-lg font-semibold text-foreground">Métricas de la Mejor Estrategia ({results.strategy_name})</h3>
                </div>

                <Card className="p-4 mb-6 bg-gradient-to-br from-primary/10 to-primary/5">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <p className="text-sm text-muted-foreground mb-1">Balance Inicial</p>
                      <p className="text-xl font-mono text-foreground font-bold">${results.initial_balance?.toLocaleString() ?? 0}</p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground mb-1">Balance Final</p>
                      <p className={`text-xl font-mono font-bold ${parseFloat(results.totalReturn || '0') >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        ${results.final_balance?.toLocaleString() ?? 0}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground mb-1">Retorno Total</p>
                      <p className={`text-xl font-bold ${parseFloat(results.totalReturn) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {parseFloat(results.totalReturn) >= 0 ? '+' : ''}{results.totalReturn}%
                      </p>
                    </div>
                  </div>
                </Card>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <StatBox label="Total Operaciones" value={results.totalTrades} />
                  <StatBox label="Win Rate" value={`${results.winRate.toFixed(1)}`} unit="%" valueColor="text-primary" />
                  <StatBox label="Profit Factor" value={results.profitFactor} valueColor="text-primary" />
                  <StatBox label="Max Drawdown" value={results.maxDrawdown} unit="%" valueColor="text-red-600" />
                </div>
              </Card>

              {/* Candlestick Chart */}
              <Card className="p-6 mb-6">
                <h3 className="text-lg font-semibold text-foreground mb-4">Gráfico de Velas con Señales</h3>
                <div className="overflow-x-auto">
                  <CandleChart candles={results.candles} trades={results.trades} />
                </div>

                <div className="flex flex-wrap gap-6 mt-4 text-sm">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-blue-500"></div>
                    <span className="text-foreground text-xs">Compra (BUY)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-amber-500"></div>
                    <span className="text-foreground text-xs">Venta (SELL)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 bg-green-500"></div>
                    <span className="text-foreground text-xs">Alcista</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 bg-red-500"></div>
                    <span className="text-foreground text-xs">Bajista</span>
                  </div>
                </div>
              </Card>

              {/* Trade Details Table */}
              <Card className="p-6">
                <h3 className="text-lg font-semibold text-foreground mb-4">Detalles de Operaciones</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="border-b border-border text-xs uppercase text-muted-foreground">
                      <tr>
                        <th className="text-left py-2 px-4 font-bold">Tipo</th>
                        <th className="text-left py-2 px-4 font-bold">Acción</th>
                        <th className="text-right py-2 px-4 font-bold">Cantidad</th>
                        <th className="text-right py-2 px-4 font-bold">Precio Ejecución</th>
                        <th className="text-right py-2 px-4 font-bold">Precio Entrada</th>
                        <th className="text-right py-2 px-4 font-bold">Hora</th>
                        <th className="text-right py-2 px-4 font-bold">Profit</th>
                      </tr>
                    </thead>
                    <tbody>
                      {results.trades.map((trade, index) => (
                        <tr
                          key={index}
                          className={`border-b border-border hover:bg-muted/50 cursor-pointer transition-colors ${selectedTrade === trade ? 'bg-muted/80 border-l-4 border-l-primary' : ''}`}
                          onClick={() => handleTradeClick(trade)}
                        >
                          <td className="py-3 px-4">
                            <div className="flex items-center gap-2">
                              {trade.label?.includes('FLIP') ? (
                                <div className="p-1 bg-purple-500/20 rounded text-purple-400" title="Market Flip / Reversión">
                                  <RotateCcw size={16} />
                                </div>
                              ) : trade.side === 'BUY' ? (
                                <TrendingUp className="text-blue-500" size={16} />
                              ) : (
                                <TrendingDown className="text-amber-500" size={16} />
                              )}
                              <span className="font-semibold">
                                {trade.side}
                                {trade.label?.includes('FLIP') && <span className="text-[10px] ml-1 text-purple-400 font-mono opacity-80">RVR</span>}
                              </span>
                            </div>
                          </td>
                          <td className="py-3 px-4 text-xs font-mono text-muted-foreground">{trade.label || '-'}</td>
                          <td className="py-3 px-4 text-right font-mono">{trade.amount?.toFixed(4) || '-'}</td>
                          <td className="py-3 px-4 text-right font-mono font-medium">${trade.price.toFixed(2)}</td>
                          <td className="py-3 px-4 text-right font-mono text-muted-foreground">{trade.avg_price ? `$${trade.avg_price.toFixed(2)}` : '-'}</td>
                          <td className="py-3 px-4 text-right text-muted-foreground">
                            {new Date(trade.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                            <span className="ml-2 text-[10px] opacity-70">{new Date(trade.time).toLocaleDateString()}</span>
                          </td>
                          <td className={`py-3 px-4 text-right font-bold ${trade.profit !== undefined ? (trade.profit >= 0 ? 'text-green-500' : 'text-red-500') : ''}`}>
                            {trade.profit !== undefined ? (
                              <div className="flex flex-col items-end">
                                <span>{trade.profit >= 0 ? '+' : ''}${trade.profit.toFixed(2)}</span>
                                {trade.pnl_percent !== undefined && (
                                  <span className="text-[10px] opacity-80">
                                    ({trade.pnl_percent >= 0 ? '+' : ''}{trade.pnl_percent.toFixed(2)}%)
                                  </span>
                                )}
                              </div>
                            ) : '-'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>

              {/* Trade Detail Overlay */}
              {selectedTrade && (
                <div className="fixed bottom-6 right-6 z-50">
                  <Card className="p-4 shadow-2xl border-primary/20 bg-background/95 backdrop-blur w-72 animate-in slide-in-from-bottom-5">
                    <div className="flex justify-between items-start mb-2">
                      <h4 className="font-bold flex items-center gap-2">
                        {selectedTrade.side === 'BUY' ? <TrendingUp className="text-blue-500" size={16} /> : <TrendingDown className="text-amber-500" size={16} />}
                        Detalle Operación
                      </h4>
                      <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => setSelectedTrade(null)}>×</Button>
                    </div>
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-muted-foreground font-semibold">Precio:</span>
                        <span className="font-mono text-foreground font-bold">${selectedTrade.price.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground font-semibold">Hora:</span>
                        <span>{new Date(selectedTrade.time).toLocaleString()}</span>
                      </div>
                      {selectedTrade.profit !== undefined && (
                        <div className="pt-2 border-t border-border flex justify-between">
                          <span className="text-muted-foreground font-semibold">PnL:</span>
                          <span className={`font-black ${selectedTrade.profit >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                            {selectedTrade.profit >= 0 ? '+' : ''}{selectedTrade.profit.toFixed(2)}%
                          </span>
                        </div>
                      )}
                    </div>
                  </Card>
                </div>
              )}
            </>
          ) : (
            <Card className="p-16 text-center border-dashed border-2 bg-slate-500/5">
              <BarChart3 className="mx-auto mb-4 text-slate-500 opacity-20" size={64} />
              <p className="text-xl font-bold text-slate-500">
                Listo para el Torneo
              </p>
              <p className="text-sm text-slate-600 max-w-sm mx-auto mt-2">
                Selecciona un símbolo y ejecuta el backtesting para comparar todas las estrategias disponibles y encontrar la ganadora.
              </p>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="semiauto" className="space-y-6">
          <Card className="p-6">
            <h3 className="text-lg font-semibold text-foreground mb-4">⚙️ Configuración Semi-Automática</h3>

            {/* Exchange, Market, Timeframe Selection */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
              {/* Exchange */}
              <div>
                <label className="block text-sm font-semibold text-foreground mb-2">
                  Exchange
                </label>
                {loadingExchanges ? (
                  <div className="flex items-center gap-2 px-4 py-2 border border-border rounded-lg bg-background">
                    <Loader2 className="animate-spin" size={16} />
                    <span className="text-muted-foreground">Cargando...</span>
                  </div>
                ) : exchanges.length === 0 ? (
                  <div className="px-4 py-2 border border-border rounded-lg bg-background text-muted-foreground">
                    No hay exchanges
                  </div>
                ) : (
                  <select
                    value={selectedExchange}
                    onChange={(e) => setSelectedExchange(e.target.value)}
                    className="w-full px-4 py-2 border border-white/10 rounded-lg bg-slate-900/50 backdrop-blur-sm text-white focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    <option value="">Seleccionar</option>
                    {exchanges.map((ex: Exchange) => (
                      <option key={ex.exchangeId} value={ex.exchangeId}>
                        {ex.exchangeId.toUpperCase()}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              {/* Market */}
              <div>
                <label className="block text-sm font-semibold text-foreground mb-2">
                  Mercado
                </label>
                {loadingMarkets ? (
                  <div className="flex items-center gap-2 px-4 py-2 border border-border rounded-lg bg-background">
                    <Loader2 className="animate-spin" size={16} />
                    <span className="text-muted-foreground">Cargando...</span>
                  </div>
                ) : (
                  <select
                    value={selectedMarket}
                    onChange={(e) => setSelectedMarket(e.target.value)}
                    disabled={!selectedExchange}
                    className="w-full px-4 py-2 border border-white/10 rounded-lg bg-slate-900/50 backdrop-blur-sm text-white focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
                  >
                    {markets.map((market: string) => (
                      <option key={market} value={market}>
                        {market.toUpperCase()}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              {/* Timeframe */}
              <div>
                <label className="block text-sm font-semibold text-foreground mb-2">
                  Timeframe
                </label>
                <select
                  value={timeframe}
                  onChange={(e) => setTimeframe(e.target.value)}
                  className="w-full px-4 py-2 border border-white/10 rounded-lg bg-slate-900/50 backdrop-blur-sm text-white focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="1m">1m</option>
                  <option value="5m">5m</option>
                  <option value="15m">15m</option>
                  <option value="1h">1h</option>
                  <option value="4h">4h</option>
                  <option value="1d">1d</option>
                </select>
              </div>

              {/* Days */}
              <div>
                <label className="block text-sm font-semibold text-foreground mb-2">
                  Días
                </label>
                <input
                  type="number"
                  value={days}
                  onChange={(e) => setDays(parseInt(e.target.value))}
                  min="1"
                  max="365"
                  className="w-full px-4 py-2 border border-white/10 rounded-lg bg-slate-900/50 backdrop-blur-sm text-white focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
            </div>

            <div className="flex justify-end">
              <Button
                onClick={handleStartScan}
                disabled={isScanning || !selectedExchange || !selectedMarket}
                className={`w-full md:w-auto ${isScanning ? 'opacity-80' : ''}`}
                size="lg"
              >
                {isScanning ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Escaneando Mercado... ({scanProgress.current}/{scanProgress.total})
                  </>
                ) : (
                  <>
                    <Search className="mr-2 h-4 w-4" /> Iniciar Escaneo de Oportunidades
                  </>
                )}
              </Button>
            </div>
          </Card>

          {/* Progress Bar */}
          {isScanning && (
            <div className="space-y-2">
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>Progreso del escaneo</span>
                <span>{Math.round((scanProgress.current / (scanProgress.total || 1)) * 100)}%</span>
              </div>
              <Progress value={(scanProgress.current / (scanProgress.total || 1)) * 100} className="h-2" />
            </div>
          )}

          {/* Results Table */}
          {scanResults.length > 0 && (
            <Card className="p-0 overflow-hidden">
              <div className="p-4 border-b border-border bg-muted/30">
                <h3 className="font-bold flex items-center gap-2">
                  <Trophy className="text-yellow-500" size={18} />
                  Oportunidades Detectadas
                  <Badge variant="outline" className="ml-2">{scanResults.length}</Badge>
                </h3>
              </div>
              <div className="max-h-[600px] overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-background border-b border-border z-10">
                    <tr>
                      <th className="text-left py-3 px-4 font-semibold">Símbolo</th>
                      <th className="text-left py-3 px-4 font-semibold">Mejor Estrategia</th>
                      <th className="text-right py-3 px-4 font-semibold">PnL %</th>
                      <th className="text-right py-3 px-4 font-semibold">Win Rate</th>
                      <th className="text-right py-3 px-4 font-semibold">Trades</th>
                      <th className="text-center py-3 px-4 font-semibold">Acción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scanResults.map((result, idx) => (
                      <tr key={idx} className="border-b border-border hover:bg-muted/50 transition-colors">
                        <td className="py-3 px-4 font-bold">{result.symbol}</td>
                        <td className="py-3 px-4 text-muted-foreground">{result.strategy_name}</td>
                        <td className={`py-3 px-4 text-right font-bold ${parseFloat(result.totalReturn) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                          {parseFloat(result.totalReturn) > 0 ? '+' : ''}{result.totalReturn}%
                        </td>
                        <td className="py-3 px-4 text-right">{result.winRate}%</td>
                        <td className="py-3 px-4 text-right">{result.totalTrades}</td>
                        <td className="py-3 px-4 text-center">
                          <Button variant="outline" size="sm" onClick={() => setSelectedResult(result)}>
                            Ver Detalles
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {/* Details Modal */}
          <Dialog open={!!selectedResult} onOpenChange={(open) => !open && setSelectedResult(null)}>
            <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2 text-2xl">
                  {selectedResult?.symbol}
                  <Badge variant="outline">{selectedResult?.strategy_name}</Badge>
                </DialogTitle>
                <DialogDescription>
                  Análisis detallado de la simulación
                </DialogDescription>
              </DialogHeader>

              {selectedResult && (
                <div className="space-y-6 mt-4">
                  {/* Stats Grid */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <StatBox label="Retorno Total" value={selectedResult.totalReturn} unit="%" valueColor={parseFloat(selectedResult.totalReturn) >= 0 ? 'text-green-500' : 'text-red-500'} />
                    <StatBox label="Win Rate" value={selectedResult.winRate} unit="%" valueColor="text-blue-500" />
                    <StatBox label="Profit Factor" value={selectedResult.profitFactor} valueColor="text-purple-500" />
                    <StatBox label="Max Drawdown" value={selectedResult.maxDrawdown} unit="%" valueColor="text-orange-500" />
                  </div>

                  {/* Chart */}
                  <div className="h-64 md:h-80 w-full">
                    <CandleChart candles={selectedResult.candles} trades={selectedResult.trades} />
                  </div>

                  {/* Deploy Action */}
                  <div className="flex justify-end gap-3 pt-4 border-t border-border">
                    <Button variant="outline" onClick={() => setSelectedResult(null)}>Cerrar</Button>
                    <Button
                      className="bg-green-600 hover:bg-green-700"
                      onClick={() => {
                        // Deploy Logic specifically for the modal result
                        const deploy = async () => {
                          const toastId = toast.loading(`Desplegando ${selectedResult.symbol}...`);
                          try {
                            const res = await fetch(`${CONFIG.API_BASE_URL}/backtest/deploy_bot?` + new URLSearchParams({
                              symbol: selectedResult.symbol,
                              strategy: selectedResult.strategy_name || '',
                              initial_balance: virtualBalance.toString()
                            }), { method: 'POST' });

                            if (!res.ok) throw new Error("Fallo en la conexión");
                            toast.success(`¡Bot para ${selectedResult.symbol} desplegado!`, { id: toastId });
                            setSelectedResult(null); // Close modal on success
                          } catch (e: any) {
                            toast.error(e.message, { id: toastId });
                          }
                        }
                        deploy();
                      }}
                    >
                      <BrainCircuit className="mr-2 h-4 w-4" /> Desplegar Bot Automático
                    </Button>
                  </div>
                </div>
              )}
            </DialogContent>
          </Dialog>

        </TabsContent>
      </Tabs>
    </div>
  );
}
