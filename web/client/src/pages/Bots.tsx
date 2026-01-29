import React, { useState, useEffect, useMemo } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
    Play,
    Pause,
    Trash2,
    Cpu,
    Activity,
    TrendingUp,
    ShieldCheck,
    Zap
} from 'lucide-react';
import { toast } from 'sonner';

// Gráfico de PnL Tarea 4.4
const PnLChart = ({ data }: { data: number[] }) => {
    const min = Math.min(...data || [0], -1);
    const range = Math.max(...data || [0], 1) - min;
    return (
        <div className="h-16 w-full flex items-end gap-1 mt-2">
            {(data || [0, 0, 0]).map((val, i) => (
                <div key={i} className={`flex-1 rounded-t-sm ${val >= 0 ? 'bg-blue-500/40' : 'bg-red-500/40'}`} style={{ height: `${((val - min) / range) * 100}%` }} />
            ))}
        </div>
    );
};

// Monitor Híbrido Tarea 4.3
const ExecutionMonitor = ({ bot }: any) => {
    const candles = useMemo(() => {
        let p = 50000;
        return Array.from({ length: 40 }).map((_, i) => ({ time: i, open: p, close: (p += (Math.random() - 0.5) * 150) }));
    }, [bot?.id]);

    if (!bot) return (
        <Card className="overflow-hidden border-blue-500/20 bg-slate-900/60 p-6 flex justify-center items-center">
            <p className="text-muted-foreground text-xs">Selecciona un bot para monitorear</p>
        </Card>
    );

    return (
        <Card className="overflow-hidden border-blue-500/20 bg-slate-900/60 transition-all hover:border-blue-500/40">
            <div className="p-4 border-b border-white/5 flex items-center justify-between">
                <h4 className="text-xs font-bold uppercase tracking-widest flex items-center gap-2">
                    <ShieldCheck className="w-4 h-4 text-blue-500" /> Live Monitor sp4: {bot?.symbol}
                </h4>
                <Badge variant="outline" className="text-[8px] animate-pulse border-green-500/50 text-green-500">Socket Active</Badge>
            </div>
            <div className="p-6">
                <div className="relative h-40 w-full border-b border-white/5 flex items-end gap-1">
                    {candles.map((c, i) => (
                        <div key={i} className={`flex-1 ${c.close >= c.open ? 'bg-green-500/50' : 'bg-red-500/50'}`} style={{ height: `${(c.close / 50500) * 100}%` }} />
                    ))}
                </div>
            </div>
        </Card>
    );
};

export default function Bots() {
    const [bots, setBots] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedId, setSelectedId] = useState<string | null>(null);

    const fetchBots = async () => {
        try {
            const response = await fetch(`${window.location.origin}/api/bots`);
            const data = await response.json();
            // Enrich data with mock PnL for visualization if not present
            const enriched = data.map((b: any) => ({
                ...b,
                pnl: b.pnl || [0, 0, 0] // Placeholder
            }));
            setBots(enriched);
            if (enriched.length > 0 && !selectedId) setSelectedId(enriched[0].id);
        } catch (error) {
            console.error("Error cargando bots:", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchBots();
    }, []);

    const updateBot = async (botId: string, updates: any) => {
        try {
            const res = await fetch(`${window.location.origin}/api/bots/${botId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates)
            });
            if (res.ok) {
                toast.success("Bot actualizado");
                fetchBots();
            }
        } catch (e) {
            toast.error("Error al actualizar bot");
        }
    };

    const activeBot = bots.find(b => b.id === selectedId);

    return (
        <div className="p-6 space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Bot Instances sp4</h1>
                    <p className="text-muted-foreground">Control de modelos de IA y ejecución dual (Simulado/Real).</p>
                </div>
                <div className="flex gap-2">
                    <Badge variant="outline" className="bg-green-500/10 text-green-500 border-green-500/20 px-3 py-1">
                        <Zap className="w-3 h-3 mr-2" />
                        AutoTrade Active
                    </Badge>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
                {/* List of Bots */}
                <div className="space-y-4 lg:col-span-1">
                    {loading ? (
                        Array(3).fill(0).map((_, i) => <Card key={i} className="h-24 animate-pulse bg-muted/20" />)
                    ) : bots.map(b => (
                        <Card
                            key={b.id}
                            onClick={() => setSelectedId(b.id)}
                            className={`p-4 cursor-pointer border-l-4 transition-all hover:bg-muted/10 ${selectedId === b.id ? 'border-l-blue-500 bg-secondary/20 shadow-sm' : 'border-l-transparent opacity-70'}`}
                        >
                            <div className="flex justify-between items-start mb-2">
                                <h4 className="text-sm font-bold truncate pr-2">{b.name || b.symbol}</h4>
                                <Badge variant={b.mode === 'real' ? 'destructive' : 'secondary'} className="text-[8px] uppercase">{b.mode || 'SIM'}</Badge>
                            </div>
                            <p className="text-[10px] font-mono text-muted-foreground mb-3">{b.symbol} | {b.strategy_name}</p>

                            <div className="flex justify-between items-center mt-2">
                                <Switch
                                    checked={b.status === 'active'}
                                    onCheckedChange={(checked) => updateBot(b.id, { status: checked ? 'active' : 'paused' })}
                                    className="scale-75"
                                    onClick={(e) => e.stopPropagation()}
                                />
                                <span className={`text-[10px] font-bold ${b.status === 'active' ? 'text-green-500' : 'text-muted-foreground'}`}>{b.status}</span>
                            </div>

                        </Card>
                    ))}
                </div>

                {/* Dashboard & Monitor Area */}
                <div className="lg:col-span-3 space-y-6">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <Card className="p-6 bg-gradient-to-br from-blue-500/5 to-transparent">
                            <p className="text-xs font-bold text-muted-foreground uppercase mb-2">Last Strategy Return</p>
                            <h3 className="text-3xl font-black text-foreground flex items-center gap-2">
                                <TrendingUp className="w-6 h-6 text-green-500" /> +2.5%
                            </h3>
                        </Card>
                        <Card className="p-6">
                            <p className="text-xs font-bold text-muted-foreground uppercase mb-2">Active Config</p>
                            <div className="flex gap-2">
                                <Badge variant="outline">{activeBot?.timeframe || '1h'}</Badge>
                                <Badge variant="outline">{activeBot?.symbols || activeBot?.symbol || 'BTC/USDT'}</Badge>
                                <Badge variant={activeBot?.mode === 'real' ? 'destructive' : 'secondary'}>{activeBot?.mode?.toUpperCase() || 'SIMULATED'}</Badge>
                            </div>
                        </Card>
                    </div>

                    <ExecutionMonitor bot={activeBot} />

                </div>
            </div>
        </div>
    );
}
