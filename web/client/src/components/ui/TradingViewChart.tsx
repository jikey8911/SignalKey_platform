import React, { useEffect, useRef, useMemo } from 'react';
import {
    createChart,
    ColorType,
    IChartApi,
    ISeriesApi,
    Time,
    SeriesMarker,
    CandlestickSeries, // <--- Importante para v5
    CandlestickData
} from 'lightweight-charts';

interface TradeMarker {
    time: number | string;
    side: 'BUY' | 'SELL';
    price: number;
    label?: string;
}

interface ChartProps {
    data: { time: string | number; open: number; high: number; low: number; close: number }[];
    trades?: TradeMarker[];
    colors?: {
        backgroundColor?: string;
        lineColor?: string;
        textColor?: string;
        areaTopColor?: string;
        areaBottomColor?: string;
    };
    height?: number;
}

const toSeconds = (t: string | number): Time => {
    if (typeof t === 'string') return (new Date(t).getTime() / 1000) as Time;
    if (typeof t === 'number') {
        if (t > 33000000000) return (Math.floor(t / 1000)) as Time;
        return Math.floor(t) as Time;
    }
    return t as Time;
};

export const TradingViewChart: React.FC<ChartProps> = ({ data, trades, colors, height = 400 }) => {
    const chartContainerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);

    // CAMBIO V5: El tipo genérico ahora es la clase de la serie, no un string
    const seriesRef = useRef<ISeriesApi<CandlestickSeries> | null>(null);

    const formattedData = useMemo(() => {
        return [...data]
            .map(d => ({ ...d, time: toSeconds(d.time) }))
            .sort((a, b) => (a.time as number) - (b.time as number)) as CandlestickData<Time>[];
    }, [data]);

    const markers = useMemo(() => {
        if (!trades || trades.length === 0 || formattedData.length === 0) return [];

        const candleTimes = new Set(formattedData.map(d => d.time as number));
        const sortedCandleTimes = formattedData.map(d => d.time as number);

        return trades.map(t => {
            const tradeTime = toSeconds(t.time) as number;
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
                size: 2
            } as SeriesMarker<Time>;
        }).sort((a, b) => (a.time as number) - (b.time as number));

    }, [trades, formattedData]);

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
            }
        });

        // CAMBIO V5: Usar chart.addSeries(CandlestickSeries, opciones)
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

        candlestickSeries.setData(formattedData);

        if (markers.length > 0) {
            candlestickSeries.setMarkers(markers);
        }

        seriesRef.current = candlestickSeries;
        chartRef.current = chart;

        const handleResize = () => {
            chart.applyOptions({ width: chartContainerRef.current?.clientWidth || 0 });
        };

        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            chart.remove();
        };
    }, [formattedData, colors, height]); // Agregué deps faltantes

    useEffect(() => {
        if (seriesRef.current && markers.length > 0) {
            seriesRef.current.setMarkers(markers);
        }
    }, [markers]);

    return <div ref={chartContainerRef} className="w-full shadow-xl rounded-lg overflow-hidden border border-slate-800" />;
};
