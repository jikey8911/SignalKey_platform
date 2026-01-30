import React, { useState, useEffect, useMemo, useContext } from 'react';
import {
    Play, Pause, Trash2, Cpu, Activity, TrendingUp, ShieldCheck, Zap,
    LayoutDashboard, Signal, History, Settings as SettingsIcon, BrainCircuit,
    Database, Coins, Menu, X, ArrowUpRight, ArrowDownRight, Clock,
    CheckCircle2, RotateCcw, Search, Bell
} from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { useSocketContext } from '@/contexts/SocketContext'; // Real Context

// --- MONITOR HÍBRIDO (Integrado con Socket Tarea 4.3 & 4.5) ---

const ExecutionMonitor = ({ bot }: any) => {
    const { lastMessage } = useSocketContext();
    const [signals, setSignals] = useState<any[]>([]);

    // Integración real: Añadir señal del socket a la lista visual
    useEffect(() => {
        if (lastMessage && lastMessage.event === 'signal_update') {
            // Adapta esto según la estructura real de tu evento 'signal_update'
            const signalData = lastMessage.data;
            if (signalData?.bot_id === bot?.id || !bot) {
                setSignals(prev => [signalData, ...prev].slice(0, 5));
            }
        }
    }, [lastMessage, bot?.id]);

    // Mock visual candles for background
    const candles = useMemo(() => {
        let p = 50000;
        return Array.from({ length: 40 }).map((_, i) => ({ time: i, open: p, close: (p += (Math.random() - 0.5) * 150) }));
    }, [bot?.id]);

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
                <Badge variant="success">WS Active</Badge>
            </div>

            <div className="p-6">
                <div className="relative h-44 w-full border-b border-white/5 mb-6 flex items-end gap-1">
                    {candles.map((c, i) => (
                        <div key={i} className={`flex-1 ${c.close >= c.open ? 'bg-green-500/50' : 'bg-red-500/50'}`} style={{ height: `${(c.close / 50500) * 100}%` }} />
                    ))}
                    {/* Visual Overlay for Last Signal */}
                    {signals.length > 0 && (
                        <div className="absolute top-0 right-10 animate-bounce">
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

const BotsPage = () => {
    // Mock Bots State (Reemplazar con llamada real a API cuando se conecte el endpoint)
    const [bots] = useState([
        { id: '1', name: 'Agnostic Sniper sp4', symbol: 'BTC/USDT', strategy: 'StatisticalMeanRev', status: 'active', mode: 'simulated', pnl: [2, 5, 4, 12, 18] },
        { id: '2', name: 'Alpha Trend ETH', symbol: 'ETH/USDT', strategy: 'TrendEMA', status: 'paused', mode: 'real', pnl: [0, -1, 1, -2, 2] },
    ]);
    const [selectedId, setSelectedId] = useState('1');
    const activeBot = bots.find(b => b.id === selectedId);

    return (
        <div className="p-8 space-y-8">
            <div className="flex justify-between items-center">
                <h1 className="text-4xl font-black text-white tracking-tighter uppercase italic">Control de Bots <span className="text-blue-500">sp4</span></h1>
                <Badge variant="success" className="py-2 px-4 shadow-lg shadow-green-500/10">
                    <Zap className="w-3 h-3 mr-2 fill-current" /> AutoTrade Sync
                </Badge>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-4 gap-8">
                {/* Lista de Bots */}
                <div className="xl:col-span-1 space-y-4">
                    {bots.map((bot) => (
                        <Card key={bot.id} className={`p-5 cursor-pointer border-l-4 ${selectedId === bot.id ? 'border-l-blue-500 bg-blue-500/5' : 'border-l-transparent opacity-60'}`} onClick={() => setSelectedId(bot.id)}>
                            <div className="flex justify-between items-start mb-3">
                                <Badge variant={bot.mode === 'real' ? 'destructive' : 'secondary'}>{bot.mode}</Badge>
                                <div className={`h-2 w-2 rounded-full ${bot.status === 'active' ? 'bg-green-500 animate-pulse' : 'bg-slate-600'}`} />
                            </div>
                            <h4 className="text-lg font-bold text-white leading-tight">{bot.name}</h4>
                            <p className="text-[10px] font-mono text-slate-500">{bot.symbol} | {bot.strategy}</p>
                        </Card>
                    ))}
                </div>

                {/* Panel Principal */}
                <div className="xl:col-span-3 space-y-6">
                    <Card className="p-6 bg-gradient-to-br from-blue-500/5 to-transparent border-blue-500/10">
                        <p className="text-[10px] font-bold text-slate-500 uppercase mb-2">Profit Acumulado sp4.5</p>
                        <h3 className="text-3xl font-black text-white">+{(activeBot?.pnl.slice(-1)[0] || 0)}%</h3>
                    </Card>
                    <ExecutionMonitor bot={activeBot} />
                </div>
            </div>
        </div>
    );
};

export default BotsPage;
