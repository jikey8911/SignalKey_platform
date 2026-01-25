import React, { useState, useEffect, useMemo } from 'react';
import { CONFIG } from '../config';
import { Card } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { useQuery } from '@tanstack/react-query';
import { Play, RotateCw, Brain, BarChart3, Clock, CheckCircle, AlertTriangle, Loader2, Search } from 'lucide-react';
import { toast } from 'sonner';
import { trpc } from '@/lib/trpc';
import { useAuth } from '@/_core/hooks/useAuth';

export const Training = () => {
    const { user } = useAuth();
    const [selectedSymbol, setSelectedSymbol] = useState('');
    const [epochs, setEpochs] = useState(20);
    const [days, setDays] = useState(365);
    const [isTraining, setIsTraining] = useState(false);

    // Batch Selection State
    const [batchExchange, setBatchExchange] = useState('');
    const [batchMarket, setBatchMarket] = useState('spot');
    const [selectedBatchSymbols, setSelectedBatchSymbols] = useState<string[]>([]);
    const [symbolSearch, setSymbolSearch] = useState('');

    // Fetch Models
    const { data: models, isLoading, refetch } = useQuery({
        queryKey: ['ml-models'],
        queryFn: async () => {
            const res = await fetch(`${CONFIG.API_BASE_URL}/ml/models`);
            if (!res.ok) throw new Error('Failed to fetch models');
            return res.json();
        },
        refetchInterval: 5000
    });

    // --- Dynamic Data for Batch Selector ---
    const [exchanges, setExchanges] = useState<any[]>([]);

    useEffect(() => {
        fetch(`${CONFIG.API_BASE_URL}/market/exchanges`)
            .then(res => res.json())
            .then(data => {
                if (Array.isArray(data)) {
                    // Map string[] to object structure expected by UI
                    setExchanges(data.map(e => ({ exchangeId: e })));
                }
            })
            .catch(err => console.error("Error fetching exchanges:", err));
    }, []);

    // State for Batch Training
    const [markets, setMarkets] = useState<string[]>([]);
    const [loadingSymbols, setLoadingSymbols] = useState(false);

    // Store raw fetched symbols
    const [allSymbols, setAllSymbols] = useState<any[]>([]);

    // Fetch Markets
    useEffect(() => {
        if (!batchExchange) {
            setMarkets([]);
            return;
        }
        setMarkets([]);
        fetch(`${CONFIG.API_BASE_URL}/market/exchanges/${batchExchange}/markets`)
            .then(res => res.json())
            .then(data => {
                if (Array.isArray(data)) setMarkets(data);
            })
            .catch(err => console.error("Error fetching markets:", err));
    }, [batchExchange]);

    // Fetch Symbols
    useEffect(() => {
        if (!batchExchange || !batchMarket) return;
        setLoadingSymbols(true);
        fetch(`${CONFIG.API_BASE_URL}/market/exchanges/${batchExchange}/markets/${batchMarket}/symbols`)
            .then(res => res.json())
            .then(data => {
                if (Array.isArray(data)) {
                    // Map string[] to { symbol, price } for UI compatibility
                    const mapped = data.map(s => ({ symbol: s, price: 0 }));
                    setAllSymbols(mapped);
                }
            })
            .catch(err => console.error("Error fetching symbols:", err))
            .finally(() => setLoadingSymbols(false));
    }, [batchExchange, batchMarket]);

    // Client-side filtering
    const filteredSymbols = useMemo(() => {
        if (!allSymbols) return [];
        return allSymbols.filter((s: any) => s.symbol.toLowerCase().includes(symbolSearch.toLowerCase()));
    }, [allSymbols, symbolSearch]);

    // Auto-select defaults
    useEffect(() => {
        if (exchanges.length > 0 && !batchExchange) setBatchExchange(exchanges[0].exchangeId);
    }, [exchanges]);

    // Reset market when exchange changes to avoid invalid queries
    useEffect(() => {
        setBatchMarket('');
        setSelectedBatchSymbols([]);
    }, [batchExchange]);

    useEffect(() => {
        if (markets.length > 0 && (!batchMarket || !markets.includes(batchMarket))) {
            setBatchMarket(markets[0]);
        }
    }, [markets, batchMarket]);

    const handleTrainSingle = async () => {
        if (!selectedSymbol) return;
        setIsTraining(true);
        const toastId = toast.loading(`Iniciando entrenamiento para ${selectedSymbol}...`);
        try {
            const res = await fetch(`${CONFIG.API_BASE_URL}/ml/train`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    symbol: selectedSymbol,
                    days,
                    epochs,
                    user_id: user?.openId
                })
            });
            if (res.ok) {
                toast.success("Entrenamiento iniciado en segundo plano", { id: toastId });
                refetch();
            } else {
                throw new Error("Error iniciando");
            }
        } catch (e: any) {
            toast.error(e.message, { id: toastId });
        } finally {
            setIsTraining(false);
        }
    };

    const handleTrainGlobal = async () => {
        if (selectedBatchSymbols.length === 0) {
            toast.error("Selecciona al menos un símbolo para el entrenamiento global");
            return;
        }
        setIsTraining(true);
        const toastId = toast.loading(`Iniciando entrenamiento GLOBAL para ${selectedBatchSymbols.length} símbolos...`);
        try {
            // New "Global Model" logic requested by user
            const res = await fetch(`${CONFIG.API_BASE_URL}/ml/train_global`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    symbols: selectedBatchSymbols,
                    timeframe: '1h',
                    days: 365,
                    epochs: 20,
                    user_id: user?.openId,
                    exchange_id: batchExchange
                })
            });
            if (res.ok) {
                toast.success("Entrenamiento de Modelo Global iniciado!", { id: toastId });
                setSelectedBatchSymbols([]); // Clear after success
            } else {
                throw new Error("Error iniciando entrenamiento global");
            }
        } catch (e: any) {
            toast.error(e.message, { id: toastId });
        } finally {
            setIsTraining(false);
        }
    };

    const handleTrainBatch = async () => {
        if (selectedBatchSymbols.length === 0) {
            toast.error("Selecciona al menos un símbolo");
            return;
        }

        setIsTraining(true);
        const toastId = toast.loading(`Encolando batch (${selectedBatchSymbols.length} pares) en ${batchExchange}...`);
        try {
            const res = await fetch(`${CONFIG.API_BASE_URL}/ml/train_batch`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    symbols: selectedBatchSymbols,
                    days,
                    epochs,
                    user_id: user?.openId,
                    exchange_id: batchExchange
                })
            });
            if (res.ok) {
                toast.success("Batch iniciado. Revisa los logs.", { id: toastId });
                setSelectedBatchSymbols([]); // Clear after success
            } else {
                throw new Error("Error iniciando batch");
            }
        } catch (e: any) {
            toast.error(e.message, { id: toastId });
        } finally {
            setIsTraining(false);
        }
    };

    const toggleSymbol = (sym: string) => {
        if (selectedBatchSymbols.includes(sym)) {
            setSelectedBatchSymbols(prev => prev.filter(s => s !== sym));
        } else {
            setSelectedBatchSymbols(prev => [...prev, sym]);
        }
    };



    return (
        <div className="container mx-auto p-4 md:p-8 space-y-8 animate-in fade-in duration-500">
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight text-foreground flex items-center gap-2">
                        <Brain className="text-primary" />
                        Centro de Entrenamiento IA
                    </h1>
                    <p className="text-muted-foreground mt-2">
                        Gestiona y entrena tus modelos neuronales locales (PyTorch LSTM).
                    </p>
                </div>
                <Button variant="outline" onClick={() => refetch()} className="gap-2">
                    <RotateCw className={isLoading ? "animate-spin" : ""} size={16} />
                    Refrescar
                </Button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Panel Izquierdo: Acciones */}
                <div className="space-y-6 lg:col-span-1">
                    {/* Single Training */}
                    <Card className="p-6 border-l-4 border-l-blue-500 shadow-sm hover:shadow-md transition-shadow">
                        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                            <Play className="text-blue-500" size={20} /> Entrenar Modelo Individual
                        </h3>

                        <div className="space-y-4">
                            <div>
                                <label className="text-xs font-semibold uppercase text-muted-foreground mb-1 block">Símbolo</label>
                                <input
                                    value={selectedSymbol}
                                    onChange={e => setSelectedSymbol(e.target.value.toUpperCase())}
                                    className="w-full bg-background border border-input rounded px-3 py-2 text-sm"
                                    placeholder="BTC/USDT"
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="text-xs font-semibold uppercase text-muted-foreground mb-1 block">Días Hist.</label>
                                    <input type="number" value={days} onChange={e => setDays(Number(e.target.value))} className="w-full bg-background border border-input rounded px-3 py-2 text-sm" />
                                </div>
                                <div>
                                    <label className="text-xs font-semibold uppercase text-muted-foreground mb-1 block">Épocas</label>
                                    <input type="number" value={epochs} onChange={e => setEpochs(Number(e.target.value))} className="w-full bg-background border border-input rounded px-3 py-2 text-sm" />
                                </div>
                            </div>

                            <Button onClick={handleTrainSingle} disabled={isTraining} className="w-full">
                                {isTraining ? 'Iniciando...' : 'Iniciar Entrenamiento'}
                            </Button>
                        </div>
                    </Card>

                    {/* Batch Training */}
                    <Card className="p-6 border-l-4 border-l-purple-500 shadow-sm hover:shadow-md transition-shadow flex flex-col max-h-[600px]">
                        <h3 className="text-lg font-semibold mb-2 flex items-center gap-2">
                            <BarChart3 className="text-purple-500" size={20} /> Entrenador Masivo
                        </h3>
                        <p className="text-xs text-muted-foreground mb-4">
                            Selecciona múltiples pares de tu exchange.
                        </p>

                        <div className="space-y-3 flex-1 flex flex-col overflow-hidden">
                            {/* Exchange/Market Selectors */}
                            <div className="grid grid-cols-2 gap-2">
                                <div>
                                    <label className="text-[10px] font-semibold uppercase text-muted-foreground mb-1 block">Exchange</label>
                                    <select
                                        value={batchExchange}
                                        onChange={e => setBatchExchange(e.target.value)}
                                        className="w-full bg-background border border-input rounded px-2 py-1 text-xs h-8"
                                    >
                                        <option value="">Select...</option>
                                        {exchanges.map((e: any) => (
                                            <option key={e.exchangeId} value={e.exchangeId}>{e.exchangeId}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label className="text-[10px] font-semibold uppercase text-muted-foreground mb-1 block">Mercado</label>
                                    <select
                                        value={batchMarket}
                                        onChange={e => setBatchMarket(e.target.value)}
                                        className="w-full bg-background border border-input rounded px-2 py-1 text-xs h-8"
                                    >
                                        {markets.map((m: any) => (
                                            <option key={m} value={m}>{m.toUpperCase()}</option>
                                        ))}
                                    </select>
                                </div>
                            </div>

                            {/* Symbol Search */}
                            <div className="relative">
                                <Search className="absolute left-2 top-2 text-muted-foreground" size={14} />
                                <input
                                    value={symbolSearch}
                                    onChange={e => setSymbolSearch(e.target.value)}
                                    placeholder="Filtrar símbolos..."
                                    className="w-full bg-background border border-input rounded pl-8 pr-2 py-1.5 text-xs"
                                />
                            </div>

                            {/* Symbol List */}
                            <div className="flex-1 overflow-y-auto border border-border rounded bg-muted/20 p-2 space-y-1 min-h-[150px]">
                                {loadingSymbols ? (
                                    <div className="flex items-center justify-center h-20">
                                        <Loader2 className="animate-spin text-muted-foreground" size={20} />
                                    </div>
                                ) : (
                                    filteredSymbols.map((sym: any) => (
                                        <div
                                            key={sym.symbol}
                                            onClick={() => toggleSymbol(sym.symbol)}
                                            className={`flex items-center gap-2 p-1.5 rounded cursor-pointer transition-colors text-xs ${selectedBatchSymbols.includes(sym.symbol)
                                                ? 'bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300'
                                                : 'hover:bg-muted'
                                                }`}
                                        >
                                            <div className={`w-3 h-3 rounded-full border ${selectedBatchSymbols.includes(sym.symbol) ? 'bg-purple-500 border-purple-500' : 'border-muted-foreground'
                                                }`} />
                                            <span className="font-medium">{sym.symbol}</span>
                                            <span className="ml-auto text-muted-foreground">${Number(sym.price).toFixed(2)}</span>
                                        </div>
                                    ))
                                )}
                            </div>

                            <div className="pt-2 border-t border-border">
                                <div className="flex justify-between items-center mb-2">
                                    <span className="text-xs font-medium">{selectedBatchSymbols.length} seleccionados</span>
                                    <button onClick={() => setSelectedBatchSymbols([])} className="text-[10px] text-muted-foreground hover:text-foreground">Limpiar</button>
                                </div>
                                <Button onClick={handleTrainBatch} disabled={isTraining || selectedBatchSymbols.length === 0} variant="outline" className="w-full border-purple-500 text-purple-600 hover:bg-purple-50">
                                    {isTraining ? 'Encolando...' : 'Entrenar Batch (Múltiples)'}
                                </Button>
                                <Button onClick={handleTrainGlobal} disabled={isTraining || selectedBatchSymbols.length === 0} variant="default" className="w-full bg-purple-600 hover:bg-purple-700 mt-2">
                                    {isTraining ? 'Entrenando...' : 'Entrenar Modelo ÚNICO (Global)'}
                                </Button>
                            </div>
                        </div>
                    </Card>
                </div>

                {/* Panel Derecho: Modelos */}
                <div className="lg:col-span-2">
                    <Card className="h-full flex flex-col border-t-4 border-t-primary shadow-sm">
                        <div className="p-6 border-b border-border">
                            <h3 className="text-lg font-semibold flex items-center gap-2">
                                <CheckCircle className="text-green-500" size={20} /> Modelos Entrenados
                                <span className="ml-auto text-xs font-normal text-muted-foreground bg-secondary px-2 py-1 rounded-full">
                                    Total: {models?.length || 0}
                                </span>
                            </h3>
                        </div>

                        <div className="flex-1 overflow-auto p-0">
                            {!models || models.length === 0 ? (
                                <div className="flex flex-col items-center justify-center h-64 text-muted-foreground">
                                    <AlertTriangle className="mb-2 opacity-50" size={32} />
                                    <p>No hay modelos entrenados aún.</p>
                                    <p className="text-sm">Inicia un entrenamiento para comenzar.</p>
                                </div>
                            ) : (
                                <table className="w-full text-sm text-left">
                                    <thead className="bg-muted/50 text-muted-foreground font-medium border-b border-border sticky top-0">
                                        <tr>
                                            <th className="px-6 py-3">Símbolo</th>
                                            <th className="px-6 py-3">Tipo</th>
                                            <th className="px-6 py-3">Accuracy (Test)</th>
                                            <th className="px-6 py-3">Loss (Final)</th>
                                            <th className="px-6 py-3">Última Act.</th>
                                            <th className="px-6 py-3">Status</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {models.map((m: any, idx: number) => (
                                            <tr key={idx} className="border-b border-border hover:bg-muted/30 transition-colors">
                                                <td className="px-6 py-4 font-bold md:sticky md:left-0 bg-background">{m.symbol}</td>
                                                <td className="px-6 py-4 text-xs font-mono text-purple-600 dark:text-purple-400">
                                                    {m.model_type || 'LSTM'}
                                                </td>
                                                <td className="px-6 py-4">
                                                    <div className="flex items-center gap-2">
                                                        <div className="w-16 h-2 bg-secondary rounded-full overflow-hidden">
                                                            <div
                                                                className={`h-full rounded-full ${m.accuracy > 0.6 ? 'bg-green-500' : m.accuracy > 0.5 ? 'bg-yellow-500' : 'bg-red-500'}`}
                                                                style={{ width: `${(m.accuracy || 0) * 100}%` }}
                                                            />
                                                        </div>
                                                        {((m.accuracy || 0) * 100).toFixed(1)}%
                                                    </div>
                                                </td>
                                                <td className="px-6 py-4 font-mono text-xs">{m.final_loss?.toFixed(4) || 'N/A'}</td>
                                                <td className="px-6 py-4 text-xs text-muted-foreground">
                                                    <div className="flex items-center gap-1">
                                                        <Clock size={12} />
                                                        {m.last_trained ? new Date(m.last_trained).toLocaleString() : 'N/A'}
                                                    </div>
                                                </td>
                                                <td className="px-6 py-4">
                                                    <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400">
                                                        Ready
                                                    </span>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            )}
                        </div>
                    </Card>
                </div>
            </div>
        </div>
    );
};

export default Training;
