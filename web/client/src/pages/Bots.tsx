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
    type: 'BUY' | 'SELL';
    price: number;
    timestamp: number | string;
    status?: string;
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

    // Hook de WebSocket
    const { lastJsonMessage, sendJsonMessage, readyState } = useSocket();

    // 1. Cargar lista de bots al montar el componente
    useEffect(() => {
        fetchBots();
    }, []);

    const fetchBots = async () => {
        try {
            const response = await api.get('/bots');
            const data = response.data || [];
            setBots(data);
            // Seleccionar el primer bot si no hay selección actual
            if (data.length > 0 && !selectedBot) {
                setSelectedBot(data[0]);
            }
        } catch (error) {
            console.error("Error cargando bots:", error);
        }
    };

    // 2. Manejo de Suscripción (Cada vez que cambia el bot seleccionado)
    useEffect(() => {
        if (!selectedBot) return;

        // Resetear estados visuales
        setIsLoadingChart(true);
        setChartData([]);
        setSignals([]);
        setPositions([]);

        // A) Cargar historial de velas (para que el gráfico no empiece vacío)
        const fetchHistory = async () => {
            try {
                const response = await api.get(`/market/candles`, {
                    params: {
                        symbol: selectedBot.symbol,
                        timeframe: selectedBot.timeframe,
                        limit: 1000
                    }
                });
                setChartData(response.data || []);
            } catch (error) {
                console.error("Error historial API:", error);
            } finally {
                setIsLoadingChart(false);
            }
        };
        fetchHistory();

        // B) Suscribirse al Bot específico vía WebSocket
        if (readyState === 1) { // 1 = OPEN
            console.log(`[Bots] Suscribiendo al ID: ${selectedBot.id}`);
            sendJsonMessage({
                action: 'SUBSCRIBE_BOT',
                bot_id: selectedBot.id
            });
        }

        // C) Limpieza: Desuscribirse al cambiar de bot o desmontar
        return () => {
            if (readyState === 1) {
                console.log(`[Bots] Desuscribiendo ID: ${selectedBot.id}`);
                sendJsonMessage({
                    action: 'UNSUBSCRIBE_BOT',
                    bot_id: selectedBot.id
                });
            }
        };
    }, [selectedBot?.id, readyState]);

    // 3. Procesador de Mensajes en Tiempo Real
    useEffect(() => {
        if (!lastJsonMessage) return;

        const msg = lastJsonMessage as any;

        // Solo procesar mensajes si son relevantes para el contexto actual
        // (Opcional: verificar msg.bot_id si el backend lo envía en todos los eventos)

        if (msg.type === 'bot_snapshot') {
            // Snapshot inicial recibido al suscribirse
            console.log("Snapshot recibido:", msg);
            if (msg.signals) setSignals(msg.signals);
            if (msg.positions) setPositions(msg.positions);
            // Si el backend enviara 'candles' en el snapshot, podríamos actualizar chartData aquí también
        }
        else if (msg.type === 'signal_new' || msg.type === 'signal_update') {
            // Nueva señal generada
            console.log("Nueva señal:", msg.data);
            setSignals(prev => [...prev, msg.data]);
        }
        else if (msg.type === 'position_update') {
            // Actualización de posiciones
            setPositions(msg.data);
        }
        // Nota: Las actualizaciones de precio (velas) se pasan directamente al gráfico vía props

    }, [lastJsonMessage]);

    // Transformar señales en marcadores para el gráfico
    const chartMarkers = signals.map(sig => ({
        time: typeof sig.timestamp === 'string' ? new Date(sig.timestamp).getTime() / 1000 : sig.timestamp,
        position: sig.type === 'BUY' ? 'belowBar' : 'aboveBar',
        color: sig.type === 'BUY' ? '#2196F3' : '#E91E63',
        shape: sig.type === 'BUY' ? 'arrowUp' : 'arrowDown',
        text: sig.type,
        size: 2, // Tamaño relativo del marcador
    }));

    // Manejadores de acciones
    const handleStartBot = async () => {
        if (!selectedBot) return;
        try {
            await api.post(`/bots/${selectedBot.id}/start`);
            // Actualizamos la lista localmente o refrescamos
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
        <div className="flex h-[calc(100vh-4rem)] w-full bg-background overflow-hidden">

            {/* --- Sidebar: Lista de Bots --- */}
            <div className="w-80 border-r bg-card/30 flex flex-col hidden md:flex">
                <div className="p-4 border-b flex justify-between items-center bg-background/50">
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
                        {bots.map((bot) => (
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
                    </div>
                </ScrollArea>
            </div>

            {/* --- Contenido Principal --- */}
            <div className="flex-1 flex flex-col min-w-0 bg-background/50">

                {/* Header del Bot Seleccionado */}
                <header className="h-16 border-b flex items-center px-6 justify-between bg-card/50 backdrop-blur-sm sticky top-0 z-20">
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
                            <div className={`h-2.5 w-2.5 rounded-full shadow-sm transition-colors ${readyState === 1 ? 'bg-green-500 shadow-green-500/50' : 'bg-red-500'}`} />
                            <span className={readyState === 1 ? 'text-green-600' : 'text-red-500'}>
                                {readyState === 1 ? 'En Línea' : 'Desconectado'}
                            </span>
                        </div>
                    </div>
                </header>

                {/* Área de Trabajo */}
                <main className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6">
                    {selectedBot ? (
                        <>
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
                                        interval={selectedBot.timeframe}
                                        socketData={lastJsonMessage} // Pasa actualizaciones de velas en tiempo real
                                        markers={chartMarkers}       // Pinta las señales de compra/venta
                                    />
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
                                                        {signals.slice().reverse().map((sig, idx) => (
                                                            <div key={idx} className="flex items-center justify-between p-3 hover:bg-muted/5 transition-colors">
                                                                <div className="flex items-center gap-3">
                                                                    <div className={`w-1 h-8 rounded-full ${sig.type === 'BUY' ? 'bg-green-500' : 'bg-red-500'}`} />
                                                                    <div className="flex flex-col">
                                                                        <span className="font-medium text-sm flex items-center gap-2">
                                                                            {sig.type === 'BUY' ? 'Compra Detectada' : 'Venta Detectada'}
                                                                        </span>
                                                                        <span className="text-xs text-muted-foreground font-mono">
                                                                            {new Date(Number(sig.timestamp)).toLocaleString()}
                                                                        </span>
                                                                    </div>
                                                                </div>
                                                                <div className="flex items-center gap-4 text-sm">
                                                                    <div className="flex flex-col items-end">
                                                                        <span className="text-muted-foreground text-xs">Precio Señal</span>
                                                                        <span className="font-mono font-medium">{sig.price}</span>
                                                                    </div>
                                                                    <Badge variant={sig.type === 'BUY' ? 'default' : 'destructive'} className="w-20 justify-center">
                                                                        {sig.type}
                                                                    </Badge>
                                                                </div>
                                                            </div>
                                                        ))}
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
    );
}
