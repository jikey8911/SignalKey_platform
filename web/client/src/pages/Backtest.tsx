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

  // TRPC Queries
  const { data: exchanges = [], isLoading: loadingExchanges } = trpc.backtest.getExchanges.useQuery(undefined, {
    enabled: !!user?.openId
  });

  const { data: marketData, isLoading: loadingMarkets } = trpc.backtest.getMarkets.useQuery(
    { exchangeId: selectedExchange },
    { enabled: !!selectedExchange && !!user?.openId }
  );
  const markets = marketData?.markets || [];

  const { data: symbolData, isLoading: loadingSymbols } = trpc.backtest.getSymbols.useQuery(
    { exchangeId: selectedExchange, marketType: selectedMarket },
    { enabled: !!selectedExchange && !!selectedMarket && !!user?.openId }
  );
  const symbols = symbolData?.symbols || [];

  // Auto-select exchange effect
  useEffect(() => {
    if (exchanges.length === 1 && !selectedExchange) {
      setSelectedExchange(exchanges[0].exchangeId);
    }
  }, [exchanges, selectedExchange]);

  // Auto-select market effect
  useEffect(() => {
    if (markets.length > 0) {
      if (markets.includes('spot')) {
        setSelectedMarket('spot');
      } else {
        setSelectedMarket(markets[0]);
      }
    }
  }, [markets]);

  const handleRunBacktest = async () => {
    setIsRunning(true);
    try {
      toast.loading('Ejecutando backtesting...');

      // Simular resultados de backtesting con datos de velas
      await new Promise(resolve => setTimeout(resolve, 2000));

      // Generar datos de velas simuladas
      const candles: Candle[] = [];
      let basePrice = 45000;
      const now = Date.now();

      for (let i = 0; i < 100; i++) {
        const variation = (Math.random() - 0.5) * 1000;
        const open = basePrice;
        const close = basePrice + variation;
        const high = Math.max(open, close) + Math.random() * 500;
        const low = Math.min(open, close) - Math.random() * 500;

        candles.push({
          time: now - (100 - i) * 3600000,
          open,
          high,
          low,
          close,
        });

        basePrice = close;
      }

      // Generar trades simulados
      const trades: Trade[] = [];
      for (let i = 10; i < candles.length - 5; i += 15) {
        if (Math.random() > 0.5) {
          // BUY
          trades.push({
            time: candles[i].time,
            price: candles[i].close,
            side: 'BUY',
          });

          // SELL después de algunos candles
          const sellIndex = i + Math.floor(Math.random() * 5) + 2;
          if (sellIndex < candles.length) {
            const sellPrice = candles[sellIndex].close;
            const profit = ((sellPrice - candles[i].close) / candles[i].close) * 100;
            trades.push({
              time: candles[sellIndex].time,
              price: sellPrice,
              side: 'SELL',
              profit,
            });
          }
        }
      }

      const mockResults: BacktestResults = {
        symbol,
        timeframe,
        days,
        totalTrades: trades.filter(t => t.side === 'BUY').length,
        winRate: Math.floor(Math.random() * 60) + 30,
        profitFactor: (Math.random() * 2 + 0.5).toFixed(2),
        maxDrawdown: (Math.random() * 30 + 5).toFixed(2),
        totalReturn: (Math.random() * 100 - 20).toFixed(2),
        sharpeRatio: (Math.random() * 2 + 0.5).toFixed(2),
        candles,
        trades,
      };

      setResults(mockResults);
      toast.success('Backtesting completado');
    } catch (error) {
      toast.error('Error al ejecutar backtesting');
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
                  {exchanges.map((ex) => (
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
                  {markets.map((market) => (
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
                      {symbols.map((sym) => (
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
        {results && (
          <>
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
