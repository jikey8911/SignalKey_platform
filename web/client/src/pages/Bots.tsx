import React, { useState, useEffect, useMemo } from 'react';
import {
    Play, Pause, Trash2, Cpu, Activity, TrendingUp, ShieldCheck, Zap,
    LayoutDashboard, Signal, History, Settings as SettingsIcon, BrainCircuit,
    Database, Coins, Menu, X, ArrowUpRight, ArrowDownRight, Clock,
    CheckCircle2, RotateCcw, Search, Bell
} from 'lucide-react';
import { useAuth } from '@/_core/hooks/useAuth';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useSocketContext } from '@/contexts/SocketContext';
import { toast } from 'react-hot-toast';
import { CONFIG } from '@/config';
import { TradingViewChart } from '@/components/ui/TradingViewChart';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Separator } from '@/components/ui/separator';

// --- MONITOR HÍBRIDO (Integrado con Socket Tarea 4.3 & 4.5) ---

const ExecutionMonitor = ({ bot }: any) => {
    const { lastMessage } = useSocketContext();
    const [liveSignals, setLiveSignals] = useState<any[]>([]);
    const [historySignals, setHistorySignals] = useState<any[]>([]);
    const [candles, setCandles] = useState<any[]>([]);
    const [loading, setLoading] = useState(false);

    // Fetch Initial Candles & Signal History
    useEffect(() => {
        if (!bot?.id || !bot?.symbol) return;

        const fetchData = async () => {
            setLoading(true);
            try {
                // Fetch Candles
                const candleRes = await fetch(`${CONFIG.API_BASE_URL}/market/candles?symbol=${encodeURIComponent(bot.symbol)}&timeframe=${bot.timeframe || '1h'}&limit=100`);
                if (candleRes.ok) {
                    const data = await candleRes.json();
                    setCandles(data);
                }

                // Fetch History Signals (New Endpoint S9)
                const signalRes = await fetch(`${CONFIG.API_BASE_URL}/bots/${bot.id}/signals`);
                if (signalRes.ok) {
                    const data = await signalRes.json();
                    setHistorySignals(data);
                }
            } catch (e) {
                console.error("Error fetching monitor data", e);
            } finally {
                setLoading(false);
            }
        };
        fetchData();
        setLiveSignals([]); // Reset live signals when changing bot
    }, [bot?.id, bot?.symbol, bot?.timeframe]);

    // Integración real: Añadir señal del socket a la lista visual
    useEffect(() => {
        if (lastMessage && (lastMessage.event === 'signal_update' || lastMessage.event === 'live_execution_signal')) {
            const signalData = lastMessage.data;
            if (signalData?.bot_id === bot?.id) {
                setLiveSignals(prev => [signalData, ...prev].slice(0, 5));
                // Also add to history for chart
                setHistorySignals(prev => [...prev, signalData]);
            }
        }
    }, [lastMessage, bot?.id]);

    const combinedSignals = useMemo(() => {
        return [...historySignals];
    }, [historySignals]);

    return (
        <Card className="overflow-hidden border-blue-500/20">
            <div className="p-4 border-b border-white/5 bg-slate-900/80 flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="h-2 w-2 bg-blue-500 rounded-full animate-pulse" />
                    <h4 className="text-xs font-bold text-white uppercase tracking-widest flex items-center gap-2 font-mono">
                        <ShieldCheck className="w-4 h-4 text-blue-500" />
                        Live Monitor sp4.5: {bot?.symbol || 'GLOBAL'}
                    </h4>
                </div>
                <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-[10px]">{bot?.timeframe}</Badge>
                    <Badge variant="success" className="bg-green-500/10 text-green-400 border-green-500/20">WS Active</Badge>
                </div>
            </div>

            <div className="p-6">
                <div className="mb-6">
                    {loading ? (
                        <div className="h-64 flex items-center justify-center bg-slate-950/50 rounded-lg border border-white/5 text-slate-500">
                            Cargando datos del mercado...
                        </div>
                    ) : (
                        <TradingViewChart
                            data={candles}
                            trades={combinedSignals.map(s => ({
                                time: new Date(s.createdAt || Date.now()).getTime(),
                                price: s.price,
                                side: (s.decision?.includes('BUY') || s.type === 'LONG' || s.side === 'buy') ? 'BUY' : 'SELL',
                                label: s.decision || s.type || s.side
                            }))}
                            height={320}
                        />
                    )}
                </div>

                <div className="space-y-2">
                    <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Flujo de ejecución reciente</p>
                    {liveSignals.length === 0 && historySignals.length === 0 ? (
                        <p className="text-xs text-slate-600 italic">Esperando señales del servidor...</p>
                    ) : (
                        [...liveSignals, ...historySignals].slice(0, 5).map((sig, idx) => (
                            <div key={idx} className="flex justify-between items-center text-xs p-2 bg-white/5 rounded-lg border border-white/5 animate-in slide-in-from-left-2">
                                <span className={(sig.decision?.includes('BUY') || sig.type === 'LONG' || sig.side === 'buy') ? 'text-blue-400' : 'text-amber-400'}>
                                    ● {sig.decision || sig.type || sig.side}
                                </span>
                                <span className="text-white font-mono">${sig.price?.toFixed(2)}</span>
                                <span className="text-[10px] text-slate-500">
                                    {new Date(sig.createdAt || Date.now()).toLocaleTimeString()}
                                </span>
                            </div>
                        ))
                    )}
                </div>
            </div>
        </Card>
    );
};

// --- CONFIG MODULE ---
const BotInfoModule = ({ bot }: { bot: any }) => {
    return (
        <div className="space-y-6 animate-in slide-in-from-bottom-2 duration-500">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Status Card */}
                <Card className="p-6 bg-slate-900 border-white/10">
                    <h3 className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-4 border-b border-white/5 pb-2">Estado General</h3>
                    <div className="space-y-4">
                        <div className="flex justify-between items-center">
                            <span className="text-slate-500 text-sm">Estado:</span>
                            <Badge variant={bot.status === 'active' ? 'success' : 'secondary'} className="uppercase">
                                {bot.status === 'active' ? 'ACTIVO' : 'PAUSADO'}
                            </Badge>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-slate-500 text-sm">Modo:</span>
                            <Badge variant={bot.mode === 'real' ? 'destructive' : 'outline'} className="uppercase border-blue-500/50">
                                {bot.mode === 'real' ? 'REAL TRADING' : 'SIMULACIÓN'}
                            </Badge>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-slate-500 text-sm">Par:</span>
                            <span className="font-mono text-white text-lg font-bold">{bot.symbol}</span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-slate-500 text-sm">Estrategia:</span>
                            <span className="text-blue-400 font-medium">{bot.strategy_name}</span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-slate-500 text-sm">Timeframe:</span>
                            <span className="text-white font-mono bg-slate-800 px-2 rounded">{bot.timeframe}</span>
                        </div>
                    </div>
                </Card>

                {/* Configuration Card */}
                <Card className="p-6 bg-slate-900 border-white/10">
                    <h3 className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-4 border-b border-white/5 pb-2">Configuración de Riesgo</h3>
                    <div className="space-y-4">
                        <div className="flex justify-between items-center">
                            <span className="text-slate-500 text-sm">Monto Inversión:</span>
                            <span className="font-mono text-white">${bot.amount?.toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-slate-500 text-sm">Take Profits:</span>
                            <div className="flex gap-1">
                                {(bot.takeProfits || []).map((tp: any, idx: number) => (
                                    <Badge key={idx} variant="outline" className={`text-[10px] ${tp.status === 'hit' ? 'bg-green-500/20 text-green-400' : 'text-slate-500'}`}>
                                        {tp.price?.toFixed(2)}
                                    </Badge>
                                ))}
                                {(!bot.takeProfits || bot.takeProfits.length === 0) && <span className="text-xs text-slate-600">Auto (IA)</span>}
                            </div>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-slate-500 text-sm">Stop Loss:</span>
                            <span className="font-mono text-red-400">${bot.stopLoss?.toFixed(4) || '---'}</span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-slate-500 text-sm">Leverage:</span>
                            <span className="font-mono text-amber-500">x{bot.leverage || 1}</span>
                        </div>
                    </div>
                </Card>
            </div>

            {/* Performance Snapshot */}
            <Card className="p-6 bg-gradient-to-r from-blue-900/10 to-slate-900/50 border-white/5">
                <h3 className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-2">Snapshot de Rendimiento</h3>
                <div className="flex gap-8 items-end">
                    <div>
                        <p className="text-xs text-slate-500 mb-1">PnL Actual</p>
                        <p className={`text-3xl font-black ${bot.pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                            {bot.pnl > 0 ? '+' : ''}{bot.pnl?.toFixed(2) || '0.00'}%
                        </p>
                    </div>
                    <div>
                        <p className="text-xs text-slate-500 mb-1">Precio Entrada</p>
                        <p className="text-xl font-mono text-white">${bot.entryPrice?.toFixed(4)}</p>
                    </div>
                    <div>
                        <p className="text-xs text-slate-500 mb-1">Precio Actual</p>
                        <p className="text-xl font-mono text-white">${bot.current_price?.toFixed(4) || '---'}</p>
                    </div>
                </div>
            </Card>
        </div>
    );
}

const SignalHistoryModule = ({ botId }: { botId: string }) => {
    const [signals, setSignals] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchHistory = async () => {
            setLoading(true);
            try {
                const res = await fetch(`${CONFIG.API_BASE_URL}/bots/${botId}/signals`);
                if (res.ok) {
                    const data = await res.json();
                    setSignals(data.sort((a: any, b: any) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()));
                }
            } catch (e) {
                console.error("Error fetching history", e);
            } finally {
                setLoading(false);
            }
        };
        fetchHistory();
    }, [botId]);

    if (loading) return <div className="text-center py-10 text-slate-500 animate-pulse">Cargando historial...</div>;

    return (
        <Card className="overflow-hidden bg-slate-900 border-white/10 animate-in fade-in slide-in-from-bottom-4">
            <div className="max-h-[500px] overflow-y-auto custom-scrollbar">
                <table className="w-full text-left text-sm text-slate-400">
                    <thead className="bg-slate-950 text-xs uppercase font-medium text-slate-500 sticky top-0 z-10">
                        <tr>
                            <th className="px-6 py-4 bg-slate-950">Fecha</th>
                            <th className="px-6 py-4 bg-slate-950">Señal</th>
                            <th className="px-6 py-4 bg-slate-950">Precio</th>
                            <th className="px-6 py-4 bg-slate-950">Confianza</th>
                            <th className="px-6 py-4 bg-slate-950 text-right">Estado</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                        {signals.length === 0 ? (
                            <tr>
                                <td colSpan={5} className="px-6 py-10 text-center text-slate-600 italic">
                                    No hay señales registradas para este bot.
                                </td>
                            </tr>
                        ) : (
                            signals.map((signal) => (
                                <tr key={signal.id} className="hover:bg-white/5 transition-colors">
                                    <td className="px-6 py-4 font-mono text-xs text-slate-500">
                                        {new Date(signal.createdAt).toLocaleString()}
                                    </td>
                                    <td className="px-6 py-4">
                                        <Badge variant="outline" className={`${signal.decision?.toLowerCase().includes('buy') ? 'text-green-400 border-green-500/30 bg-green-500/10' : signal.decision?.toLowerCase().includes('sell') ? 'text-red-400 border-red-500/30 bg-red-500/10' : 'text-slate-400 border-slate-500/30'}`}>
                                            {signal.decision}
                                        </Badge>
                                    </td>
                                    <td className="px-6 py-4 font-mono text-white">
                                        {signal.price ? `$${signal.price.toFixed(2)}` : '---'}
                                    </td>
                                    <td className="px-6 py-4">
                                        {signal.confidence ? (
                                            <div className="flex items-center gap-2">
                                                <div className="h-1.5 w-16 bg-slate-800 rounded-full overflow-hidden">
                                                    <div className="h-full bg-blue-500" style={{ width: `${signal.confidence * 100}%` }} />
                                                </div>
                                                <span className="text-xs">{Math.round(signal.confidence * 100)}%</span>
                                            </div>
                                        ) : '-'}
                                    </td>
                                    <td className="px-6 py-4 text-right">
                                        <span className="text-xs text-slate-500 lowercase">{signal.status || 'processed'}</span>
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>
        </Card>
    );
};


const GlobalSignalTicker = () => {
    const { lastMessage } = useSocketContext();
    const [globalSignals, setGlobalSignals] = useState<any[]>([]);

    useEffect(() => {
        if (lastMessage && (lastMessage.event === 'signal_update' || lastMessage.event === 'live_execution_signal')) {
            // Add to global list regardless of selected bot
            setGlobalSignals(prev => {
                const newSig = lastMessage.data;
                // Avoid duplicates if unique ID exists
                if (prev.find(s => s.id === newSig.id && s.timestamp === newSig.timestamp)) return prev;
                return [newSig, ...prev].slice(0, 8); // Keep last 8
            });
        }
    }, [lastMessage]);

    if (globalSignals.length === 0) return (
        <Card className="mb-6 p-4 bg-slate-900/50 border-dashed border-white/10 flex items-center justify-center gap-2 text-slate-500 text-xs">
            <Activity className="w-4 h-4" />
            Esperando señales de la red neuronal...
        </Card>
    );

    return (
        <Card className="mb-6 bg-slate-950 border-blue-500/20 overflow-hidden relative">
            <div className="absolute top-0 left-0 w-1 h-full bg-blue-500 animate-pulse" />
            <div className="p-3 flex items-center gap-4 overflow-x-auto custom-scrollbar">
                <div className="flex items-center gap-2 pr-4 border-r border-white/10 shrink-0">
                    <BrainCircuit className="w-5 h-5 text-blue-500" />
                    <div className="flex flex-col">
                        <span className="text-[10px] uppercase font-bold text-white leading-none">Global</span>
                        <span className="text-[10px] text-blue-400 font-mono tracking-wider">LIVE FEED</span>
                    </div>
                </div>

                <div className="flex gap-3">
                    {globalSignals.map((sig, idx) => (
                        <div key={idx} className="flex flex-col bg-white/5 rounded px-3 py-1.5 min-w-[100px] border border-white/5 animate-in slide-in-from-right-4 fade-in duration-500">
                            <div className="flex justify-between items-center mb-1">
                                <span className="text-[10px] font-bold text-slate-300">{sig.symbol || 'UNK'}</span>
                                <span className="text-[9px] text-slate-500">{new Date(sig.createdAt || Date.now()).toLocaleTimeString()}</span>
                            </div>
                            <div className="flex justify-between items-center">
                                <Badge variant="outline" className={`h-4 text-[9px] px-1 ${(sig.decision?.includes('BUY') || sig.type === 'LONG') ? 'text-green-400 border-green-500/30' : 'text-red-400 border-red-500/30'}`}>
                                    {sig.decision || sig.type}
                                </Badge>
                                <span className="text-[10px] font-mono text-white">${sig.price?.toFixed(2)}</span>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </Card>
    );
};

// --- PÁGINA DE BOTS ---

const BotsPage = () => {
    const { user } = useAuth();
    const [bots, setBots] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const { lastMessage } = useSocketContext();

    const fetchBots = async () => {
        if (!user?.openId) return;

        try {
            const res = await fetch(`${CONFIG.API_BASE_URL}/bots/`);
            if (res.ok) {
                const data = await res.json();
                setBots(data);
                if (data.length > 0 && !selectedId) {
                    setSelectedId(data[0].id);
                }
            }
        } catch (e) {
            console.error("Error fetching bots:", e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (user?.openId) {
            fetchBots();
            const interval = setInterval(fetchBots, 60000);
            return () => clearInterval(interval);
        }
    }, [user?.openId]);

    // Also update on active_bot_update socket event if available
    useEffect(() => {
        if (lastMessage && lastMessage.event === 'bot_update') {
            setBots(prev => prev.map(b => b.id === lastMessage.data.id ? { ...b, ...lastMessage.data } : b));
        }
    }, [lastMessage]);

    const activeBot = useMemo(() => bots.find(b => b.id === selectedId), [bots, selectedId]);

    const handleDelete = async (e: React.MouseEvent, id: string) => {
        e.stopPropagation();
        if (!confirm("Eliminar bot?")) return;
        try {
            const res = await fetch(`http://localhost:8000/api/bots/${id}`, { method: 'DELETE' });
            if (res.ok) {
                toast.success("Bot eliminado");
                fetchBots();
                if (selectedId === id) setSelectedId(null);
            }
        } catch (e) {
            toast.error("Error eliminando bot");
        }
    }

    return (
        <div className="p-8 space-y-8 animate-in fade-in duration-500">
            <div className="flex justify-between items-center">
                <h1 className="text-4xl font-black text-white tracking-tighter uppercase italic">Control de Bots <span className="text-blue-500">sp4</span></h1>
                <div className="flex gap-4">
                    <Button variant="outline" onClick={fetchBots} disabled={loading}>
                        <RotateCcw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} /> Refresh
                    </Button>
                    <Badge variant="success" className="py-2 px-4 shadow-lg shadow-green-500/10 h-10 flex items-center">
                        <Zap className="w-3 h-3 mr-2 fill-current" /> AutoTrade Sync
                    </Badge>
                </div>
            </div>

            {loading && bots.length === 0 ? (
                <div className="text-center py-20 text-slate-500">Cargando Bots...</div>
            ) : (
                <div className="grid grid-cols-1 xl:grid-cols-4 gap-8">
                    {/* Lista de Bots */}
                    <div className="xl:col-span-1 space-y-4 max-h-[80vh] overflow-y-auto pr-2 custom-scrollbar">
                        {bots.length === 0 && <div className="text-slate-500 italic p-4">No hay bots activos. Crea uno en el Strategy Lab.</div>}

                        {bots.map((bot) => (
                            <Card
                                key={bot.id}
                                className={`p-5 cursor-pointer border-l-4 transition-all hover:bg-white/5 group relative ${selectedId === bot.id ? 'border-l-blue-500 bg-blue-500/5' : 'border-l-transparent opacity-70 hover:opacity-100'}`}
                                onClick={() => setSelectedId(bot.id)}
                            >
                                <div className="flex justify-between items-start mb-3">
                                    <div className="flex gap-2">
                                        {/* Badge de Modo */}
                                        {bot.mode === 'real' ? (
                                            <Badge className="bg-green-500/20 text-green-400 border-green-500/50 text-[10px]">Real Live</Badge>
                                        ) : (
                                            <Badge variant="secondary" className="text-[10px] bg-slate-700 text-slate-300">Simulación</Badge>
                                        )}
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <div className={`h-2 w-2 rounded-full ${bot.status === 'active' ? 'bg-green-500 animate-pulse' : 'bg-slate-600'}`} />
                                        <button onClick={(e) => handleDelete(e, bot.id)} className="opacity-0 group-hover:opacity-100 transition-opacity hover:text-red-500">
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    </div>
                                </div>
                                <h4 className="text-lg font-bold text-white leading-tight mb-1">{bot.name}</h4>
                                <div className="flex justify-between items-end">
                                    <p className="text-[10px] font-mono text-slate-500">{bot.symbol} | {bot.strategy_name}</p>
                                    {bot.pnl !== undefined && bot.pnl !== 0 && (
                                        <span className={`text-xs font-bold font-mono ${bot.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                            {bot.pnl > 0 ? '+' : ''}{bot.pnl.toFixed(2)}%
                                        </span>
                                    )}
                                </div>
                            </Card>
                        ))}
                    </div>

                    {/* Panel Principal con TABS */}
                    <div className="xl:col-span-3 space-y-6">
                        <GlobalSignalTicker />
                        {activeBot ? (
                            <Tabs defaultValue="info" className="w-full">
                                <TabsList className="bg-slate-900/50 border border-white/5">
                                    <TabsTrigger value="info">Configuración</TabsTrigger>
                                    <TabsTrigger value="monitor">Live Monitor</TabsTrigger>
                                    <TabsTrigger value="history">Historial de Señales</TabsTrigger>
                                </TabsList>

                                <div className="mt-6">
                                    <TabsContent value="info">
                                        <BotInfoModule bot={activeBot} />
                                    </TabsContent>

                                    <TabsContent value="monitor">
                                        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
                                            <Card className="p-6 bg-gradient-to-br from-blue-500/5 to-transparent border-blue-500/10">
                                                <p className="text-[10px] font-bold text-slate-500 uppercase mb-2">Profit Actual</p>
                                                <h3 className={`text-3xl font-black ${activeBot.pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                                                    {activeBot.pnl > 0 ? '+' : ''}{activeBot.pnl?.toFixed(2) || '0.00'}%
                                                </h3>
                                            </Card>
                                            <Card className="p-6 bg-slate-900/50 border-white/5">
                                                <p className="text-[10px] font-bold text-slate-500 uppercase mb-2">Precio Actual</p>
                                                <h3 className="text-2xl font-mono text-white">
                                                    ${activeBot.current_price?.toFixed(2) || '---'}
                                                </h3>
                                            </Card>
                                            <Card className="p-6 bg-slate-900/50 border-white/5">
                                                <p className="text-[10px] font-bold text-slate-500 uppercase mb-2">Bot ID</p>
                                                <h3 className="text-sm font-mono text-slate-400 truncate" title={activeBot.id}>
                                                    {activeBot.id}
                                                </h3>
                                            </Card>
                                        </div>
                                        <ExecutionMonitor bot={activeBot} />
                                    </TabsContent>

                                    <TabsContent value="history">
                                        <SignalHistoryModule botId={activeBot.id} />
                                    </TabsContent>
                                </div>
                            </Tabs>
                        ) : (
                            <div className="flex h-full items-center justify-center text-slate-600 bg-slate-900/20 rounded-xl border border-white/5">
                                <div className="text-center">
                                    <Activity className="w-12 h-12 mx-auto mb-4 text-slate-700 opacity-50" />
                                    <p>Selecciona un bot del panel izquierdo</p>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

export default BotsPage;
