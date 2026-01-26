import React, { useState, useEffect } from 'react';
import { SignalsKeiLayout } from '@/components/SignalsKeiLayout';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Play, BarChart3, TrendingUp, TrendingDown, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/_core/hooks/useAuth';
import { trpc } from '@/lib/trpc';
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
  botConfiguration?: any; // New field for Bot Configuration
  metrics?: any; // Raw metrics from backend
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
  const [selectedModel, setSelectedModel] = useState<string>(''); // Selected ML model
  const [isRunning, setIsRunning] = useState(false);
  const [results, setResults] = useState<BacktestResults | null>(null);
  const [mlModels, setMlModels] = useState<any[]>([]);
  const [virtualBalance, setVirtualBalance] = useState<number>(10000);
  const [loadingModels, setLoadingModels] = useState(false);
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

  // Fetch ML Models
  useEffect(() => {
    const fetchModels = async () => {
      setLoadingModels(true);
      try {
        const res = await fetch(`${CONFIG.API_BASE_URL}/backtest/ml_models`);
        if (res.ok) {
          const data = await res.json();
          setMlModels(data.models || []);
        }
      } catch (e) {
        console.error('Error fetching ML models:', e);
      } finally {
        setLoadingModels(false);
      }
    };

    if (user?.openId) {
      fetchModels();
    }
  }, [user]);

  // Fetch Virtual Balance
  useEffect(() => {
    const fetchBalance = async () => {
      if (!user?.openId) return;

      setLoadingBalance(true);
      try {
        const res = await fetch(
          `${CONFIG.API_BASE_URL}/backtest/virtual_balance/${user.openId}?market_type=CEX&asset=USDT`
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
    if (!selectedModel) {
      toast.error('Por favor selecciona un modelo');
      return;
    }


    setIsRunning(true);
    const toastId = toast.loading(`Ejecutando backtesting con modelo...`);

    try {
      // Llamar al endpoint real de backtesting
      const response = await fetch(
        `${CONFIG.API_BASE_URL}/backtest/run?` + new URLSearchParams({
          user_id: user.openId,
          symbol: selectedSymbol,
          exchange_id: selectedExchange || 'binance',
          days: days.toString(),
          timeframe: timeframe,
          model_id: selectedModel
        }),
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Error al ejecutar backtesting');
      }

      const data = await response.json();

      // Transformar datos del backend al formato del frontend
      // El backend retorna trades con formato diferente
      const transformedTrades: Trade[] = data.trades?.map((t: any) => ({
        time: new Date(t.time).getTime(),
        price: t.price,
        side: t.type as 'BUY' | 'SELL',
        profit: t.pnl
      })) || [];

      // Map chart_data from backend to Candle interface
      const candles: Candle[] = data.chart_data?.map((c: any) => ({
        time: c.time * 1000, // Backend sends seconds (timestamp), Frontend expects ms maybe? 
        // Wait, backend sends "int(timestamp)". timestamp() in python is seconds float. 
        // int(ts) is seconds. JS needs milliseconds usually.
        // Let's check existing code. line 273: time: now - ... 3600000. ms.
        // So * 1000 is needed if backend sends seconds.
        // Verify backend: `timestamp = candle['timestamp'].timestamp()` -> float seconds.
        // `point["time"] = int(timestamp)`.
        // So yes, * 1000.
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
        profitFactor: '0', // Not calculated in backend currently
        maxDrawdown: data.metrics?.max_drawdown?.toFixed(2) || '0',
        totalReturn: data.metrics?.profit_pct?.toFixed(2) || '0',
        sharpeRatio: data.metrics?.sharpe_ratio?.toString() || '0',
        candles,
        trades: transformedTrades,
        botConfiguration: data.bot_configuration,
        metrics: data.metrics
      };

      setResults(backtestResults);
      toast.success(
        `Backtesting completado (${(data as any).strategy_name})`,
        { id: toastId }
      );
    } catch (error: any) {
      console.error('Error en backtesting:', error);
      toast.error(error.message || 'Error al ejecutar backtesting', { id: toastId });
    } finally {
      setIsRunning(false);
    }
  };

  const StatBox = ({ label, value, unit = '' }: any) => (
    <div className="p-4 bg-muted rounded-lg">
      <p className="text-xs text-muted-foreground mb-1">{label}</p>
      <p className="text-2xl font-bold text-foreground">
        {value}{unit}
      </p>
    </div>
  );

  const CandleChart = ({ candles, trades }: { candles: Candle[]; trades: Trade[] }) => {
    const minPrice = Math.min(...candles.map(c => c.low)) * 0.99;
    const maxPrice = Math.max(...candles.map(c => c.high)) * 1.01;
    const priceRange = maxPrice - minPrice;

    const width = 1000;
    const height = 400;
    const candleWidth = width / candles.length;
    const padding = 40;

    const priceToY = (price: number) => {
      return height - ((price - minPrice) / priceRange) * (height - padding * 2) - padding;
    };

    const timeToX = (index: number) => {
      return (index / candles.length) * (width - padding * 2) + padding;
    };

    return (
      <svg width={width} height={height} className="border border-border rounded-lg bg-background">
        {/* Grid */}
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
          const y = height - (ratio * (height - padding * 2)) - padding;
          const price = minPrice + ratio * priceRange;
          return (
            <g key={`grid-${ratio}`}>
              <line x1={padding} y1={y} x2={width - padding} y2={y} stroke="#333" strokeDasharray="5,5" strokeWidth="1" />
              <text x={5} y={y + 4} fontSize="12" fill="#666" className="text-muted-foreground">
                ${price.toFixed(0)}
              </text>
            </g>
          );
        })}

        {/* Candles */}
        {candles.map((candle, index) => {
          const x = timeToX(index) + candleWidth / 2;
          const openY = priceToY(candle.open);
          const closeY = priceToY(candle.close);
          const highY = priceToY(candle.high);
          const lowY = priceToY(candle.low);

          const isGreen = candle.close >= candle.open;
          const color = isGreen ? '#10b981' : '#ef4444';

          return (
            <g key={`candle-${index}`}>
              {/* Wick */}
              <line x1={x} y1={highY} x2={x} y2={lowY} stroke={color} strokeWidth="1" />
              {/* Body */}
              <rect
                x={x - candleWidth / 3}
                y={Math.min(openY, closeY)}
                width={candleWidth * 0.66}
                height={Math.abs(closeY - openY) || 1}
                fill={color}
                stroke={color}
                strokeWidth="1"
              />
            </g>
          );
        })}

        {/* Trade Markers */}
        {trades.map((trade, index) => {
          const candleIndex = candles.findIndex(c => c.time === trade.time);
          if (candleIndex === -1) return null;

          const x = timeToX(candleIndex) + candleWidth / 2;
          const y = priceToY(trade.price) - 20;
          const isBuy = trade.side === 'BUY';
          const markerColor = isBuy ? '#3b82f6' : '#f59e0b';

          return (
            <g key={`trade-${index}`}>
              {/* Marker Circle */}
              <circle cx={x} cy={y} r={6} fill={markerColor} stroke="white" strokeWidth="2" />

              {/* Label */}
              <text
                x={x}
                y={y - 15}
                fontSize="11"
                fontWeight="bold"
                textAnchor="middle"
                fill={markerColor}
                className="pointer-events-none"
              >
                {isBuy ? '↓ BUY' : '↑ SELL'}
              </text>

              {/* Profit Label for SELL */}
              {!isBuy && trade.profit !== undefined && (
                <text
                  x={x}
                  y={y - 2}
                  fontSize="10"
                  textAnchor="middle"
                  fill={trade.profit >= 0 ? '#10b981' : '#ef4444'}
                  className="pointer-events-none"
                >
                  {trade.profit >= 0 ? '+' : ''}{trade.profit.toFixed(2)}%
                </text>
              )}
            </g>
          );
        })}

        {/* Axes */}
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="#666" strokeWidth="2" />
        <line x1={padding} y1={padding} x2={padding} y2={height - padding} stroke="#666" strokeWidth="2" />
      </svg>
    );
  };

  return (
    <SignalsKeiLayout currentPage="/backtest">
      <div className="space-y-6 max-w-6xl">
        <div>
          <h2 className="text-3xl font-bold text-foreground mb-2">Backtesting</h2>
          <p className="text-muted-foreground">
            Prueba tus estrategias con datos históricos y visualiza los puntos de entrada y salida
          </p>
        </div>

        {/* Configuration */}
        <Card className="p-6">
          <h3 className="text-lg font-semibold text-foreground mb-4">Configuración</h3>

          {/* Debug Info */}
          <div className="bg-muted/50 p-2 text-xs font-mono mb-4 rounded border border-yellow-500/20 flex justify-between items-center">
            <span>
              DEBUG: Exch={selectedExchange || '?'} | Mkt={selectedMarket || '?'} |
              Syms={symbols.length} | Load={loadingSymbols ? 'YES' : 'NO'}
            </span>
            <Button variant="ghost" size="sm" onClick={() => { }} className="h-6 text-xs">
              Reload
            </Button>
          </div>

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
                  className="w-full px-4 py-2 border border-border rounded-lg bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
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
                  className="w-full px-4 py-2 border border-border rounded-lg bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
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
                className="w-full px-4 py-2 border border-border rounded-lg bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
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
              <label className="block text-sm font-semibold text-foreground mb-2">
                Símbolos Disponibles
              </label>
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
                      {symbols.map((sym: Symbol) => (
                        <tr
                          key={sym.symbol}
                          className="border-b border-border hover:bg-muted/50 cursor-pointer"
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
              className="w-full px-4 py-2 border border-border rounded-lg bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>

          {/* Virtual Balance Display */}
          <div className="mb-6">
            <label className="block text-sm font-semibold text-foreground mb-2">
              Balance Virtual (USDT)
            </label>
            <div className="px-4 py-3 border border-border rounded-lg bg-muted/30">
              {loadingBalance ? (
                <div className="flex items-center gap-2">
                  <Loader2 className="animate-spin" size={16} />
                  <span className="text-muted-foreground">Cargando...</span>
                </div>
              ) : (
                <div className="flex items-center justify-between">
                  <span className="text-2xl font-bold text-primary">
                    ${virtualBalance.toLocaleString()}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    Balance inicial para backtest
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* ML Models Selector */}
          <div className="mb-6">
            <label className="block text-sm font-semibold text-foreground mb-2">
              Modelo
            </label>
            {loadingModels ? (
              <div className="flex items-center gap-2 px-4 py-2 border border-border rounded-lg bg-background">
                <Loader2 className="animate-spin" size={16} />
                <span className="text-muted-foreground">Cargando modelos...</span>
              </div>
            ) : mlModels.length === 0 ? (
              <div className="p-4 border border-yellow-500/20 rounded-lg bg-yellow-500/10 text-yellow-600 text-sm">
                ⚠️ No hay modelos disponibles.
              </div>
            ) : (
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="w-full px-4 py-2 border border-border rounded-lg bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="">Seleccionar modelo...</option>
                {mlModels.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.symbol} - {model.timeframe} (Accuracy: {(model.accuracy * 100).toFixed(1)}%)
                  </option>
                ))}
              </select>
            )}
            {selectedModel && (
              <div className="mt-2 p-2 bg-blue-500/10 border border-blue-500/20 rounded text-xs text-blue-600">
                ℹ️ Modelo seleccionado: {mlModels.find(m => m.id === selectedModel)?.symbol}
              </div>
            )}
          </div>

          <Button
            onClick={handleRunBacktest}
            disabled={isRunning || !selectedSymbol || !selectedModel}
            className="flex items-center gap-2 w-full md:w-auto"
          >
            <Play size={18} />
            {isRunning ? 'Ejecutando...' : 'Ejecutar Backtesting'}
          </Button>
        </Card>

        {/* Results */}
        {results && (
          <>
            {/* Bot Configuration & Deploy Card */}
            {results.botConfiguration && (
              <Card className="p-6 bg-gradient-to-r from-cyan-500/10 to-blue-500/10 border-cyan-500/30 mb-6">
                <div className="flex flex-col md:flex-row justify-between gap-6">
                  <div className="flex-1">
                    <h3 className="text-xl font-bold text-cyan-600 dark:text-cyan-400 flex items-center gap-2 mb-2">
                      🤖 Configuración de Bot Generada
                    </h3>
                    <div className="bg-background/50 p-4 rounded-lg border border-border text-sm font-mono space-y-2">
                      <p><span className="text-muted-foreground">Estrategia:</span> <span className="font-bold">{results.botConfiguration.strategy_type}</span></p>
                      <p><span className="text-muted-foreground">Modelo ID:</span> {results.botConfiguration.model_id}</p>
                      <p><span className="text-muted-foreground">Parámetros:</span></p>
                      <ul className="list-disc pl-5 text-xs text-muted-foreground">
                        {Object.entries(results.botConfiguration.parameters || {}).map(([k, v]) => (
                          <li key={k}>{k}: {String(v)}</li>
                        ))}
                      </ul>
                    </div>
                  </div>

                  <div className="flex flex-col justify-center items-end gap-3">
                    <div className="text-right">
                      <p className="text-sm text-muted-foreground">Rendimiento Estimado</p>
                      <p className="text-2xl font-bold text-green-500">+{results.totalReturn}%</p>
                    </div>
                    <Button
                      onClick={async () => {
                        try {
                          toast.loading("Desplegando bot...");
                          // Using backend endpoint
                          const res = await fetch(`${CONFIG.API_BASE_URL}/backtest/deploy_bot?` + new URLSearchParams({
                            user_id: user?.openId || '',
                            symbol: results.symbol,
                            strategy: results.botConfiguration.strategy_type,
                            initial_balance: virtualBalance.toString()
                          }), { method: 'POST' });

                          if (!res.ok) throw new Error("Error al desplegar");

                          toast.success("Bot desplegado exitosamente! Ver en Dashboard.");
                        } catch (e: any) {
                          toast.error(e.message);
                        }
                      }}
                      className="bg-cyan-600 hover:bg-cyan-700 text-white w-full md:w-auto"
                    >
                      🚀 Desplegar Bot Ahora
                    </Button>
                  </div>
                </div>
              </Card>
            )}

            {/* Strategy Info Card */}
            <Card className="p-6 mb-6 bg-gradient-to-r from-blue-500/5 to-purple-500/5">
              <h3 className="text-lg font-semibold text-foreground mb-3">🧠 Información de la Estrategia</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Estrategia Usada</p>
                  <p className="text-sm font-semibold text-foreground">
                    {(results as any).strategy_name || (results as any).strategy_used}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Balance Inicial</p>
                  <p className="text-sm font-semibold text-primary">
                    ${((results as any).initial_balance || virtualBalance).toLocaleString()}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Balance Final</p>
                  <p className={`text-sm font-semibold ${((results as any).final_balance || 0) >= ((results as any).initial_balance || virtualBalance)
                    ? 'text-green-600'
                    : 'text-red-600'
                    }`}>
                    ${((results as any).final_balance || 0).toLocaleString()}
                  </p>
                </div>
              </div>
              {(results as any).ai_confidence_avg && (
                <div className="mt-4 p-3 bg-blue-500/10 border border-blue-500/20 rounded">
                  <p className="text-xs text-blue-600">
                    🎯 Confianza Promedio de IA: {((results as any).ai_confidence_avg * 100).toFixed(1)}%
                  </p>
                </div>
              )}
            </Card>

            {/* Metrics */}
            <Card className="p-6">
              <div className="flex items-center gap-2 mb-6">
                <BarChart3 className="text-primary" size={24} />
                <h3 className="text-lg font-semibold text-foreground">Resultados</h3>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                <StatBox label="Total de Trades" value={results.totalTrades} />
                <StatBox label="Win Rate" value={results.winRate} unit="%" />
                <StatBox label="Profit Factor" value={results.profitFactor} />
                <StatBox label="Max Drawdown" value={results.maxDrawdown} unit="%" />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <StatBox label="Retorno Total" value={results.totalReturn} unit="%" />
                <StatBox label="Sharpe Ratio" value={results.sharpeRatio} />
              </div>
            </Card>

            {/* Candlestick Chart with Trade Markers */}
            <Card className="p-6">
              <h3 className="text-lg font-semibold text-foreground mb-4">Gráfico de Velas con Señales</h3>
              <div className="overflow-x-auto">
                <CandleChart candles={results.candles} trades={results.trades} />
              </div>

              {/* Legend */}
              <div className="flex gap-6 mt-4 text-sm">
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 rounded-full bg-blue-500"></div>
                  <span className="text-foreground">Señal de Compra (BUY)</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 rounded-full bg-amber-500"></div>
                  <span className="text-foreground">Señal de Venta (SELL)</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 bg-green-500"></div>
                  <span className="text-foreground">Vela Alcista</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 bg-red-500"></div>
                  <span className="text-foreground">Vela Bajista</span>
                </div>
              </div>
            </Card>

            {/* Trade Details */}
            <Card className="p-6">
              <h3 className="text-lg font-semibold text-foreground mb-4">Detalles de Operaciones</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b border-border">
                    <tr>
                      <th className="text-left py-2 px-4 text-muted-foreground font-semibold">Tipo</th>
                      <th className="text-left py-2 px-4 text-muted-foreground font-semibold">Precio</th>
                      <th className="text-left py-2 px-4 text-muted-foreground font-semibold">Hora</th>
                      <th className="text-left py-2 px-4 text-muted-foreground font-semibold">Profit %</th>
                    </tr>
                  </thead>
                  <tbody>
                    {results.trades.map((trade, index) => (
                      <tr key={index} className="border-b border-border hover:bg-muted/50">
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2">
                            {trade.side === 'BUY' ? (
                              <TrendingUp className="text-blue-500" size={16} />
                            ) : (
                              <TrendingDown className="text-amber-500" size={16} />
                            )}
                            <span className="font-semibold">{trade.side}</span>
                          </div>
                        </td>
                        <td className="py-3 px-4 text-foreground">${trade.price.toFixed(2)}</td>
                        <td className="py-3 px-4 text-muted-foreground">
                          {new Date(trade.time).toLocaleTimeString()}
                        </td>
                        <td className="py-3 px-4">
                          {trade.profit !== undefined ? (
                            <span className={trade.profit >= 0 ? 'text-green-500 font-semibold' : 'text-red-500 font-semibold'}>
                              {trade.profit >= 0 ? '+' : ''}{trade.profit.toFixed(2)}%
                            </span>
                          ) : (
                            <span className="text-muted-foreground">-</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </>
        )}

        {!results && (
          <Card className="p-12 text-center">
            <BarChart3 className="mx-auto mb-4 text-muted-foreground" size={48} />
            <p className="text-lg text-muted-foreground">
              Configura los parámetros y ejecuta un backtesting para ver los resultados con gráficas de velas
            </p>
          </Card>
        )}
      </div>
    </SignalsKeiLayout>
  );
}
