import React, { useState, useEffect, useRef } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { BrainCircuit, Database, Play, History, CheckCircle2, RotateCcw, Terminal, Plus, Trophy } from 'lucide-react';
import { toast } from 'sonner';
import { useSocketContext } from '@/contexts/SocketContext';
import { useAuth } from '@/_core/hooks/useAuth';
import { CONFIG } from '@/config';

export default function Training() {
    const { user } = useAuth(); // Get authenticated user

    // Configuration State
    const [exchanges, setExchanges] = useState<string[]>([]);
    const [selectedExchange, setSelectedExchange] = useState('okx'); // Default requested

    const [markets, setMarkets] = useState<string[]>(['spot']);
    const [selectedMarket, setSelectedMarket] = useState('spot'); // Default requested

    const [availableSymbols, setAvailableSymbols] = useState<string[]>([]);
    const [selectedSymbols, setSelectedSymbols] = useState<string[]>(['BTC/USDT', 'ETH/USDT']); // Defaults
    const [symbolPairFilter, setSymbolPairFilter] = useState<string>('USDT');
    const [randomCount, setRandomCount] = useState<number>(5);

    // Loading flags for each select
    const [loadingExchanges, setLoadingExchanges] = useState(false);
    const [loadingMarkets, setLoadingMarkets] = useState(false);
    const [loadingSymbols, setLoadingSymbols] = useState(false);

    const [loading, setLoading] = useState(false);
    const [models, setModels] = useState<string[]>([]);
    const [logs, setLogs] = useState<string[]>([]);

    // Socket integration
    const { lastMessage } = useSocketContext();
    const scrollRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (lastMessage) {
            try {
                const data = JSON.parse(lastMessage.data);
                if (data.event === 'training_log') {
                    const msg = data.data.message;
                    setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`]);
                }
            } catch (e) {
                // Ignore parse errors for non-json
            }
        }
    }, [lastMessage]);

    // Auto-scroll logs
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [logs]);

    // Fetch available strategies from backend
    useEffect(() => {
        const fetchStrategies = async () => {
            try {
                const res = await fetch(`${CONFIG.API_BASE_URL}/ml/strategies?market=${selectedMarket}`);
                if (res.ok) {
                    const data = await res.json();
                    setModels(data.strategies || []);
                } else {
                    console.error('Failed to fetch strategies');
                    // Fallback to default
                    setModels(['StatisticalMeanReversion', 'TrendEma', 'RsiReversion']);
                }
            } catch (e) {
                console.error('Error fetching strategies:', e);
                setModels(['StatisticalMeanReversion', 'TrendEma', 'RsiReversion']);
            }
        };
        fetchStrategies();
    }, [selectedMarket]);

    // 1. Fetch Exchanges on Mount
    useEffect(() => {
        const fetchExchanges = async () => {
            setLoadingExchanges(true);
            try {
                const res = await fetch(`${CONFIG.API_BASE_URL}/market/exchanges`);
                if (res.ok) {
                    const data = await res.json();
                    const list: string[] = (data || []).map((x: any) => String(x).toLowerCase());
                    setExchanges(list);

                    // Default: OKX if present, else first
                    if (list.length) {
                        if (list.includes('okx')) setSelectedExchange('okx');
                        else setSelectedExchange(list[0]);
                    }
                }
            } catch (error) {
                console.error("Failed to fetch exchanges:", error);
            } finally {
                setLoadingExchanges(false);
            }
        };
        fetchExchanges();
    }, []);

    // 2. Fetch Markets when Exchange changes
    useEffect(() => {
        const fetchMarkets = async () => {
            if (!selectedExchange) return;
            setLoadingMarkets(true);
            try {
                // reset dependent state
                setAvailableSymbols([]);

                const res = await fetch(`${CONFIG.API_BASE_URL}/market/exchanges/${selectedExchange}/markets`);
                if (res.ok) {
                    const data = await res.json();
                    const list: string[] = (data || []).map((x: any) => String(x).toLowerCase());
                    setMarkets(list);
                    // Reset to spot if available, else first one
                    if (list.includes('spot')) setSelectedMarket('spot');
                    else if (list.length > 0) setSelectedMarket(list[0]);
                } else {
                    setMarkets([]);
                }
            } catch (error) {
                console.error("Failed to fetch markets:", error);
                setMarkets([]);
            } finally {
                setLoadingMarkets(false);
            }
        };
        fetchMarkets();
    }, [selectedExchange]);

    // 3. Fetch Symbols when Exchange or Market changes
    useEffect(() => {
        const fetchSymbols = async () => {
            if (!selectedExchange || !selectedMarket) return;
            setLoadingSymbols(true);
            try {
                const res = await fetch(`${CONFIG.API_BASE_URL}/market/exchanges/${selectedExchange}/markets/${selectedMarket}/symbols`);
                if (res.ok) {
                    const data = await res.json();
                    const list: string[] = (data || []).map((x: any) => String(x));
                    setAvailableSymbols(list);
                } else {
                    setAvailableSymbols([]);
                }
            } catch (error) {
                console.error("Failed to fetch symbols:", error);
                setAvailableSymbols([]);
            } finally {
                setLoadingSymbols(false);
            }
        };
        fetchSymbols();
    }, [selectedExchange, selectedMarket]);

    const toggleSymbol = (sym: string) => {
        if (selectedSymbols.includes(sym)) {
            setSelectedSymbols(prev => prev.filter(s => s !== sym));
        } else {
            setSelectedSymbols(prev => [...prev, sym]);
        }
    };

    const handleRandomSymbols = () => {
        const pool = availableSymbols
            .filter(s => symbolPairFilter === 'ALL' ? true : s.endsWith(`/${symbolPairFilter}`));

        if (pool.length === 0) {
            toast.error('No hay símbolos disponibles para ese filtro');
            return;
        }

        const count = Math.max(1, Math.min(randomCount || 1, pool.length));
        const shuffled = [...pool].sort(() => Math.random() - 0.5);
        setSelectedSymbols(shuffled.slice(0, count));
        toast.success(`Seleccionados ${count} símbolos al azar`);
    };

    const handleTrain = async () => {
        if (!user?.openId) {
            toast.error("User ID not found. Please relogin.");
            return;
        }

        if (selectedSymbols.length === 0) {
            toast.error("Please select at least one symbol.");
            return;
        }

        setLoading(true);
        setLogs([]); // Clear previous logs
        toast.info("Iniciando secuencia de entrenamiento...");
        console.log("🚀 [Training] Triggered by user:", user.openId);

        try {
            const url = `${CONFIG.API_BASE_URL}/ml/train-strategies`;
            const payload = {
                exchange: selectedExchange,
                market: selectedMarket,
                symbols: selectedSymbols,
                timeframe: '1h',
                days: 60,
                user_id: user.openId // Pass real user ID to backend
            };
            console.log("🚀 [Training] Sending payload:", payload);

            const res = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                toast.success("Endpoint disparado. Escuchando logs...");
            } else {
                console.error("❌ [Training] Fetch failed:", res.status, res.statusText);
                toast.error(`Error ${res.status}: ${res.statusText}`);
            }
        } catch (e) {
            console.error("❌ [Training] Fetch exception:", e);
            toast.error("Training failed: " + e);
        } finally {
            // Keep loading state until logs finish or timeout
            setTimeout(() => setLoading(false), 5000);
        }
    };

    return (
        <div className="p-6 space-y-6 animate-in fade-in duration-500">
            <div className="flex justify-between items-center">
                <h1 className="text-3xl font-bold tracking-tighter">Training Center</h1>
                <Badge variant="outline" className="bg-blue-500/5 text-blue-500 border-blue-500/20">
                    IA Engine Agnostic
                </Badge>
            </div>

            {/* Main Training Section */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <Card className="lg:col-span-2 border-white/5 bg-slate-900/40">
                    <CardHeader>
                        <CardTitle className="text-sm flex items-center gap-2 opacity-70">
                            <Database className="w-4 h-4 text-blue-500" /> Configuración Multiactivo
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-6">
                        <div className="grid grid-cols-2 gap-4">
                            {/* Exchange Selector */}
                            <div className="space-y-2">
                                <label className="text-[10px] font-bold uppercase text-slate-500">Exchange</label>
                                <div className="relative">
                                    <select
                                        value={selectedExchange}
                                        onChange={(e) => setSelectedExchange(e.target.value)}
                                        disabled={loadingExchanges}
                                        className="w-full bg-slate-800 border-none rounded-xl px-3 py-2 text-xs text-white outline-none ring-1 ring-white/5 disabled:opacity-60"
                                    >
                                        {exchanges.map(ex => <option key={ex} value={ex}>{ex.toUpperCase()}</option>)}
                                        {exchanges.length === 0 && <option value="okx">OKX (Default)</option>}
                                    </select>
                                    {(loadingExchanges) && (
                                        <div className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-slate-400">Cargando…</div>
                                    )}
                                </div>
                            </div>

                            {/* Market Selector */}
                            <div className="space-y-2">
                                <label className="text-[10px] font-bold uppercase text-slate-500">Mercado</label>
                                <div className="relative">
                                    <select
                                        value={selectedMarket}
                                        onChange={(e) => setSelectedMarket(e.target.value)}
                                        disabled={loadingMarkets || !markets.length}
                                        className="w-full bg-slate-800 border-none rounded-xl px-3 py-2 text-xs text-white outline-none ring-1 ring-white/5 disabled:opacity-60"
                                    >
                                        {markets.map(m => <option key={m} value={m}>{m.toUpperCase()}</option>)}
                                    </select>
                                    {(loadingMarkets) && (
                                        <div className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-slate-400">Cargando…</div>
                                    )}
                                </div>
                            </div>
                        </div>

                        {/* Symbol Selection Area */}
                        <div className="space-y-2">
                            <div className="flex justify-between items-center">
                                <label className="text-[10px] font-bold uppercase text-slate-500">
                                    Símbolos Seleccionados ({selectedSymbols.length})
                                </label>
                                <span className="text-[10px] text-slate-600">
                                    {loadingSymbols ? 'Cargando símbolos…' : `Disponibles: ${availableSymbols.length}`}
                                </span>
                            </div>

                            {/* Selected Symbols Pool */}
                            <div className="flex flex-wrap gap-2 p-3 rounded-xl bg-slate-950/50 border border-white/5 min-h-[60px]">
                                {selectedSymbols.length === 0 && <span className="text-xs text-slate-600 italic">No symbols selected</span>}
                                {selectedSymbols.map(s => (
                                    <Badge
                                        key={s}
                                        variant="secondary"
                                        className="text-[9px] cursor-pointer hover:bg-red-900/20 hover:text-red-400 transition-colors"
                                        onClick={() => toggleSymbol(s)}
                                    >
                                        {s} ✕
                                    </Badge>
                                ))}
                            </div>

                            {/* Available Symbols List */}
                            <div className="pt-2 space-y-2">
                                <div className="flex flex-wrap items-center justify-between gap-3">
                                    <label className="text-[10px] font-bold uppercase text-slate-500 block">Agregar Símbolo</label>
                                    <div className="flex items-center gap-2">
                                        <select
                                            value={symbolPairFilter}
                                            onChange={(e) => setSymbolPairFilter(e.target.value)}
                                            className="bg-slate-800 border-none rounded px-2 py-1 text-[10px] text-white outline-none ring-1 ring-white/5"
                                        >
                                            <option value="ALL">Todos los pares</option>
                                            <option value="USDT">/USDT</option>
                                            <option value="USDC">/USDC</option>
                                            <option value="BTC">/BTC</option>
                                            <option value="ETH">/ETH</option>
                                        </select>
                                        <input
                                            type="number"
                                            min={1}
                                            value={randomCount}
                                            onChange={(e) => setRandomCount(parseInt(e.target.value) || 1)}
                                            className="w-16 bg-slate-800 border-none rounded px-2 py-1 text-[10px] text-white outline-none ring-1 ring-white/5"
                                            title="Cantidad random"
                                        />
                                        <button
                                            type="button"
                                            onClick={handleRandomSymbols}
                                            className="text-[10px] px-2 py-1 rounded bg-blue-600 hover:bg-blue-700 text-white transition-colors"
                                        >
                                            Random
                                        </button>
                                    </div>
                                </div>
                                <div className="h-48 overflow-y-auto pr-2 grid grid-cols-1 sm:grid-cols-3 gap-2">
                                    {availableSymbols
                                        .filter(s => !selectedSymbols.includes(s))
                                        .filter(s => symbolPairFilter === 'ALL' ? true : s.endsWith(`/${symbolPairFilter}`))
                                        .map(s => (
                                            <button
                                                key={s}
                                                onClick={() => toggleSymbol(s)}
                                                title={s}
                                                className="text-[10px] px-3 py-2 rounded bg-slate-800 hover:bg-blue-600 text-slate-300 hover:text-white transition-colors text-left"
                                            >
                                                + {s}
                                            </button>
                                        ))}
                                </div>
                            </div>
                        </div>

                        <Button className="w-full py-6 bg-blue-600 hover:bg-blue-700 text-white font-bold uppercase tracking-widest rounded-2xl" onClick={handleTrain} disabled={loading}>
                            {loading ? <RotateCcw className="w-4 h-4 animate-spin mr-2" /> : <Play className="w-4 h-4 mr-2" />}
                            Entrenar Modelos de Estrategia
                        </Button>

                        {/* Live Logs Console */}
                        <div className="mt-4">
                            <div className="text-[10px] font-bold uppercase text-slate-500 mb-2 flex items-center gap-2">
                                <Terminal className="w-3 h-3" /> Live Real-Time Logs
                            </div>
                            <div ref={scrollRef} className="h-64 overflow-y-auto bg-slate-950 rounded-xl p-3 border border-white/5 font-mono text-[10px] text-slate-300 space-y-1 shadow-inner">
                                {logs.length === 0 ? (
                                    <span className="text-slate-600 italic">Waiting for training sequence...</span>
                                ) : (
                                    logs.map((log, i) => (
                                        <div key={i} className="border-l-2 border-blue-500/50 pl-2">{log}</div>
                                    ))
                                )}
                            </div>
                        </div>

                    </CardContent>
                </Card>

                <div className="space-y-6">
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

                    <Card className="border-white/5 bg-gradient-to-br from-blue-600/10 to-transparent">
                        <CardHeader>
                            <CardTitle className="text-sm opacity-70">Info</CardTitle>
                        </CardHeader>
                        <CardContent className="text-xs text-slate-500 leading-relaxed">
                            Los modelos entrenados se guardan localmente para ser utilizados en el Backtest Tournament y en los Bots en vivo.
                            Se recomienda entrenar con al menos 60 días de datos para mayor robustez.
                        </CardContent>
                    </Card>
                </div>
            </div>
        </div>
    )
}
