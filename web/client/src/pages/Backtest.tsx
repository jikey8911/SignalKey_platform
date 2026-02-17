import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Play, BarChart3, TrendingUp, TrendingDown, Loader2, Trophy, BrainCircuit, ChevronRight, Search, RotateCcw, CircleStop, X } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/_core/hooks/useAuth';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Progress } from '@/components/ui/progress';
import { CONFIG } from '@/config';
import { TradingViewChart } from '@/components/ui/TradingViewChart';
import { wsService } from '@/lib/websocket'; // Importar servicio WS

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
  signals_non_zero?: number;
  signal_source?: 'model' | 'strategy_fallback' | string;
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

// TradingView Chart Wrapper for Backtest
const BacktestChart = ({ candles, trades }: { candles: Candle[]; trades: Trade[] }) => (
  <TradingViewChart
    data={candles}
    trades={trades.map(t => ({
      time: t.time,
      price: t.price,
      side: t.side,
      label: t.label
    }))}
    height={400}
  />
);

export default function Backtest() {
  const { user } = useAuth();

  // Exchange, Market, Symbol selection
  const [selectedExchange, setSelectedExchange] = useState<string>('');
  const [selectedMarket, setSelectedMarket] = useState<string>('');
  const [selectedSymbol, setSelectedSymbol] = useState<string>('');

  // Backtest config
  const [symbol, setSymbol] = useState('BTC/USDT');
  const [timeframe, setTimeframe] = useState('1h');
  const [days, setDays] = useState(30);
  const [isRunning, setIsRunning] = useState(false);
  const [results, setResults] = useState<BacktestResults | null>(null);
  const [initialBalance, setInitialBalance] = useState<number>(10000); // Default 10000
  const [tradeAmount, setTradeAmount] = useState<number>(1000); // Default 1000 for DCA step

  // Guardar estimados (AI) devueltos por /backtest/optimize para mostrarlos en la UI
  const [optEstimates, setOptEstimates] = useState<Record<string, { expected_profit_pct?: number; expected_win_rate?: number }>>({});
  const optKey = useCallback((strategyName?: string, sym?: string) => `${sym || ''}__${strategyName || ''}`, []);

  // Symbol Search
  const [symbolSearch, setSymbolSearch] = useState('');

  // Balances/limits for simulation (source of truth)
  const [virtualBalance, setVirtualBalance] = useState<number>(10000);
  const [loadingBalance, setLoadingBalance] = useState(false);
  const [investmentLimits, setInvestmentLimits] = useState<{ cexMaxAmount?: number; dexMaxAmount?: number }>({});

  // Fetch Exchanges
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [loadingExchanges, setLoadingExchanges] = useState(false);

  useEffect(() => {
    setLoadingExchanges(true);
    console.log("[Backtest] Fetching user exchanges from:", `${CONFIG.API_BASE_URL}/backtest/exchanges`);
    fetch(`${CONFIG.API_BASE_URL}/backtest/exchanges`, { credentials: 'include' })
      .then(res => {
        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
        return res.json();
      })
      .then(data => {
        console.log("[Backtest] User exchanges loaded:", data);
        if (!Array.isArray(data)) return;

        // API already returns [{exchangeId,isActive}]
        const list: Exchange[] = data.filter((x: any) => x?.exchangeId);
        setExchanges(list);

        // Default exchange: prefer OKX if present, else first.
        if (list.length > 0) {
          const okx = list.find((e: any) => String(e.exchangeId).toLowerCase() === 'okx');
          const defaultExchange = (okx?.exchangeId || list[0]?.exchangeId || '').toString();

          setSelectedExchange(defaultExchange);

          // Reset dependent selections and load markets (which will also load symbols)
          setMarkets([]);
          setSelectedMarket('');
          setSymbols([]);
          setSelectedSymbol('');
          loadMarkets(defaultExchange);
        }
      })
      .catch(err => {
        console.error("[Backtest] Error fetching exchanges:", err);
        toast.error("Error al cargar exchanges");
      })
      .finally(() => setLoadingExchanges(false));
  }, []);

  // WebSocket Connection Initialization
  useEffect(() => {
    if (user?.openId) {
      console.log(`[Backtest] Initializing WebSocket for user: ${user.openId}`);
      wsService.connect(user.openId);
    }
    return () => {
      // We don't necessarily want to disconnect here if other pages use it, 
      // but wsService.connect handles existing connections.
    };
  }, [user?.openId]);

  // Fetch Symbols
  const [symbols, setSymbols] = useState<Symbol[]>([]);
  const [loadingSymbols, setLoadingSymbols] = useState(false);

  const loadSymbols = useCallback((exchangeId: string, marketType: string) => {
    if (!exchangeId || !marketType) return;

    const mt = String(marketType).toLowerCase();
    if (mt === 'dex') {
      setSymbols([]);
      return;
    }

    setLoadingSymbols(true);
    fetch(`${CONFIG.API_BASE_URL}/backtest/symbols/${encodeURIComponent(exchangeId)}?market_type=${encodeURIComponent(mt)}`, { credentials: 'include' })
      .then(res => res.json())
      .then(data => {
        const arr = Array.isArray(data) ? data : (Array.isArray(data?.symbols) ? data.symbols : []);
        if (Array.isArray(arr)) {
          const mapped: Symbol[] = arr.map((s: any) => {
            const sym = (typeof s === 'string') ? s : (s.symbol || '');
            return {
              symbol: sym,
              baseAsset: sym.split('/')[0] || '',
              quoteAsset: sym.split('/')[1] || '',
              price: (typeof s === 'object' && s?.price) ? Number(s.price) : 0,
              priceChange: (typeof s === 'object' && s?.priceChange) ? Number(s.priceChange) : 0,
              priceChangePercent: (typeof s === 'object' && s?.priceChangePercent) ? Number(s.priceChangePercent) : 0,
              volume: (typeof s === 'object' && s?.volume) ? Number(s.volume) : 0,
            };
          });
          setSymbols(mapped);
        }
      })
      .catch(err => console.error('Error fetching symbols:', err))
      .finally(() => setLoadingSymbols(false));
  }, []);

  // Fetch Markets (dynamic from CCXT, per exchange)
  const [markets, setMarkets] = useState<string[]>([]);
  const [loadingMarkets, setLoadingMarkets] = useState(false);

  const loadMarkets = useCallback((exchangeId: string) => {
    if (!exchangeId) {
      setMarkets([]);
      return;
    }
    setLoadingMarkets(true);
    fetch(`${CONFIG.API_BASE_URL}/backtest/markets/${encodeURIComponent(exchangeId)}`, { credentials: 'include' })
      .then(res => res.json())
      .then(data => {
        const arr = Array.isArray(data) ? data : (Array.isArray(data?.markets) ? data.markets : []);
        if (Array.isArray(arr)) {
          setMarkets(arr);

          // Default market: prefer spot if present, else first.
          if (arr.length > 0) {
            const spot = arr.find((m: any) => String(m).toLowerCase() === 'spot');
            const preferred = String(spot ?? arr[0]);

            setSelectedMarket(preferred);
            setSelectedSymbol('');
            loadSymbols(exchangeId, preferred);
          }
        }
      })
      .catch(err => {
        console.error('Error fetching markets:', err);
        setMarkets([]);
      })
      .finally(() => setLoadingMarkets(false));
  }, [loadSymbols]);

  // Handle Exchange Change
  const handleExchangeChange = (exchangeId: string) => {
    setSelectedExchange(exchangeId);

    // Clear dependent states
    setMarkets([]);
    setSelectedMarket('');
    setSymbols([]);
    setSelectedSymbol('');

    if (exchangeId) {
      loadMarkets(exchangeId);
    }
  };

  // Handle Market Change
  const handleMarketChange = (marketType: string) => {
    const mt = String(marketType);
    setSelectedMarket(mt);
    if (selectedExchange) {
      loadSymbols(selectedExchange, mt);
    }
    setSelectedSymbol('');
  };

  // --- Semi-Auto Access (WebSocket) ---
  const [isScanning, setIsScanning] = useState(false);
  const [scanResults, setScanResults] = useState<BacktestResults[]>([]);
  const [scanProgress, setScanProgress] = useState({ current: 0, total: 0, percent: 0, symbol: '' });
  const [selectedResult, setSelectedResult] = useState<BacktestResults | null>(null);

  // Escuchar eventos WebSocket
  useEffect(() => {
    const handleBacktestStart = (data: any) => {
      setIsScanning(true);
      setScanResults([]);
      setScanProgress({ current: 0, total: data.total || 0, percent: 0, symbol: 'Iniciando...' });
      toast.info(`Iniciando escaneo de ${data.total} símbolos...`);
    };

    const handleBacktestProgress = (data: any) => {
      setScanProgress({
        current: data.current,
        total: data.total,
        percent: data.percent,
        symbol: data.symbol
      });
    };

    const handleBacktestResult = (data: any) => {
      // Transformar datos del WS a la estructura BacktestResults
      // Nota: 'details' viene serializado como en el endpoint single run
      const details = data.details || {};

      const normalizeTime = (t: any): number => {
        if (typeof t === 'string') return new Date(t).getTime();
        if (typeof t === 'number' && t < 20000000000) return t * 1000;
        return t;
      };

      const transformedTrades: Trade[] = details.trades?.map((t: any) => ({
        time: normalizeTime(t.time),
        price: t.price,
        side: t.type as 'BUY' | 'SELL',
        profit: t.pnl,
        amount: t.amount,
        avg_price: t.avg_price,
        label: t.label,
        pnl_percent: t.pnl_percent
      })) || [];

      const candles: Candle[] = details.chart_data?.map((c: any) => ({
        time: normalizeTime(c.time),
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close
      })) || [];

      // Normalización robusta: soporta payload en 0..100 o 0..1.
      const toFinite = (v: any) => {
        const n = Number(v);
        return Number.isFinite(n) ? n : 0;
      };

      const initialBal = toFinite(details?.initial_balance ?? details?.resolved_initial_balance);
      const finalBal = toFinite(details?.final_balance);
      const impliedPct = initialBal > 0 && finalBal > 0
        ? ((finalBal / initialBal) - 1) * 100
        : null;

      const normalizePct = (v: any, implied: number | null = null) => {
        const n = toFinite(v);

        // Si tenemos balances, usamos esa referencia para detectar escala.
        if (implied !== null && Number.isFinite(implied)) {
          if (Math.abs(n - implied) < 0.05) return n;          // ya viene en %
          if (Math.abs((n * 100) - implied) < 0.05) return n * 100; // viene como ratio
        }

        // Fallback heurístico
        if (Math.abs(n) > 0 && Math.abs(n) <= 1) return n * 100;
        return n;
      };

      const pnlValue = normalizePct(
        details?.profit_pct ?? details?.metrics?.profit_pct ?? data?.pnl ?? 0,
        impliedPct
      );
      const wrValue = normalizePct(
        details?.win_rate ?? details?.metrics?.win_rate ?? data?.win_rate ?? 0,
        null
      );
      const tradesValue = Number(
        details?.total_trades ?? details?.metrics?.total_trades ?? data?.trades ?? 0
      );

      const result: BacktestResults = {
        symbol: data.symbol,
        timeframe: timeframe, // Usamos el estado local ya que es el mismo para todos
        days: days,
        totalTrades: tradesValue,
        winRate: wrValue,
        profitFactor: details.metrics?.profit_factor?.toString() || '0',
        maxDrawdown: Number(details.metrics?.max_drawdown || 0).toFixed(2),
        totalReturn: pnlValue.toFixed(2),
        sharpeRatio: details.metrics?.sharpe_ratio?.toString() || '0',
        candles: candles,
        trades: transformedTrades,
        botConfiguration: details.bot_configuration,
        metrics: details.metrics,
        tournamentResults: details.tournament_results,
        winner: details.winner,
        strategy_name: data.strategy,
        initial_balance: details.initial_balance,
        final_balance: details.final_balance
      };

      // Top 10 por símbolo: mayor PnL y, en empate, mayor Win Rate.
      setScanResults(prev => {
        const bySymbol = new Map<string, BacktestResults>();

        const compare = (a: BacktestResults, b: BacktestResults) => {
          const profitA = Number.parseFloat(a.totalReturn) || 0;
          const profitB = Number.parseFloat(b.totalReturn) || 0;
          if (profitB !== profitA) return profitB - profitA;
          const wrA = Number(a.winRate) || 0;
          const wrB = Number(b.winRate) || 0;
          if (wrB !== wrA) return wrB - wrA;
          const trA = Number(a.totalTrades) || 0;
          const trB = Number(b.totalTrades) || 0;
          return trB - trA;
        };

        [...prev, result].forEach((r) => {
          const key = r.symbol;
          const current = bySymbol.get(key);
          if (!current || compare(r, current) < 0) {
            bySymbol.set(key, r);
          }
        });

        return Array.from(bySymbol.values())
          .sort(compare)
          .slice(0, 10);
      });
    };

    const handleBacktestComplete = (data: any) => {
      setIsScanning(false);
      setScanProgress({ ...scanProgress, percent: 100, symbol: 'Completado' });
      toast.success("Escaneo completado exitosamente");
    };

    const handleBacktestError = (data: any) => {
      console.error("Backtest Error:", data);
      toast.error(`Error en backtest: ${data.message || data.error}`);
      if (data.message && data.message.includes("Critical")) {
        setIsScanning(false);
      }
    };

    const handleSingleBacktestStart = (data: any) => {
      setIsRunning(true);
      toast.info(`Backtest iniciado: ${data?.symbol || ''}`);
    };

    const handleSingleBacktestResult = (data: any) => {
      try {
        const normalizeTime = (t: any): number => {
          if (typeof t === 'string') return new Date(t).getTime();
          if (typeof t === 'number' && t < 20000000000) return t * 1000;
          return t;
        };

        const toFinite = (v: any) => {
          const n = Number(v);
          return Number.isFinite(n) ? n : 0;
        };

        const initialBal = toFinite(data?.initial_balance);
        const normalizePct = (v: any, implied: number | null = null) => {
          const n = toFinite(v);
          if (implied !== null && Number.isFinite(implied)) {
            if (Math.abs(n - implied) < 0.05) return n;
            if (Math.abs((n * 100) - implied) < 0.05) return n * 100;
          }
          if (Math.abs(n) > 0 && Math.abs(n) <= 1) return n * 100;
          return n;
        };

        const transformedTrades: Trade[] = (data.trades || []).map((t: any) => ({
          time: normalizeTime(t.time),
          price: t.price,
          side: t.type as 'BUY' | 'SELL',
          profit: t.pnl,
          amount: t.amount,
          avg_price: t.avg_price,
          label: t.label,
          pnl_percent: t.pnl_percent
        }));

        transformedTrades.sort((a, b) => {
          if (b.time !== a.time) return b.time - a.time;
          const isCloseA = a.label?.includes('CLOSE') || false;
          const isCloseB = b.label?.includes('CLOSE') || false;
          if (isCloseA && !isCloseB) return 1;
          if (!isCloseA && isCloseB) return -1;
          return 0;
        });

        const candles: Candle[] = (data.chart_data || []).map((c: any) => ({
          time: normalizeTime(c.time),
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close
        }));

        const normalizedTournament: TournamentResult[] = (data.tournament_results || []).map((r: any) => {
          const finalB = toFinite(r.final_balance);
          const implied = initialBal > 0 && finalB > 0 ? ((finalB / initialBal) - 1) * 100 : null;
          return {
            strategy: String(r.strategy || 'unknown'),
            profit_pct: normalizePct(r.profit_pct, implied),
            total_trades: Number(r.total_trades || 0),
            win_rate: normalizePct(r.win_rate, null),
            final_balance: finalB,
            signals_non_zero: Number(r.signals_non_zero || 0),
            signal_source: r.signal_source || 'model',
          };
        });

        const overallFinalBal = toFinite(data?.final_balance);
        const overallImplied = initialBal > 0 && overallFinalBal > 0 ? ((overallFinalBal / initialBal) - 1) * 100 : null;

        const backtestResults: BacktestResults = {
          symbol: data.symbol,
          timeframe: data.timeframe,
          days: data.days,
          totalTrades: Number(data.metrics?.total_trades || 0),
          winRate: normalizePct(data.metrics?.win_rate || 0, null),
          profitFactor: (data.metrics?.profit_factor ?? 0).toString(),
          maxDrawdown: Number(data.metrics?.max_drawdown || 0).toFixed(2),
          totalReturn: normalizePct(data.metrics?.profit_pct || 0, overallImplied).toFixed(2),
          sharpeRatio: (data.metrics?.sharpe_ratio ?? 0).toString(),
          candles,
          trades: transformedTrades,
          botConfiguration: data.bot_configuration,
          metrics: data.metrics,
          tournamentResults: normalizedTournament,
          winner: data.winner,
          strategy_name: data.strategy_name,
          initial_balance: Number(data.initial_balance || 0),
          final_balance: Number(data.final_balance || 0)
        };

        setResults(backtestResults);
        toast.success(`Backtest completado. Ganador: ${data.strategy_name || ''}`);
      } catch (e: any) {
        console.error('Error parsing single backtest result:', e);
        toast.error(`Error parseando resultado: ${e.message}`);
      } finally {
        setIsRunning(false);
      }
    };

    const handleSingleBacktestError = (data: any) => {
      console.error('Single backtest error:', data);
      toast.error(`Error en backtest: ${data?.message || 'desconocido'}`);
      setIsRunning(false);
    };

    const handleSymbolError = (data: any) => {
      console.warn(`Error en símbolo ${data.symbol}: ${data.error}`);
    }

    wsService.on('backtest_start', handleBacktestStart);
    wsService.on('backtest_progress', handleBacktestProgress);
    wsService.on('backtest_result', handleBacktestResult);
    wsService.on('backtest_complete', handleBacktestComplete);
    wsService.on('backtest_error', handleBacktestError);
    wsService.on('backtest_symbol_error', handleSymbolError);

    wsService.on('single_backtest_start', handleSingleBacktestStart);
    wsService.on('single_backtest_result', handleSingleBacktestResult);
    wsService.on('single_backtest_error', handleSingleBacktestError);

    return () => {
      wsService.off('backtest_start', handleBacktestStart);
      wsService.off('backtest_progress', handleBacktestProgress);
      wsService.off('backtest_result', handleBacktestResult);
      wsService.off('backtest_complete', handleBacktestComplete);
      wsService.off('backtest_error', handleBacktestError);
      wsService.off('backtest_symbol_error', handleSymbolError);

      wsService.off('single_backtest_start', handleSingleBacktestStart);
      wsService.off('single_backtest_result', handleSingleBacktestResult);
      wsService.off('single_backtest_error', handleSingleBacktestError);
    };
  }, [timeframe, days]); // Dependencias para el contexto de result mapping

  const handleStartScan = () => {
    if (!user?.openId || !selectedExchange || !selectedMarket) {
      toast.error("Configuración incompleta");
      return;
    }

    // Enviar comando por WS. El backend debe resolver los symbols (solo activos) y hacer el batch.
    wsService.send({
      action: "run_batch_backtest",
      data: {
        exchangeId: selectedExchange,
        marketType: selectedMarket,
        timeframe: timeframe,
        days: days,
        initialBalance: initialBalance,
        tradeAmount: tradeAmount,
        topN: 10
      }
    });

    // Reset UI state (y además el backend emitirá backtest_start)
    setIsScanning(true);
    setScanResults([]);
  };

  const handleStopScan = () => {
    // No implemented explicit stop in backend yet, but we can simulate locally or reload
    // For now just warn user
    toast.info("La detención del proceso en servidor no está implementada, recarga la página si deseas cancelar la visualización.");
    setIsScanning(false);
  };

  // (Removed) legacy symbols loader via /market/...; we now load via loadSymbols() using /backtest/symbols.

  // Fetch user config and auto-select active exchange
  useEffect(() => {
    if (!user?.openId) return;

    fetch(`${CONFIG.API_BASE_URL}/config/`, { credentials: 'include' })
      .then(res => res.json())
      .then(data => {
        const config = data.config;
        if (config) {
          setInvestmentLimits(config.investmentLimits || {});

          let activeEx = config.activeExchange;
          if (!activeEx && config.exchanges && config.exchanges.length > 0) {
            const firstActive = config.exchanges.find((e: any) => e.isActive);
            if (firstActive) activeEx = firstActive.exchangeId;
          }

          if (activeEx) {
            // Keep exchange/market/symbols in sync
            handleExchangeChange(activeEx);
          }
        }
      })
      .catch(err => console.error("Error fetching user config for active exchange:", err));
  }, [user?.openId]);

  // NOTE: Default selection is handled when exchanges are fetched (prefers OKX) and when user config loads.


  // Fetch Virtual Balance (según mercado seleccionado)
  useEffect(() => {
    const fetchBalance = async () => {
      if (!user?.openId) return;

      setLoadingBalance(true);
      try {
        const mt = String(selectedMarket || 'spot').toLowerCase();
        const isCex = ['spot', 'cex', 'futures', 'future', 'swap'].includes(mt);
        const vbMarket = isCex ? 'CEX' : 'DEX';
        const asset = isCex ? 'USDT' : 'SOL';

        const res = await fetch(
          `${CONFIG.API_BASE_URL}/backtest/virtual_balance?market_type=${vbMarket}&asset=${asset}`,
          { credentials: 'include' }
        );
        if (res.ok) {
          const data = await res.json();
          const bal = Number(data.balance || (isCex ? 10000 : 10));
          setVirtualBalance(bal);
          setInitialBalance(bal); // no editable: espejo del virtual balance
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
  }, [user?.openId, selectedMarket]);

  // Inversión por entrada desde config (no editable en UI)
  useEffect(() => {
    const mt = String(selectedMarket || 'spot').toLowerCase();
    const isCex = ['spot', 'cex', 'futures', 'future', 'swap'].includes(mt);
    const amount = Number(isCex ? investmentLimits.cexMaxAmount : investmentLimits.dexMaxAmount);
    if (Number.isFinite(amount) && amount > 0) {
      setTradeAmount(amount);
    }
  }, [selectedMarket, investmentLimits]);

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
    toast.loading('Ejecutando backtest en segundo plano...');

    wsService.send({
      action: 'run_single_backtest',
      data: {
        symbol: selectedSymbol,
        exchangeId: selectedExchange || 'okx',
        marketType: selectedMarket,
        timeframe,
        days,
        initialBalance: initialBalance,
        tradeAmount: tradeAmount,
        strategy: 'auto',
        useAi: true,
      }
    });
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
                  <div className="flex items-center gap-2 px-4 py-2 border border-slate-700 rounded-lg bg-slate-900">
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
                    onChange={(e) => handleExchangeChange(e.target.value)}
                    className="w-full px-4 py-2 border border-slate-700 rounded-lg bg-slate-900 text-white focus:outline-none focus:ring-2 focus:ring-primary"
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
                  <div className="flex items-center gap-2 px-4 py-2 bg-slate-900 rounded-lg border border-slate-700 h-[42px]">
                    <Loader2 className="h-4 w-4 animate-spin text-primary" />
                    <span className="text-muted-foreground text-sm">Cargando...</span>
                  </div>
                ) : (
                  <select
                    value={selectedMarket}
                    onChange={(e) => handleMarketChange(e.target.value)}
                    disabled={!selectedExchange || markets.length === 0}
                    className="w-full px-4 py-2 border border-slate-700 rounded-lg bg-slate-900 text-white focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
                  >
                    <option value="">Seleccionar mercado</option>
                    {markets.map((m) => (
                      <option key={m} value={m}>
                        {String(m).toUpperCase()}
                      </option>
                    ))}
                    <option value="dex" disabled>DEX</option>
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
                  className="w-full px-4 py-2 border border-slate-700 rounded-lg bg-slate-900 text-white focus:outline-none focus:ring-2 focus:ring-primary"
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
                      className="px-3 py-1 text-sm border border-slate-700 rounded-md bg-slate-900 text-white focus:outline-none focus:ring-2 focus:ring-primary w-40"
                    />
                  </div>
                </div>
                {loadingSymbols ? (
                  <div className="flex items-center justify-center gap-2 p-8 border border-slate-800 rounded-lg bg-slate-950/50">
                    <Loader2 className="animate-spin" size={24} />
                    <span className="text-muted-foreground">Cargando símbolos...</span>
                  </div>
                ) : symbols.length === 0 ? (
                  <div className="p-4 border border-slate-800 rounded-lg bg-slate-950/50 text-muted-foreground text-center">
                    No hay símbolos disponibles
                  </div>
                ) : (
                  <div className="border border-border rounded-lg bg-slate-950/50 h-96 overflow-y-auto" style={{ height: '400px' }}>
                    <table className="w-full text-sm">
                      <thead className="sticky top-0 bg-slate-900 border-b border-border text-white shadow-md z-10">
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
                            className="border-b border-border hover:bg-slate-800/50 cursor-pointer text-slate-200 transition-colors"
                            onClick={() => {
                              setSelectedSymbol(sym.symbol);
                              setSymbol(sym.symbol);
                            }}
                          >
                            <td className="py-3 px-4 font-bold text-cyan-400">{sym.symbol}</td>
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
                className="w-full px-4 py-2 border border-slate-700 rounded-lg bg-slate-900 text-white focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>

            {/* Simulation Configuration */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
              <div>
                <label className="block text-sm font-semibold text-foreground mb-2">
                  Balance Virtual (USDT)
                </label>
                <input
                  type="number"
                  value={initialBalance}
                  readOnly
                  disabled
                  className="w-full px-4 py-2 border border-slate-700 rounded-lg bg-slate-800 text-white/90"
                />
              </div>
              <div>
                <label className="block text-sm font-semibold text-foreground mb-2">
                  Inversión por Entrada (Configuración global)
                </label>
                <input
                  type="number"
                  value={tradeAmount}
                  readOnly
                  disabled
                  className="w-full px-4 py-2 border border-slate-700 rounded-lg bg-slate-800 text-white/90"
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
                          <th className="text-right py-2 px-4 text-muted-foreground font-semibold">Señales</th>
                          <th className="text-right py-2 px-4 text-muted-foreground font-semibold">Fuente</th>
                          <th className="text-right py-2 px-4 text-muted-foreground font-semibold">Balance Final</th>
                          <th className="text-right py-2 px-4 text-muted-foreground font-semibold">Acciones</th>
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
                              <div>
                                {res.profit_pct >= 0 ? '+' : ''}{res.profit_pct}%
                                {(() => {
                                  const est = optEstimates[optKey(res.strategy, results.symbol)];
                                  if (!est || est.expected_profit_pct == null) return null;
                                  return <div className="text-[10px] text-muted-foreground font-normal">AI~ {est.expected_profit_pct}%</div>;
                                })()}
                              </div>
                            </td>
                            <td className="py-3 px-4 text-right">
                              <div>
                                {res.win_rate}%
                                {(() => {
                                  const est = optEstimates[optKey(res.strategy, results.symbol)];
                                  if (!est || est.expected_win_rate == null) return null;
                                  return <div className="text-[10px] text-muted-foreground">AI~ {est.expected_win_rate}%</div>;
                                })()}
                              </div>
                            </td>
                            <td className="py-3 px-4 text-right">{res.total_trades}</td>
                            <td className="py-3 px-4 text-right">{res.signals_non_zero ?? 0}</td>
                            <td className="py-3 px-4 text-right">
                              {res.signal_source === 'strategy_fallback' ? (
                                <Badge variant="outline" className="text-[10px] border-amber-500/40 text-amber-400">fallback</Badge>
                              ) : (
                                <Badge variant="outline" className="text-[10px] border-emerald-500/40 text-emerald-400">model</Badge>
                              )}
                            </td>
                            <td className="py-3 px-4 text-right font-mono">${res.final_balance.toLocaleString()}</td>
                            <td className="py-3 px-4 text-right">
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={async () => {
                                  const toastId = toast.loading(`Optimizando ${res.strategy}...`);
                                  try {
                                    const response = await fetch(`${CONFIG.API_BASE_URL}/backtest/optimize`, {
                                      method: 'POST',
                                      headers: { 'Content-Type': 'application/json' },
                                      credentials: 'include',
                                      body: JSON.stringify({
                                        strategy_name: res.strategy,
                                        symbol: results.symbol,
                                        exchange_id: selectedExchange || 'okx',
                                        timeframe: results.timeframe,
                                        market_type: selectedMarket || 'spot',
                                        days: results.days,
                                        initial_balance: results.initial_balance || initialBalance,
                                        trade_amount: tradeAmount,
                                      })
                                    });
                                    if (!response.ok) {
                                      const err = await response.json().catch(() => ({}));
                                      throw new Error(err.detail || 'Error optimizando');
                                    }
                                    const opt = await response.json();

                                    // Guardar estimado para mostrarlo al lado de los valores actuales
                                    setOptEstimates(prev => ({
                                      ...prev,
                                      [optKey(res.strategy, results.symbol)]: {
                                        expected_profit_pct: opt?.expected_profit_pct,
                                        expected_win_rate: opt?.expected_win_rate,
                                      }
                                    }));

                                    const extra = (opt?.expected_profit_pct != null || opt?.expected_win_rate != null)
                                      ? ` (AI: PnL~${opt.expected_profit_pct ?? 'N/A'}%, WR~${opt.expected_win_rate ?? 'N/A'}%)`
                                      : '';
                                    toast.success(`Estrategia ${res.strategy} optimizada y guardada${extra}`, { id: toastId });
                                  } catch (e: any) {
                                    toast.error(`Error: ${e.message}`, { id: toastId });
                                  }
                                }}
                              >
                                Optimizar
                              </Button>
                            </td>
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
                      <div className="bg-slate-950/50 p-4 rounded-xl border border-cyan-500/20 text-sm font-mono space-y-2 shadow-inner">
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
                              initial_balance: virtualBalance.toString(),
                              timeframe: results.timeframe // Enviar timeframe del resultado
                            }), {
                              method: 'POST',
                              credentials: 'include'
                            });

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
                  <BacktestChart candles={results.candles} trades={results.trades} />
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
                        <th className="text-left py-2 px-4 font-semibold">Tipo</th>
                        <th className="text-left py-2 px-4 font-semibold">Acción</th>
                        <th className="text-right py-2 px-4 font-semibold">Cantidad</th>
                        <th className="text-right py-2 px-4 font-semibold">Precio Ejecución</th>
                        <th className="text-right py-2 px-4 font-semibold">Precio Entrada</th>
                        <th className="text-right py-2 px-4 font-semibold">Hora</th>
                        <th className="text-right py-2 px-4 font-semibold">Profit</th>
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
                  <Card className="p-4 shadow-2xl border-primary/20 bg-slate-950/95 backdrop-blur w-72 animate-in slide-in-from-bottom-5">
                    <div className="flex justify-between items-start mb-2">
                      <h4 className="font-bold flex items-center gap-2">
                        {selectedTrade.side === 'BUY' ? <TrendingUp className="text-blue-500" size={16} /> : <TrendingDown className="text-amber-500" size={16} />}
                        Detalle Operación
                      </h4>
                      <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => setSelectedTrade(null)}>
                        <X size={16} />
                      </Button>
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
                  <div className="flex items-center gap-2 px-4 py-2 border border-slate-700 rounded-lg bg-slate-900">
                    <Loader2 className="animate-spin" size={16} />
                    <span className="text-muted-foreground">Cargando...</span>
                  </div>
                ) : exchanges.length === 0 ? (
                  <div className="px-4 py-2 border border-slate-700 rounded-lg bg-slate-900 text-muted-foreground">
                    No hay exchanges
                  </div>
                ) : (
                  <select
                    value={selectedExchange}
                    onChange={(e) => handleExchangeChange(e.target.value)}
                    className="w-full px-4 py-2 border border-slate-700 rounded-lg bg-slate-900 text-white focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    <option value="">Seleccionar Exchange</option>
                    {exchanges.map((ex) => (
                      <option key={ex.exchangeId} value={ex.exchangeId}>
                        {ex.exchangeId.toUpperCase()}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              {/* Market Type */}
              <div>
                <label className="block text-sm font-semibold text-foreground mb-2">
                  Mercado
                </label>
                {loadingMarkets ? (
                  <div className="flex items-center gap-2 px-4 py-2 bg-slate-900 rounded-lg border border-slate-700 h-[42px]">
                    <Loader2 className="h-4 w-4 animate-spin text-primary" />
                    <span className="text-muted-foreground text-sm">Cargando...</span>
                  </div>
                ) : (
                  <select
                    value={selectedMarket}
                    onChange={(e) => handleMarketChange(e.target.value)}
                    disabled={!selectedExchange || markets.length === 0}
                    className="w-full px-4 py-2 border border-slate-700 rounded-lg bg-slate-900 text-white focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
                  >
                    <option value="">Seleccionar mercado</option>
                    {markets.map((m) => (
                      <option key={m} value={m}>
                        {String(m).toUpperCase()}
                      </option>
                    ))}
                    <option value="dex" disabled>DEX</option>
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
                  className="w-full px-4 py-2 border border-slate-700 rounded-lg bg-slate-900 text-white focus:outline-none focus:ring-2 focus:ring-primary"
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
                  className="w-full px-4 py-2 border border-slate-700 rounded-lg bg-slate-900 text-white focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
            </div>

            {/* Simulation Config for Semi-Auto */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6 border-t border-border pt-4">
              <div>
                <label className="block text-sm font-semibold text-foreground mb-2">
                  Balance Virtual (USDT)
                </label>
                <input
                  type="number"
                  value={initialBalance}
                  readOnly
                  disabled
                  className="w-full px-4 py-2 border border-slate-700 rounded-lg bg-slate-800 text-white/90"
                />
              </div>
              <div>
                <label className="block text-sm font-semibold text-foreground mb-2">
                  Inversión por Entrada (Configuración global)
                </label>
                <input
                  type="number"
                  value={tradeAmount}
                  readOnly
                  disabled
                  className="w-full px-4 py-2 border border-slate-700 rounded-lg bg-slate-800 text-white/90"
                />
              </div>
            </div>

            <div className="flex justify-end gap-4">
              {isScanning && (
                <Button
                  onClick={handleStopScan}
                  variant="destructive"
                  size="lg"
                >
                  <CircleStop className="mr-2 h-4 w-4 fill-current" /> Detener Escaneo
                </Button>
              )}
              <Button
                onClick={handleStartScan}
                disabled={isScanning || !selectedExchange || !selectedMarket}
                className={`w-full md:w-auto ${isScanning ? 'opacity-80' : ''}`}
                size="lg"
              >
                {isScanning ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Escaneando {scanProgress.symbol} ({scanProgress.current}/{scanProgress.total})
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
                <span>Progreso: {scanProgress.symbol}</span>
                <span>{Math.round(scanProgress.percent)}%</span>
              </div>
              <Progress value={scanProgress.percent} className="h-2" />
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

                  {/* Estimado AI (se llena al darle "Optimizar") */}
                  {(() => {
                    const est = optEstimates[optKey(selectedResult.strategy_name, selectedResult.symbol)];
                    if (!est || (est.expected_profit_pct == null && est.expected_win_rate == null)) return null;
                    return (
                      <Card className="p-4 bg-muted/40 border border-border">
                        <div className="flex items-center justify-between gap-4">
                          <div className="flex items-center gap-2">
                            <BrainCircuit className="text-cyan-500" size={18} />
                            <div>
                              <p className="text-sm font-semibold">Estimado (AI)</p>
                              <p className="text-xs text-muted-foreground">Proyección aproximada para esta optimización</p>
                            </div>
                          </div>
                          <div className="flex gap-4 text-sm">
                            <div className="text-right">
                              <p className="text-[10px] text-muted-foreground uppercase font-bold">PnL estimado</p>
                              <p className="font-mono font-bold">{est.expected_profit_pct ?? 'N/A'}%</p>
                            </div>
                            <div className="text-right">
                              <p className="text-[10px] text-muted-foreground uppercase font-bold">WR estimado</p>
                              <p className="font-mono font-bold">{est.expected_win_rate ?? 'N/A'}%</p>
                            </div>
                          </div>
                        </div>
                      </Card>
                    );
                  })()}

                  {/* Chart */}
                  <div className="h-64 md:h-80 w-full">
                    <BacktestChart candles={selectedResult.candles} trades={selectedResult.trades} />
                  </div>

                  {/* Deploy / Optimize Action */}
                  <div className="flex justify-end gap-3 pt-4 border-t border-border">
                    <Button variant="outline" onClick={() => setSelectedResult(null)}>Cerrar</Button>

                    <Button
                      variant="outline"
                      onClick={async () => {
                        const toastId = toast.loading(`Optimizando ${selectedResult.strategy_name}...`);
                        try {
                          const response = await fetch(`${CONFIG.API_BASE_URL}/backtest/optimize`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            credentials: 'include',
                            body: JSON.stringify({
                              strategy_name: selectedResult.strategy_name,
                              symbol: selectedResult.symbol,
                              exchange_id: selectedExchange || 'okx',
                              timeframe: selectedResult.timeframe,
                              market_type: selectedMarket || 'spot',
                              days: selectedResult.days,
                              initial_balance: selectedResult.initial_balance || initialBalance,
                              trade_amount: tradeAmount,
                            })
                          });
                          if (!response.ok) {
                            const err = await response.json().catch(() => ({}));
                            throw new Error(err.detail || 'Error optimizando');
                          }
                          const opt = await response.json();

                          // Guardar estimado para mostrarlo al lado de los valores actuales
                          setOptEstimates(prev => ({
                            ...prev,
                            [optKey(selectedResult.strategy_name, selectedResult.symbol)]: {
                              expected_profit_pct: opt?.expected_profit_pct,
                              expected_win_rate: opt?.expected_win_rate,
                            }
                          }));

                          const extra = (opt?.expected_profit_pct != null || opt?.expected_win_rate != null)
                            ? ` (AI: PnL~${opt.expected_profit_pct ?? 'N/A'}%, WR~${opt.expected_win_rate ?? 'N/A'}%)`
                            : '';
                          toast.success(`Estrategia ${selectedResult.strategy_name} optimizada y guardada${extra}`, { id: toastId });
                        } catch (e: any) {
                          toast.error(`Error: ${e.message}`, { id: toastId });
                        }
                      }}
                    >
                      Optimizar
                    </Button>

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
                              initial_balance: virtualBalance.toString(),
                              timeframe: selectedResult.timeframe // Enviar timeframe del modal
                            }), {
                              method: 'POST',
                              credentials: 'include'
                            });

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
