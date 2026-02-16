import React, { useState, useEffect } from 'react';
import { useSocket } from '../_core/hooks/useSocket';
import { TradingViewChart } from '../components/ui/TradingViewChart';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { ScrollArea } from '../components/ui/scroll-area';
import { Activity, TrendingUp, Clock, RefreshCw, Zap, Wallet, Plus, Play, Square, Settings } from 'lucide-react';
import { api } from '../lib/api';

// --- Tipos de Datos ---
interface Bot {
    id: string;
    name: string;
    symbol: string;
    timeframe: string;
    status: string;
    strategy_config?: { name: string };
    config?: any;
}

interface Signal {
    id?: string;
    decision: string;
    price: number;
    timestamp?: number | string;
    createdAt?: string;
    status?: string;
    type?: 'BUY' | 'SELL'; // Compatibilidad legacy
}

interface Position {
    symbol: string;
    side: 'LONG' | 'SHORT';
    entryPrice: number;
    amount: number;
    unrealizedPnL?: number;
}

export default function BotsPage() {
    const [bots, setBots] = useState<Bot[]>([]);
    const [selectedBot, setSelectedBot] = useState<Bot | null>(null);

    // Estados de datos en vivo
    const [chartData, setChartData] = useState<any[]>([]);
    const [signals, setSignals] = useState<Signal[]>([]);
    const [positions, setPositions] = useState<Position[]>([]);
    const [isLoadingChart, setIsLoadingChart] = useState(false);
    const [latestSignals, setLatestSignals] = useState<any[]>([]); // Top general (todos los bots)
    const [recentBotSignals, setRecentBotSignals] = useState<any[]>([]); // Últimas señales del bot seleccionado
    const [lastLiveSignalId, setLastLiveSignalId] = useState<string>('');

    // Hook de WebSocket
    const { lastMessage, sendMessage, isConnected } = useSocket();

    // 1. Cargar lista de bots al montar el componente
    useEffect(() => {
        fetchBots();
    }, []);

    const fetchBots = async () => {
        try {
            const response = await api.get('/bots/');
            // Asegurar que 'data' sea un array antes de actualizar el estado
            const payload = response.data;
            const data = Array.isArray(payload)
              ? payload
              : (Array.isArray(payload?.bots) ? payload.bots : []);
            setBots(data);
            // Seleccionar el primer bot si no hay selección actual y hay datos
            if (data.length > 0 && !selectedBot) {
                setSelectedBot(data[0]);
            }
        } catch (error) {
            console.error("Error cargando bots:", error);
            setBots([]); // Resetear a vacío en caso de error
        }
    };

    // 2. Manejo de Suscripción (Cada vez que cambia el bot seleccionado)
    useEffect(() => {
        if (!selectedBot) return;

        let cancelled = false;
        const activeBotId = selectedBot.id;

        // Resetear estados visuales al cambiar bot
        setIsLoadingChart(true);
        setChartData([]);
        setSignals([]);
        setPositions([]);
        setRecentBotSignals([]);

        // A) Cargar histórico de velas (>=40) y trades del bot por HTTP como bootstrap
        (async () => {
            try {
                const ex = (selectedBot as any).exchangeId || (selectedBot as any).exchange_id || 'binance';
                const mt = (selectedBot as any).marketType || (selectedBot as any).market_type || 'spot';

                const [candlesRes, tradesRes] = await Promise.all([
                    api.get('/market/candles', {
                        params: {
                            symbol: selectedBot.symbol,
                            timeframe: selectedBot.timeframe,
                            exchange_id: ex,
                            market_type: mt,
                            limit: 120,
                        }
                    }),
                    api.get(`/trades/bot/${activeBotId}`, { params: { limit: 300 } })
                ]);

                if (cancelled) return;

                const candles = Array.isArray(candlesRes?.data) ? candlesRes.data : [];
                const trades = Array.isArray(tradesRes?.data) ? tradesRes.data : [];

                if (candles.length > 0) setChartData(candles);
                if (trades.length > 0) setSignals(trades as any);
            } catch (e) {
                if (!cancelled) console.warn('Bootstrap histórico/trades falló, se usará snapshot WS', e);
            } finally {
                if (!cancelled) setIsLoadingChart(false);
            }
        })();

        // B) Suscribirse al Bot específico vía WebSocket
        if (isConnected) {
            sendMessage({
                action: "SUBSCRIBE_BOT",
                bot_id: activeBotId
            });
        }

        // C) Limpieza: evitar race conditions al cambiar rápido de bot
        return () => {
            cancelled = true;
            if (isConnected) {
                sendMessage({
                    action: "UNSUBSCRIBE_BOT",
                    bot_id: activeBotId
                });
            }
        };
    }, [selectedBot, isConnected]);

    // 3. Procesar Mensajes de WebSocket
    useEffect(() => {
        if (!lastMessage) return;

        const msg = lastMessage as any;
        const event = msg.event || msg.type; // Compatible con ambos formatos

        if (event === 'bot_snapshot') {
            // Inicialización completa desde el servidor
            if (msg.bot_id === selectedBot?.id) {
                const snapshotTrades = Array.isArray(msg.trades) ? msg.trades : [];
                const snapshotSignals = Array.isArray(msg.signals) ? msg.signals : [];
                const snapshotCandles = Array.isArray(msg.candles) ? msg.candles : [];

                // Priorizar trades (colección trades) para marcadores precisos del gráfico.
                setSignals(snapshotTrades.length > 0 ? snapshotTrades : snapshotSignals);
                setPositions(msg.positions || []);

                // Señales recientes del bot (arranca con histórico + luego live)
                const normalizedSignals = [...snapshotSignals]
                    .map((s: any) => ({
                        id: s.id || s._id,
                        decision: s.decision || s.type || s.signal,
                        symbol: s.symbol || selectedBot?.symbol,
                        reasoning: s.reasoning || s.status || '',
                        timestamp: s.timestamp || s.createdAt || Date.now(),
                    }))
                    .sort((a: any, b: any) => Number(new Date(b.timestamp as any)) - Number(new Date(a.timestamp as any)))
                    .slice(0, 10);
                setRecentBotSignals(normalizedSignals);
                if (normalizedSignals.length > 0) setLastLiveSignalId(String(normalizedSignals[0].id || ''));

                // IMPORTANTE: no pisar histórico ya cargado con [] si snapshot llega sin candles.
                if (snapshotCandles.length > 0) {
                    setChartData(snapshotCandles);
                }

                setIsLoadingChart(false); // Indicar que la carga inicial ha terminado
            }
        }
        else if (event === 'bot_update') {
            const data = msg.data || msg;
            if (data.id === selectedBot?.id) {
                // Actualizar PnL y Precio en tiempo real en la cabecera/lista
                setSelectedBot(prev => prev ? { ...prev, ...data } : null);
                // Si hay posiciones, podemos actualizarlas si el mensaje trae info
            }
        }
        else if (event === 'candle_update') {
            const data = msg.data || msg;
            if (data.symbol === selectedBot?.symbol) {
                const c = data.candle || {};
                const t = c.time ?? c.timestamp;
                if (!t) return;
                const candle = {
                    time: t,
                    open: Number(c.open),
                    high: Number(c.high),
                    low: Number(c.low),
                    close: Number(c.close),
                    volume: Number(c.volume || 0),
                };

                // Actualizar última vela o agregar nueva cuando cierre la actual
                setChartData(prev => {
                    if (!prev || prev.length === 0) return [candle];
                    const last = prev[prev.length - 1];
                    if (last && Number(last.time) === Number(candle.time)) {
                        const updated = [...prev];
                        updated[updated.length - 1] = { ...last, ...candle };
                        return updated;
                    }
                    return [...prev, candle];
                });
            }
        }
        else if (event === 'price_update') {
            const data = msg.data || msg;
            if (data.symbol !== selectedBot?.symbol) return;
            const price = Number(data.price);
            if (!Number.isFinite(price) || price <= 0) return;

            // Tick en vivo: actualizar cierre/alto/bajo de la vela en formación.
            setChartData(prev => {
                if (!prev || prev.length === 0) return prev;
                const updated = [...prev];
                const last = { ...updated[updated.length - 1] } as any;
                last.close = price;
                last.high = Math.max(Number(last.high ?? price), price);
                last.low = Math.min(Number(last.low ?? price), price);
                updated[updated.length - 1] = last;
                return updated;
            });
        }
        else if (event === 'signal_alert' || event === 'new_signal' || event === 'signal_update') {
            const data = msg.data || msg;
            // Actualizar señales del bot seleccionado
            if (data.botId === selectedBot?.id) {
                setSignals(prev => {
                    const existingIndex = prev.findIndex((s: any) => (s as any).id === data.id || (s as any)._id === data._id);
                    if (existingIndex > -1) {
                        const updatedSignals = [...prev];
                        updatedSignals[existingIndex] = { ...updatedSignals[existingIndex], ...data };
                        return updatedSignals;
                    } else {
                        return [...prev, data];
                    }
                });

                // Panel live de últimas 10 señales del bot seleccionado
                setRecentBotSignals(prev => {
                    const row = {
                        id: data.id || data._id || `${Date.now()}-${Math.random()}`,
                        decision: data.decision || data.type || data.signal,
                        symbol: data.symbol || selectedBot?.symbol,
                        reasoning: data.reasoning || data.status || '',
                        timestamp: data.timestamp || data.createdAt || Date.now(),
                    };
                    setLastLiveSignalId(String(row.id));
                    const dedup = [row, ...prev.filter((p: any) => String(p.id) !== String(row.id))];
                    return dedup.slice(0, 10);
                });
            }
            // Actualizar el panel de las últimas 5 señales (problema 2)
            if (data.type === 'BUY' || data.type === 'SELL' || data.decision === 'BUY' || data.decision === 'SELL') {
                setLatestSignals(prev => {
                    const newSignal = {
                        botName: bots.find(b => b.id === data.botId)?.name || 'Desconocido',
                        symbol: data.symbol || selectedBot?.symbol || 'Desconocido',
                        type: data.type || data.decision,
                        status: data.status || 'esperando',
                        timestamp: data.timestamp || data.createdAt || Date.now()
                    };
                    const updated = [newSignal, ...prev].slice(0, 5);
                    return updated;
                });
            }
        }
        else if (event === 'position_update' || event === 'operation_update') {
            const data = msg.data || msg;
            if (data.botId === selectedBot?.id) {
                // Actualizar lista de posiciones
                // Depende de si es un trade individual o el array completo
                setPositions(prev => {
                    // Lógica simplificada: si existe lo actualizamos, si no lo añadimos?
                    // Para SignalKey solemos tener una única posición por bot.
                    return [data];
                });
            }
        }

    }, [lastMessage, selectedBot]);

    const toMs = (t: any): number | null => {
        if (!t) return null;
        if (typeof t === 'string') return new Date(t).getTime();
        if (typeof t === 'number') return t > 20000000000 ? t : t * 1000; // ms vs seconds
        if (typeof t === 'object' && typeof t.$date === 'string') return new Date(t.$date).getTime();
        return null;
    };

    const timeframeToMs = (tf?: string): number => {
        const v = (tf || '1m').toLowerCase().trim();
        const m = v.match(/^(\d+)([mhdw])$/);
        if (!m) return 60_000;
        const n = Number(m[1]);
        const u = m[2];
        if (u === 'm') return n * 60_000;
        if (u === 'h') return n * 3_600_000;
        if (u === 'd') return n * 86_400_000;
        if (u === 'w') return n * 604_800_000;
        return 60_000;
    };

    // Transformar trades/señales en marcadores alineados al timeframe del bot.
    const tfMs = timeframeToMs(selectedBot?.timeframe);
    const botTrades = (signals || [])
        .map((sig: any, idx: number) => {
            const rawSide = String(sig.decision || sig.type || sig.side || sig.signal || '').toUpperCase();
            const side = (rawSide.includes('SELL') || rawSide.includes('SHORT') || rawSide === '2') ? 'SELL' : 'BUY';
            const msRaw = toMs(sig.timestamp) ?? toMs(sig.createdAt) ?? toMs(sig.openedAt);
            if (!msRaw) return null;

            // Alinear marcador a la vela del timeframe para que no queden desfasados.
            const ms = Math.floor(msRaw / tfMs) * tfMs;
            const price = Number(sig.price ?? sig.entryPrice ?? sig.avgEntryPrice ?? sig.executedPrice ?? 0);

            return {
                id: sig.id || sig._id || `${side}-${ms}-${idx}`,
                time: ms,
                side: side as 'BUY' | 'SELL',
                price,
                label: side,
                originalTime: msRaw,
            };
        })
        .filter((x: any) => !!x && Number.isFinite(x.price) && x.price > 0) as any[];

    const lastFiveOps = [...botTrades]
        .sort((a: any, b: any) => Number(b.originalTime || b.time) - Number(a.originalTime || a.time))
        .slice(0, 5);

    const livePrice = Number((chartData && chartData.length > 0)
        ? (chartData[chartData.length - 1]?.close)
        : 0);

    const activePos: any = positions && positions.length > 0 ? positions[0] : null;
    const entryPrice = Number(activePos?.avgEntryPrice ?? activePos?.entryPrice ?? 0);
    const currentQty = Number(activePos?.currentQty ?? activePos?.amount ?? 0);
    const sideRaw = String(activePos?.side ?? activePos?.direction ?? '').toUpperCase();
    const positionSide = sideRaw.includes('SHORT') || sideRaw.includes('SELL') ? 'SHORT' : (activePos ? 'LONG' : '-');

    const profitValue = (activePos && entryPrice > 0 && currentQty > 0 && Number.isFinite(livePrice) && livePrice > 0)
        ? (positionSide === 'SHORT'
            ? (entryPrice - livePrice) * currentQty
            : (livePrice - entryPrice) * currentQty)
        : 0;

    const pnlPercent = (activePos && entryPrice > 0 && Number.isFinite(livePrice) && livePrice > 0)
        ? ((positionSide === 'SHORT'
            ? (entryPrice - livePrice)
            : (livePrice - entryPrice)) / entryPrice) * 100
        : 0;

    // Manejadores de acciones
    const handleStartBot = async () => {
        if (!selectedBot) return;
        try {
            await api.post(`/bots/${selectedBot.id}/start`);
            setBots(prev => prev.map(b => b.id === selectedBot.id ? { ...b, status: 'running' } : b));
            setSelectedBot(prev => prev ? { ...prev, status: 'running' } : null);
        } catch (e) {
            console.error("Error iniciando bot", e);
        }
    };

    const handleStopBot = async () => {
        if (!selectedBot) return;
        try {
            await api.post(`/bots/${selectedBot.id}/stop`);
            setBots(prev => prev.map(b => b.id === selectedBot.id ? { ...b, status: 'stopped' } : b));
            setSelectedBot(prev => prev ? { ...prev, status: 'stopped' } : null);
        } catch (e) {
            console.error("Error deteniendo bot", e);
        }
    };

    return (
        <div className="flex flex-col h-[calc(100vh-4rem)] w-full bg-slate-950 text-slate-200 overflow-hidden">
            <style>{`
                @keyframes liveSignalSlideIn {
                    0% { transform: translateX(42px); opacity: 0; }
                    100% { transform: translateX(0); opacity: 1; }
                }
            `}</style>

            {/* --- Barra superior: Últimas señales --- */}
            <div className="w-full p-4 border-b border-slate-800 bg-slate-900/60 shrink-0">
                <h2 className="font-semibold flex items-center gap-2 text-sm mb-2">
                    <Zap className="h-4 w-4 text-primary" /> Últimas 5 Señales
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-2">
                    {latestSignals.length > 0 ? (
                        latestSignals.map((signal, index) => (
                            <Card key={index} className="bg-slate-800 border-slate-700 text-xs">
                                <CardContent className="p-2 flex flex-col gap-1">
                                    <div className="flex justify-between items-center">
                                        <span className="font-medium">{signal.botName}</span>
                                        <Badge variant={signal.type === 'BUY' ? 'success' : 'destructive'}>
                                            {signal.type}
                                        </Badge>
                                    </div>
                                    <div className="text-slate-400">{signal.symbol}</div>
                                    <div className="text-slate-400">Estado: {signal.status}</div>
                                    <div className="text-slate-500 text-[0.65rem]">
                                        {new Date(signal.timestamp).toLocaleTimeString()}
                                    </div>
                                </CardContent>
                            </Card>
                        ))
                    ) : (
                        <p className="text-slate-500 col-span-5">Esperando señales...</p>
                    )}
                </div>
            </div>

            <div className="flex-1 min-h-0 flex overflow-hidden">
                <div className="w-80 border-r border-slate-800 bg-slate-900/60 backdrop-blur-3xl flex flex-col hidden md:flex">
                <div className="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-900/60">
                    <h2 className="font-semibold flex items-center gap-2 text-sm">
                        <Activity className="h-4 w-4 text-primary" /> Mis Bots
                    </h2>
                    <div className="flex gap-1">
                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={fetchBots} title="Refrescar">
                            <RefreshCw className="h-3.5 w-3.5" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-8 w-8" title="Crear Bot">
                            <Plus className="h-3.5 w-3.5" />
                        </Button>
                    </div>
                </div>
                <ScrollArea className="flex-1 p-3">
                    <div className="space-y-2">
                        {Array.isArray(bots) && bots.map((bot) => (
                            <div
                                key={bot.id}
                                onClick={() => setSelectedBot(bot)}
                                className={`group flex flex-col gap-2 p-3 rounded-xl border cursor-pointer transition-all duration-200 ${selectedBot?.id === bot.id
                                    ? 'bg-primary/5 border-primary/50 shadow-sm'
                                    : 'bg-card hover:bg-accent/50 border-border hover:border-primary/20'
                                    }`}
                            >
                                <div className="flex justify-between items-start">
                                    <span className="font-semibold text-sm truncate pr-2">{bot.name}</span>
                                    <Badge
                                        variant={bot.status === 'running' ? 'default' : 'secondary'}
                                        className={`text-[10px] uppercase tracking-wider px-1.5 h-5 border-0 ${bot.status === 'running' ? 'bg-green-500/15 text-green-600' : 'bg-muted text-muted-foreground'
                                            }`}
                                    >
                                        {bot.status}
                                    </Badge>
                                </div>

                                <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                                    <div className="flex items-center gap-1.5 bg-muted/30 p-1 rounded">
                                        <TrendingUp className="h-3 w-3 opacity-70" />
                                        <span className="font-mono">{bot.symbol}</span>
                                    </div>
                                    <div className="flex items-center gap-1.5 bg-muted/30 p-1 rounded">
                                        <Clock className="h-3 w-3 opacity-70" />
                                        <span className="font-mono">{bot.timeframe}</span>
                                    </div>
                                </div>
                            </div>
                        ))}
                        {(!Array.isArray(bots) || bots.length === 0) && (
                            <div className="text-center p-4 text-xs text-muted-foreground opacity-50">
                                No se encontraron bots activos
                            </div>
                        )}
                    </div>
                </ScrollArea>
            </div>

            {/* --- Contenido Principal --- */}
            <div className="flex-1 flex flex-col min-w-0 bg-slate-950/60">

                {/* Header del Bot Seleccionado */}
                <header className="h-16 border-b border-slate-800 flex items-center px-6 justify-between bg-slate-900/60 backdrop-blur-sm sticky top-0 z-20">
                    <div className="flex items-center gap-6">
                        {selectedBot ? (
                            <div>
                                <div className="flex items-center gap-3">
                                    <h1 className="text-xl font-bold tracking-tight">{selectedBot.symbol}</h1>
                                    <Badge variant="outline" className="font-mono text-xs">{selectedBot.timeframe}</Badge>
                                    <Badge className="bg-primary/10 text-primary hover:bg-primary/20 border-primary/20">
                                        {selectedBot.strategy_config?.name || 'Estrategia Manual'}
                                    </Badge>
                                </div>
                                <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                                    <span className="flex items-center gap-1">ID: <span className="font-mono opacity-70">{selectedBot.id.substring(0, 8)}...</span></span>
                                </div>
                            </div>
                        ) : (
                            <div className="flex items-center gap-2 text-muted-foreground">
                                <Activity className="h-5 w-5" />
                                <span className="font-medium">Selecciona un bot para ver detalles</span>
                            </div>
                        )}
                    </div>

                    <div className="flex items-center gap-3">
                        {selectedBot && (
                            <>
                                {selectedBot.status === 'running' ? (
                                    <Button size="sm" variant="destructive" className="gap-2 h-8" onClick={handleStopBot}>
                                        <Square className="h-3 w-3 fill-current" /> Detener
                                    </Button>
                                ) : (
                                    <Button size="sm" className="gap-2 h-8 bg-green-600 hover:bg-green-700" onClick={handleStartBot}>
                                        <Play className="h-3 w-3 fill-current" /> Iniciar
                                    </Button>
                                )}
                                <Button variant="outline" size="icon" className="h-8 w-8">
                                    <Settings className="h-4 w-4" />
                                </Button>
                            </>
                        )}
                        <div className="h-6 w-px bg-border mx-2" />
                        <div className="flex items-center gap-2 text-xs font-medium">
                            <div className={`h-2.5 w-2.5 rounded-full shadow-sm transition-colors ${isConnected ? 'bg-green-500 shadow-green-500/50' : 'bg-red-500'}`} />
                            <span className={isConnected ? 'text-green-600' : 'text-red-500'}>
                                {isConnected ? 'En Línea' : 'Desconectado'}
                            </span>
                        </div>
                    </div>
                </header>

                {/* Área de Trabajo */}
                <main className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6">
                    {selectedBot ? (
                        <>
                            {/* Cards informativas rápidas */}
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                <Card className="shadow-sm"><CardContent className="p-3"><div className="text-xs text-muted-foreground">Operaciones</div><div className="text-lg font-semibold">{botTrades.length}</div></CardContent></Card>
                                <Card className="shadow-sm"><CardContent className="p-3"><div className="text-xs text-muted-foreground">Posición (currentQty)</div><div className="text-lg font-semibold font-mono">{activePos ? `${currentQty}` : '0'}</div></CardContent></Card>
                                <Card className="shadow-sm"><CardContent className="p-3"><div className="text-xs text-muted-foreground">Lado</div><div className={`text-lg font-semibold ${positionSide === 'SHORT' ? 'text-red-500' : 'text-green-500'}`}>{positionSide}</div></CardContent></Card>
                                <Card className="shadow-sm"><CardContent className="p-3"><div className="text-xs text-muted-foreground">Entry (avgEntryPrice)</div><div className="text-lg font-semibold font-mono">{entryPrice > 0 ? entryPrice : '-'}</div></CardContent></Card>
                                <Card className="shadow-sm"><CardContent className="p-3"><div className="text-xs text-muted-foreground">PnL % (live)</div><div className={`text-lg font-semibold font-mono ${pnlPercent >= 0 ? 'text-green-500' : 'text-red-500'}`}>{activePos ? `${pnlPercent >= 0 ? '+' : ''}${pnlPercent.toFixed(2)}%` : '-'}</div></CardContent></Card>
                                <Card className="shadow-sm"><CardContent className="p-3"><div className="text-xs text-muted-foreground">Profit (live)</div><div className={`text-lg font-semibold font-mono ${profitValue >= 0 ? 'text-green-500' : 'text-red-500'}`}>{activePos ? `${profitValue >= 0 ? '+' : ''}${profitValue.toFixed(4)}` : '-'}</div></CardContent></Card>
                            </div>

                            <Card className="shadow-sm md:col-span-3 border-primary/20 bg-gradient-to-r from-primary/5 to-transparent">
                                <CardHeader className="py-3 px-5 border-b bg-muted/10">
                                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                                        <span className="inline-flex items-center gap-2 rounded-full bg-red-500/15 text-red-400 px-2.5 py-1 text-xs font-semibold tracking-wide">
                                            <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
                                            EN VIVO
                                        </span>
                                        <Zap className="h-4 w-4 text-primary" /> Señales del bot (últimas 10)
                                    </CardTitle>
                                </CardHeader>
                                <CardContent className="p-3">
                                    <ScrollArea className="w-full whitespace-nowrap">
                                        {recentBotSignals.length > 0 ? (
                                            <div className="flex items-stretch gap-2 pb-1">
                                                <div className="shrink-0 rounded-lg border border-primary/30 bg-primary/10 px-3 py-2 flex items-center">
                                                    <span className="text-xs font-semibold tracking-wide text-primary">EN VIVO</span>
                                                </div>
                                                {recentBotSignals.map((s: any, idx: number) => {
                                                    const isSell = String(s.decision || '').toUpperCase().includes('SELL') || String(s.decision || '').toUpperCase().includes('SHORT');
                                                    const isNewest = String(s.id) === String(lastLiveSignalId);
                                                    return (
                                                        <div
                                                            key={s.id || idx}
                                                            className={`shrink-0 w-[290px] rounded-lg border p-3 flex items-center justify-between gap-3 transition-all ${isSell ? 'border-red-500/30 bg-red-500/5' : 'border-green-500/30 bg-green-500/5'} ${isNewest ? 'ring-2 ring-primary/50 shadow-lg' : ''}`}
                                                            style={isNewest ? { animation: 'liveSignalSlideIn 420ms cubic-bezier(.22,.9,.2,1)' } : undefined}
                                                        >
                                                            <div className="flex items-center gap-3 min-w-0">
                                                                <div className={`h-10 w-1.5 rounded-full ${isSell ? 'bg-red-500' : 'bg-green-500'}`} />
                                                                <div className="min-w-0">
                                                                    <div className="flex items-center gap-2">
                                                                        <Badge variant={isSell ? 'destructive' : 'default'} className="w-20 justify-center">
                                                                            {String(s.decision || 'SIGNAL').toUpperCase()}
                                                                        </Badge>
                                                                        <span className="text-sm font-medium truncate">{s.symbol || selectedBot.symbol}</span>
                                                                    </div>
                                                                    <div className="text-xs text-muted-foreground truncate mt-1">{s.reasoning || 'Señal recibida'}</div>
                                                                </div>
                                                            </div>
                                                            <span className="text-xs font-mono text-muted-foreground whitespace-nowrap">
                                                                {new Date(s.timestamp || Date.now()).toLocaleTimeString()}
                                                            </span>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        ) : (
                                            <div className="h-full flex items-center justify-center text-muted-foreground opacity-70 p-6 text-sm">
                                                Esperando señales en vivo para este bot...
                                            </div>
                                        )}
                                    </ScrollArea>
                                </CardContent>
                            </Card>

                            {/* Gráfico Principal */}
                            <Card className="flex flex-col shadow-sm border-muted transition-all hover:shadow-md min-h-[500px]">
                                <CardHeader className="py-3 px-5 border-b bg-muted/5 flex flex-row justify-between items-center">
                                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                                        <Activity className="h-4 w-4 text-muted-foreground" /> Análisis en Tiempo Real
                                    </CardTitle>
                                </CardHeader>
                                <CardContent className="flex-1 p-0 relative min-h-[450px]">
                                    {isLoadingChart && (
                                        <div className="absolute inset-0 flex flex-col items-center justify-center bg-background/80 z-10 backdrop-blur-[1px]">
                                            <RefreshCw className="h-8 w-8 text-primary animate-spin mb-2" />
                                            <span className="text-sm font-medium text-muted-foreground">Sincronizando mercado...</span>
                                        </div>
                                    )}
                                    <TradingViewChart
                                        data={chartData}
                                        symbol={selectedBot.symbol}
                                        timeframe={selectedBot.timeframe}
                                        trades={botTrades}
                                    />
                                </CardContent>
                            </Card>

                            {/* Últimas 5 operaciones del bot (desde trades) */}
                            <Card className="shadow-sm">
                                <CardHeader className="py-3 px-5 border-b bg-muted/5">
                                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                                        <Zap className="h-4 w-4 text-primary" /> Últimas 5 operaciones
                                    </CardTitle>
                                </CardHeader>
                                <CardContent className="p-0">
                                    <ScrollArea className="h-[180px]">
                                        {lastFiveOps.length > 0 ? (
                                            <div className="divide-y">
                                                {lastFiveOps.map((op: any, idx: number) => (
                                                    <div key={op.id || idx} className="flex items-center justify-between p-3 text-sm">
                                                        <div className="flex items-center gap-2">
                                                            <Badge variant={op.side === 'BUY' ? 'default' : 'destructive'} className="w-16 justify-center">
                                                                {op.side}
                                                            </Badge>
                                                            <span className="font-mono text-xs text-muted-foreground">
                                                                {new Date(op.originalTime || op.time).toLocaleString()}
                                                            </span>
                                                        </div>
                                                        <div className="font-mono font-medium">{op.price}</div>
                                                    </div>
                                                ))}
                                            </div>
                                        ) : (
                                            <div className="h-full flex items-center justify-center text-muted-foreground opacity-60 p-6 text-sm">
                                                Sin operaciones para este bot
                                            </div>
                                        )}
                                    </ScrollArea>
                                </CardContent>
                            </Card>

                            {/* Panel Inferior: Métricas y Registros */}
                            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

                                {/* Posiciones Activas */}
                                <Card className="lg:col-span-1 shadow-sm">
                                    <CardHeader className="py-3 px-5 border-b bg-muted/5">
                                        <CardTitle className="text-sm font-medium flex items-center gap-2">
                                            <Wallet className="h-4 w-4 text-blue-500" /> Posiciones Abiertas
                                        </CardTitle>
                                    </CardHeader>
                                    <CardContent className="p-0">
                                        <ScrollArea className="h-[250px]">
                                            {positions.length > 0 ? positions.map((pos, idx) => (
                                                <div key={idx} className="p-4 border-b last:border-0 flex flex-col gap-2 hover:bg-muted/5">
                                                    <div className="flex justify-between items-center">
                                                        <Badge variant="outline" className={`${pos.side === 'LONG'
                                                            ? 'bg-green-500/10 text-green-600 border-green-200'
                                                            : 'bg-red-500/10 text-red-600 border-red-200'
                                                            }`}>
                                                            {pos.side}
                                                        </Badge>
                                                        <span className="font-mono font-medium">{pos.amount} {selectedBot.symbol.split('/')[0]}</span>
                                                    </div>
                                                    <div className="flex justify-between text-sm">
                                                        <span className="text-muted-foreground">Entrada:</span>
                                                        <span className="font-mono">{pos.entryPrice}</span>
                                                    </div>
                                                    {pos.unrealizedPnL !== undefined && (
                                                        <div className="flex justify-between text-sm">
                                                            <span className="text-muted-foreground">PnL (No realizado):</span>
                                                            <span className={`font-mono font-bold ${pos.unrealizedPnL >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                                                {pos.unrealizedPnL > 0 ? '+' : ''}{pos.unrealizedPnL}%
                                                            </span>
                                                        </div>
                                                    )}
                                                </div>
                                            )) : (
                                                <div className="h-full flex flex-col items-center justify-center text-muted-foreground opacity-60 p-6">
                                                    <Wallet className="h-10 w-10 mb-2 stroke-1" />
                                                    <span className="text-sm">Sin posiciones activas</span>
                                                </div>
                                            )}
                                        </ScrollArea>
                                    </CardContent>
                                </Card>

                                {/* Historial de Señales */}
                                <Card className="lg:col-span-2 shadow-sm">
                                    <CardHeader className="py-3 px-5 border-b bg-muted/5">
                                        <CardTitle className="text-sm font-medium flex items-center gap-2">
                                            <Zap className="h-4 w-4 text-amber-500" /> Registro de Señales
                                        </CardTitle>
                                    </CardHeader>
                                    <CardContent className="p-0">
                                        <ScrollArea className="h-[250px]">
                                            <div className="min-w-full inline-block align-middle">
                                                {signals.length > 0 ? (
                                                    <div className="divide-y">
                                                        {signals.slice().reverse().map((sig, idx) => {
                                                            const isBuy = sig.decision === 'BUY' || sig.type === 'BUY';
                                                            return (
                                                                <div key={idx} className="flex items-center justify-between p-3 hover:bg-muted/5 transition-colors">
                                                                    <div className="flex items-center gap-3">
                                                                        <div className={`w-1 h-8 rounded-full ${isBuy ? 'bg-green-500' : 'bg-red-500'}`} />
                                                                        <div className="flex flex-col">
                                                                            <span className="font-medium text-sm flex items-center gap-2">
                                                                                {isBuy ? 'Compra Detectada' : 'Venta Detectada'}
                                                                            </span>
                                                                            <span className="text-xs text-muted-foreground font-mono">
                                                                                {new Date(sig.createdAt || sig.timestamp || Date.now()).toLocaleString()}
                                                                            </span>
                                                                        </div>
                                                                    </div>
                                                                    <div className="flex items-center gap-4 text-sm">
                                                                        <div className="flex flex-col items-end">
                                                                            <span className="text-muted-foreground text-xs">Precio Señal</span>
                                                                            <span className="font-mono font-medium">{sig.price}</span>
                                                                        </div>
                                                                        <Badge variant={isBuy ? 'default' : 'destructive'} className="w-20 justify-center">
                                                                            {sig.decision || sig.type}
                                                                        </Badge>
                                                                    </div>
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                ) : (
                                                    <div className="h-full flex flex-col items-center justify-center text-muted-foreground opacity-60 p-6 min-h-[200px]">
                                                        <Zap className="h-10 w-10 mb-2 stroke-1" />
                                                        <span className="text-sm">Esperando nuevas señales...</span>
                                                    </div>
                                                )}
                                            </div>
                                        </ScrollArea>
                                    </CardContent>
                                </Card>
                            </div>
                        </>
                    ) : (
                        <div className="flex flex-col items-center justify-center h-full text-muted-foreground opacity-50 space-y-4">
                            <div className="relative">
                                <Activity className="h-24 w-24 stroke-1 opacity-50" />
                                <div className="absolute -bottom-2 -right-2 bg-primary/20 p-2 rounded-full">
                                    <Settings className="h-6 w-6 text-primary" />
                                </div>
                            </div>
                            <div className="text-center">
                                <h3 className="text-lg font-medium text-foreground">Selecciona un Bot</h3>
                                <p className="text-sm max-w-xs mx-auto mt-1">
                                    Elige un bot del menú lateral para ver su análisis en tiempo real, señales y gestión de posiciones.
                                </p>
                            </div>
                        </div>
                    )}
                </main>
            </div>
            </div>
        </div>
    );
}