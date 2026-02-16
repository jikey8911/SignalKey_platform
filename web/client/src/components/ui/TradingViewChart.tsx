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

    // Usamos directamente los datos pasados por props.
    const activeData = data || [];

    const formattedData = useMemo(() => {
        return [...activeData]
            .map(d => ({ ...d, time: toSeconds(d.time) }))
            .sort((a, b) => (a.time as number) - (b.time as number)) as CandlestickData<Time>[];
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

        return trades
            .map(t => {
                const tradeTime = toSeconds(t.time) as number;

                // Usar el tiempo exacto de la señal para el marcador
                // lightweight-charts puede posicionar marcadores en tiempos arbitrarios.
                // No es necesario buscar una vela coincidente.
                let validTime = tradeTime;

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

    const lastAppliedRef = useRef<{ len: number; lastTime: number } | null>(null);
    const lastSymbolTfRef = useRef<string>('');

    // EFECTO 1.5: Actualizar Datos (Sin recrear gráfico)
    useEffect(() => {
        if (!seriesRef.current || formattedData.length === 0) return;

        const key = `${symbol || ''}:${timeframe || ''}`;
        const symbolChanged = lastSymbolTfRef.current !== key;

        const last = formattedData[formattedData.length - 1];
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
            lastAppliedRef.current = { len: formattedData.length, lastTime };
            return;
        }

        // First load or big jump: setData
        if (!prev || formattedData.length < prev.len || formattedData.length - prev.len > 5) {
            seriesRef.current.setData(formattedData);
            lastAppliedRef.current = { len: formattedData.length, lastTime };
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

        lastAppliedRef.current = { len: formattedData.length, lastTime };
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

    return <div ref={chartContainerRef} className="w-full shadow-xl rounded-lg overflow-hidden border border-slate-800" />;
};
