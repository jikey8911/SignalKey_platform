import React, { useEffect, useRef, useMemo, useState } from 'react';
import {
    createChart,
    ColorType,
    IChartApi,
    Time,
    SeriesMarker,
    CandlestickData,
    CandlestickSeries,
    createSeriesMarkers
} from 'lightweight-charts';
import { CONFIG } from '@/config';

interface TradeMarker {
    time: number | string;
    side: 'BUY' | 'SELL';
    price: number;
    label?: string;
    id?: string;
}

interface ChartProps {
    data?: { time: string | number; open: number; high: number; low: number; close: number }[];
    trades?: TradeMarker[];
    colors?: {
        backgroundColor?: string;
        lineColor?: string;
        textColor?: string;
        areaTopColor?: string;
        areaBottomColor?: string;
    };
    height?: number;
    symbol?: string;
    timeframe?: string;
}

const toSeconds = (t: string | number): Time => {
    if (typeof t === 'string') return Math.floor(new Date(t).getTime() / 1000) as Time;
    if (typeof t === 'number') {
        if (t > 33000000000) return (Math.floor(t / 1000)) as Time;
        return Math.floor(t) as Time;
    }
    return t as Time;
};

export const TradingViewChart: React.FC<ChartProps> = ({ data, trades, colors, height = 400, symbol, timeframe }) => {
    const chartContainerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const seriesRef = useRef<any>(null);
    const markersPrimitiveRef = useRef<any>(null);

    // Internal state for self-fetched data
    const [fetchedData, setFetchedData] = useState<any[]>([]);

    // If data is provided via props, use it. Otherwise use fetchedData.
    const activeData = (data && data.length > 0) ? data : fetchedData;

    // EFECTO DE CARGA INTERNA (Sincronización solicitada)
    useEffect(() => {
        if (!symbol || !timeframe || (data && data.length > 0)) return;

        const loadData = async () => {
            try {
                const res = await fetch(`${CONFIG.API_BASE_URL}/market/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=1000`);
                if (res.ok) {
                    const json = await res.json();
                    setFetchedData(json);
                }
            } catch (e) {
                console.error("Failed to fetch chart data internally", e);
            }
        };
        loadData();
    }, [symbol, timeframe, data]);

    const formattedData = useMemo(() => {
        return [...activeData]
            .map(d => ({ ...d, time: toSeconds(d.time) }))
            .sort((a, b) => (a.time as number) - (b.time as number)) as CandlestickData<Time>[];
    }, [activeData]);

    const markers = useMemo(() => {
        if (!trades || trades.length === 0 || formattedData.length === 0) return [];

        const firstCandleTime = formattedData[0].time as number;
        const lastCandleTime = formattedData[formattedData.length - 1].time as number;

        const candleTimes = new Set(formattedData.map(d => d.time as number));
        const sortedCandleTimes = formattedData.map(d => d.time as number);

        return trades
            .map(t => {
                const tradeTime = toSeconds(t.time) as number;

                // CRITICAL FIX: Only show markers that are within our visible candle range
                // A marker at time 0 or too far in the past/future stretches the price scale to infinity
                if (tradeTime < firstCandleTime - 3600 * 24 || tradeTime > lastCandleTime + 3600) {
                    return null;
                }

                let validTime = tradeTime;
                if (!candleTimes.has(tradeTime)) {
                    const found = sortedCandleTimes.slice().reverse().find(ct => ct <= tradeTime);
                    if (found) validTime = found;
                }

                return {
                    time: validTime as Time,
                    position: t.side === 'BUY' ? 'belowBar' : 'aboveBar',
                    color: t.side === 'BUY' ? '#22c55e' : '#ef4444',
                    shape: t.side === 'BUY' ? 'arrowUp' : 'arrowDown',
                    text: t.label || t.side,
                    size: 2,
                    id: t.id,
                } as any;
            })
            .filter((m): m is SeriesMarker<Time> => m !== null)
            .sort((a, b) => (a.time as number) - (b.time as number));
    }, [trades, formattedData]);

    // EFECTO 1: Crear y Destruir el Gráfico (SOLO UNA VEZ o cambios de layout)
    useEffect(() => {
        if (!chartContainerRef.current) return;

        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: colors?.backgroundColor || '#0f172a' },
                textColor: colors?.textColor || '#94a3b8',
            },
            width: chartContainerRef.current.clientWidth,
            height: height,
            grid: {
                vertLines: { color: '#1e293b' },
                horzLines: { color: '#1e293b' },
            },
            timeScale: {
                timeVisible: true,
                secondsVisible: false,
                rightOffset: 12,
                barSpacing: 6,
            },
            leftPriceScale: {
                visible: false,
            },
            rightPriceScale: {
                visible: true,
                autoScale: true,
            }
        });

        const candlestickSeries = chart.addSeries(CandlestickSeries, {
            upColor: '#22c55e',
            downColor: '#ef4444',
            borderVisible: false,
            wickUpColor: '#22c55e',
            wickDownColor: '#ef4444',
            priceFormat: {
                type: 'price',
                precision: 8,
                minMove: 0.00000001,
            },
        });

        // Asignamos las referencias
        seriesRef.current = candlestickSeries;
        chartRef.current = chart;

        // Pintamos marcadores iniciales si existen
        const markersPrimitive = createSeriesMarkers(candlestickSeries, []);
        markersPrimitiveRef.current = markersPrimitive;

        const handleResize = () => {
            chart.applyOptions({ width: chartContainerRef.current?.clientWidth || 0 });
        };

        window.addEventListener('resize', handleResize);

        // CLEANUP CRÍTICO
        return () => {
            window.removeEventListener('resize', handleResize);
            chart.remove();
            chartRef.current = null;
            seriesRef.current = null;
            markersPrimitiveRef.current = null;
        };
    }, [colors, height]);

    const lastAppliedRef = useRef<{ len: number; lastTime: number } | null>(null);

    // EFECTO 1.5: Actualizar Datos (Sin recrear gráfico)
    useEffect(() => {
        if (!seriesRef.current || formattedData.length === 0) return;

        const last = formattedData[formattedData.length - 1];
        const lastTime = Number(last.time as any);
        const prev = lastAppliedRef.current;

        // First load or big jump: setData
        if (!prev || formattedData.length < prev.len || formattedData.length - prev.len > 5) {
            seriesRef.current.setData(formattedData);
            lastAppliedRef.current = { len: formattedData.length, lastTime };
            try { chartRef.current?.timeScale().fitContent(); } catch {}
            return;
        }

        // Incremental updates: update last candle (and possibly append)
        // lightweight-charts update() can handle both same-time updates and next-bar append
        try {
            seriesRef.current.update(last);
        } catch {
            // fallback
            seriesRef.current.setData(formattedData);
        }

        lastAppliedRef.current = { len: formattedData.length, lastTime };
    }, [formattedData]);

    // EFECTO 2: Actualizar Marcadores Dinámicamente
    useEffect(() => {
        if (markersPrimitiveRef.current && markers) {
            try {
                markersPrimitiveRef.current.setMarkers(markers);
            } catch (e) {
                console.warn("No se pudieron pintar los marcadores", e);
            }
        }
    }, [markers]);

    // EFECTO 3: Ajuste de Zoom (VisibleRange) y Auto-Fit al cambiar de Bot
    useEffect(() => {
        if (!chartRef.current || formattedData.length === 0) return;

        // Defer a tick so DOM sizing + setData settle before fitting
        const t = window.setTimeout(() => {
            try {
                chartRef.current?.timeScale().fitContent();
            } catch (e) {
                console.warn("Auto-centering failed", e);
            }
        }, 0);

        return () => window.clearTimeout(t);
    }, [symbol, timeframe, formattedData.length]);

    return <div ref={chartContainerRef} className="w-full shadow-xl rounded-lg overflow-hidden border border-slate-800" />;
};
