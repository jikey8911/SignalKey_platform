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
    levels?: { price: number; label: string; color?: string }[];
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

export const TradingViewChart: React.FC<ChartProps> = ({ data, trades, levels, colors, height = 400, symbol, timeframe }) => {
    const chartContainerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const seriesRef = useRef<any>(null);
    const markersPrimitiveRef = useRef<any>(null);
    const priceLinesRef = useRef<any[]>([]);

    // Usamos directamente los datos pasados por props.
    const activeData = data || [];

    const formattedData = useMemo(() => {
        const sorted = [...activeData]
            .map(d => ({ ...d, time: toSeconds(d.time) }))
            .sort((a, b) => (a.time as number) - (b.time as number)) as CandlestickData<Time>[];

        // lightweight-charts exige `time` estrictamente ascendente (sin duplicados)
        // Si llegan duplicadas (mismo bucket), nos quedamos con la última.
        const dedup: CandlestickData<Time>[] = [];
        for (const c of sorted) {
            const t = Number(c.time as any);
            const last = dedup.length ? Number(dedup[dedup.length - 1].time as any) : null;
            if (last !== null && t === last) {
                dedup[dedup.length - 1] = c;
            } else {
                dedup.push(c);
            }
        }
        return dedup;
    }, [activeData]);

    const priceFormatCfg = useMemo(() => {
        const last = formattedData[formattedData.length - 1] as any;
        const px = Number(last?.close ?? 0);
        if (!Number.isFinite(px) || px <= 0) {
            return { type: 'price' as const, precision: 6, minMove: 0.000001 };
        }
        if (px >= 1000) return { type: 'price' as const, precision: 2, minMove: 0.01 };
        if (px >= 1) return { type: 'price' as const, precision: 4, minMove: 0.0001 };
        if (px >= 0.01) return { type: 'price' as const, precision: 6, minMove: 0.000001 };
        return { type: 'price' as const, precision: 8, minMove: 0.00000001 };
    }, [formattedData]);

    const markers = useMemo(() => {
        if (!trades || trades.length === 0 || formattedData.length === 0) return [];

        const candleTimes = formattedData.map(c => Number(c.time as any));

        const findCandleBucket = (tradeTime: number) => {
            // Queremos ubicar la operación en la vela correspondiente (<= tradeTime)
            // y si no existe, usar la más cercana disponible.
            let lo = 0;
            let hi = candleTimes.length - 1;
            let best = 0;

            while (lo <= hi) {
                const mid = (lo + hi) >> 1;
                const t = candleTimes[mid];
                if (t <= tradeTime) {
                    best = mid;
                    lo = mid + 1;
                } else {
                    hi = mid - 1;
                }
            }

            if (tradeTime < candleTimes[0]) return candleTimes[0];
            return candleTimes[Math.max(0, Math.min(best, candleTimes.length - 1))];
        };

        return trades
            .map(t => {
                const tradeTime = toSeconds(t.time) as number;
                const validTime = findCandleBucket(tradeTime);

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
            priceFormat: priceFormatCfg,
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

    // Ajustar formato de precio según rango/símbolo activo sin recrear el chart.
    useEffect(() => {
        if (!seriesRef.current) return;
        try {
            seriesRef.current.applyOptions({ priceFormat: priceFormatCfg });
        } catch {}
    }, [priceFormatCfg, symbol, timeframe]);

    const lastAppliedRef = useRef<{ len: number; firstTime: number; lastTime: number } | null>(null);
    const lastSymbolTfRef = useRef<string>('');

    // EFECTO 1.5: Actualizar Datos (Sin recrear gráfico)
    useEffect(() => {
        if (!seriesRef.current || formattedData.length === 0) return;

        const key = `${symbol || ''}:${timeframe || ''}`;
        const symbolChanged = lastSymbolTfRef.current !== key;

        const first = formattedData[0];
        const last = formattedData[formattedData.length - 1];
        const firstTime = Number(first.time as any);
        const lastTime = Number(last.time as any);
        const prev = lastAppliedRef.current;

        // Cambio de símbolo/timeframe: reset total del dataset y escala
        if (symbolChanged) {
            lastSymbolTfRef.current = key;
            lastAppliedRef.current = null;
            seriesRef.current.setData(formattedData);
            try {
                chartRef.current?.priceScale('right')?.applyOptions({ autoScale: true });
                chartRef.current?.timeScale().fitContent();
            } catch {}
            lastAppliedRef.current = { len: formattedData.length, firstTime, lastTime };
            return;
        }

        // First load / dataset cambiado (aunque sea mismo symbol/timeframe) / big jump: setData
        const datasetChanged = !!prev && (prev.firstTime !== firstTime || prev.lastTime !== lastTime);
        if (!prev || datasetChanged || formattedData.length < prev.len || formattedData.length - prev.len > 5) {
            seriesRef.current.setData(formattedData);
            lastAppliedRef.current = { len: formattedData.length, firstTime, lastTime };
            try {
                chartRef.current?.priceScale('right')?.applyOptions({ autoScale: true });
                chartRef.current?.timeScale().fitContent();
            } catch {}
            return;
        }

        // Incremental updates: update last candle (and possibly append)
        try {
            seriesRef.current.update(last);
        } catch {
            seriesRef.current.setData(formattedData);
        }

        lastAppliedRef.current = { len: formattedData.length, firstTime, lastTime };
    }, [formattedData, symbol, timeframe]);

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

    // EFECTO 2.5: Líneas de niveles (Entry/TP/SL)
    useEffect(() => {
        if (!seriesRef.current) return;

        try {
            // limpiar líneas anteriores
            for (const pl of priceLinesRef.current) {
                try { seriesRef.current.removePriceLine(pl); } catch {}
            }
            priceLinesRef.current = [];

            const valid = (levels || []).filter(l => Number.isFinite(Number(l.price)) && Number(l.price) > 0);
            for (const lvl of valid) {
                const line = seriesRef.current.createPriceLine({
                    price: Number(lvl.price),
                    color: lvl.color || '#94a3b8',
                    lineWidth: 1,
                    lineStyle: 2,
                    axisLabelVisible: true,
                    title: lvl.label,
                });
                priceLinesRef.current.push(line);
            }
        } catch (e) {
            console.warn('No se pudieron pintar líneas de niveles', e);
        }
    }, [levels, symbol, timeframe]);

    // EFECTO 3: Ajuste de Zoom (VisibleRange) y Auto-Fit al cambiar de Bot
    useEffect(() => {
        if (!chartRef.current || formattedData.length === 0) return;

        // Asegurar que fitContent se llama después de que los datos se hayan aplicado.
        // Esto se maneja en el EFECTO 1.5 cuando se llama a setData.
        // Aquí solo necesitamos asegurarnos de que el gráfico se ajuste al cambiar de bot.
        try {
            chartRef.current?.timeScale().fitContent();
        } catch (e) {
            console.warn("Auto-centering failed", e);
        }
    }, [symbol, timeframe, formattedData.length]);

    return (
        <div className="w-full">
            <div className="mb-2 text-[11px] text-slate-400 font-mono">Timezone: GMT (UTC)</div>
            <div ref={chartContainerRef} className="w-full shadow-xl rounded-lg overflow-hidden border border-slate-800" />
        </div>
    );
};
