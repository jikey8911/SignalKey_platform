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

// --- MONITOR HÍBRIDO (Integrado con Socket Tarea 4.3 & 4.5) ---

const ExecutionMonitor = ({ bot }: any) => {
    const { lastMessage } = useSocketContext();
    const [signals, setSignals] = useState<any[]>([]);
    const [candles, setCandles] = useState<any[]>([]);
    const [loading, setLoading] = useState(false);

    // Fetch Initial Candles
    useEffect(() => {
        if (!bot?.symbol) return;

        const fetchCandles = async () => {
            setLoading(true);
            try {
                const res = await fetch(`http://localhost:8000/api/market/candles?symbol=${encodeURIComponent(bot.symbol)}&timeframe=${bot.timeframe || '1h'}&limit=50`);
                if (res.ok) {
                    const data = await res.json();
                    setCandles(data);
                }
            } catch (e) {
                console.error("Error fetching candles", e);
            } finally {
                setLoading(false);
            }
        };
        fetchCandles();
    }, [bot?.symbol, bot?.timeframe]);

    // Integración real: Añadir señal del socket a la lista visual
    useEffect(() => {
        if (lastMessage && lastMessage.event === 'signal_update') {
            const signalData = lastMessage.data;
            if (signalData?.bot_id === bot?.id || !bot) {
                setSignals(prev => [signalData, ...prev].slice(0, 5));
            }
        }
        // Also listen for bot updates to refresh candles or price potentially? 
        // For now, we rely on the main list update for price
    }, [lastMessage, bot?.id]);

    // Calcular min/max para escalar gráfico
    const { min, max } = useMemo(() => {
        if (!candles.length) return { min: 0, max: 100 };
        const prices = candles.map(c => c.close);
        return { min: Math.min(...prices), max: Math.max(...prices) };
    }, [candles]);

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
                    <Badge variant="success">WS Active</Badge>
                </div>
            </div>

            <div className="p-6">
                <div className="relative h-64 w-full border-b border-white/5 mb-6 flex items-end gap-1 bg-slate-950/50 rounded-lg p-2">
                    {loading && <div className="absolute inset-0 flex items-center justify-center text-slate-500">Loading Chart...</div>}

                    {!loading && candles.map((c, i) => {
                        const height = ((c.close - min) / (max - min)) * 100;
                        const validHeight = isNaN(height) ? 50 : Math.max(1, height); // Fallback
                        return (
                            <div
                                key={i}
                                className={`flex-1 rounded-sm ${c.close >= c.open ? 'bg-green-500/50 hover:bg-green-400' : 'bg-red-500/50 hover:bg-red-400'} transition-all`}
                                style={{ height: `${validHeight}%` }}
                                title={`Time: ${new Date(c.time * 1000).toLocaleTimeString()} O:${c.open} C:${c.close}`}
                            />
                        );
                    })}

                    {/* Visual Overlay for Last Signal */}
                    {signals.length > 0 && (
                        <div className="absolute top-2 right-2 animate-bounce cursor-pointer" title={JSON.stringify(signals[0])}>
                            <Badge variant={signals[0].type === 'LONG' || signals[0].side === 'buy' ? 'success' : 'destructive'}>
                                {signals[0].type || signals[0].side} @ {signals[0].price?.toFixed(2)}
                            </Badge>
                        </div>
                    )}
                </div>

                <div className="space-y-2">
                    <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Flujo de ejecución reciente (Socket.io)</p>
                    {signals.length === 0 ? (
                        <p className="text-xs text-slate-600 italic">Esperando señales del servidor...</p>
                    ) : (
                        signals.map((sig, idx) => (
                            <div key={idx} className="flex justify-between items-center text-xs p-2 bg-white/5 rounded-lg border border-white/5 animate-in slide-in-from-left-2">
                                <span className={(sig.type === 'LONG' || sig.side === 'buy') ? 'text-green-400' : 'text-red-400'}>
                                    ● {sig.type || sig.side}
                                </span>
                                <span className="text-white font-mono">${sig.price?.toFixed(2)}</span>
                                <span className="text-[10px] text-slate-500">{new Date().toLocaleTimeString()}</span>
                            </div>
                        ))
                    )}
                </div>
            </div>
        </Card>
    );
};

// --- PÁGINA DE BOTS ---

// --- PÁGINA DE BOTS ---

const BotsPage = () => {
    const { user } = useAuth(); // sp4: Get actual user context
    const [bots, setBots] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const { lastMessage } = useSocketContext();

    const fetchBots = async () => {
        if (!user?.openId) return;

        try {
            // sp4: Pass dynamic user_id
            const res = await fetch(`${CONFIG.API_BASE_URL}/bots/?user_id=${user.openId}`);
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
            const interval = setInterval(fetchBots, 5000); // Poll every 5s for PnL updates
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

                    {/* Panel Principal */}
                    <div className="xl:col-span-3 space-y-6">
                        {activeBot ? (
                            <>
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
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
                            </>
                        ) : (
                            <div className="flex h-full items-center justify-center text-slate-600">
                                Selecciona un bot para ver detalles
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

export default BotsPage;
