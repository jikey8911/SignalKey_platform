import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { BrainCircuit, Database, Play, History, CheckCircle2, RotateCcw } from 'lucide-react';
import { toast } from 'sonner';

export default function Training() {
    const [exchange] = useState('binance');
    const [market, setMarket] = useState('spot');
    const [symbols, setSymbols] = useState(['BTC/USDT', 'ETH/USDT', 'SOL/USDT']);
    const [loading, setLoading] = useState(false);
    const [models, setModels] = useState(['StatisticalMeanRev', 'TrendMaster_Agnostic']);

    const handleTrain = async () => {
        setLoading(true);
        try {
            const url = `${window.location.origin}/api/ml/train-strategies`;
            const res = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ exchange, market, symbols, timeframe: '1h', days: 60 })
            });
            if (res.ok) toast.success("Entrenamiento masivo iniciado.");
        } catch (e) {
            toast.error("Training failed: " + e);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="p-6 space-y-6 animate-in fade-in duration-500">
            <div className="flex justify-between items-center">
                <h1 className="text-3xl font-bold tracking-tighter">Training Center sp4</h1>
                <Badge variant="outline" className="bg-blue-500/5 text-blue-500 border-blue-500/20">
                    IA Engine Agnostic
                </Badge>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <Card className="lg:col-span-2 border-white/5 bg-slate-900/40">
                    <CardHeader>
                        <CardTitle className="text-sm flex items-center gap-2 opacity-70">
                            <Database className="w-4 h-4 text-blue-500" /> Configuración Multiactivo
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-6">
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <label className="text-[10px] font-bold uppercase text-slate-500">Mercado</label>
                                <select value={market} onChange={(e) => setMarket(e.target.value)} className="w-full bg-slate-800 border-none rounded-xl px-3 py-2 text-xs text-white outline-none ring-1 ring-white/5">
                                    <option value="spot">Spot Market</option>
                                    <option value="swap">Futures (Swap)</option>
                                </select>
                            </div>
                            <div className="space-y-2">
                                <label className="text-[10px] font-bold uppercase text-slate-500">Símbolos Activos</label>
                                <div className="flex flex-wrap gap-2 p-2 rounded-xl bg-slate-950/50 border border-white/5">
                                    {symbols.map(s => <Badge key={s} variant="secondary" className="text-[9px]">{s}</Badge>)}
                                </div>
                            </div>
                        </div>
                        <Button className="w-full py-6 bg-blue-600 hover:bg-blue-700 text-white font-bold uppercase tracking-widest rounded-2xl" onClick={handleTrain} disabled={loading}>
                            {loading ? <RotateCcw className="w-4 h-4 animate-spin mr-2" /> : <Play className="w-4 h-4 mr-2" />}
                            Entrenar Modelos de Estrategia
                        </Button>
                    </CardContent>
                </Card>

                <Card className="border-white/5 bg-slate-900/40">
                    <CardHeader>
                        <CardTitle className="text-sm flex items-center gap-2 opacity-70">
                            <History className="w-4 h-4 text-blue-500" /> Inventario .pkl
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        {models.map(m => (
                            <div key={m} className="p-3 border border-white/5 rounded-xl bg-slate-950/50 flex justify-between items-center group hover:border-blue-500/30 transition-all">
                                <span className="text-xs font-mono font-bold text-slate-400 group-hover:text-blue-400">{m}.pkl</span>
                                <CheckCircle2 className="w-3 h-3 text-green-500" />
                            </div>
                        ))}
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
