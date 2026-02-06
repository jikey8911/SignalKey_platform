import React, { useEffect, useRef, useState } from 'react';
import { View, ActivityIndicator } from 'react-native';
import { WebView } from 'react-native-webview';

interface ChartProps {
  data?: any[];
  trades?: any[];
  height?: number;
  symbol?: string;
  timeframe?: string;
}

const HTML = `
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
  <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
  <style>
    body { margin: 0; padding: 0; background-color: #0f172a; overflow: hidden; }
    #container { width: 100%; height: 100vh; }
  </style>
</head>
<body>
  <div id="container"></div>
  <script>
    let chart;
    let candlestickSeries;
    let markers = [];

    const container = document.getElementById('container');

    function initChart() {
      chart = LightweightCharts.createChart(container, {
        layout: {
          background: { type: 'solid', color: '#0f172a' },
          textColor: '#94a3b8',
        },
        grid: {
          vertLines: { color: '#1e293b' },
          horzLines: { color: '#1e293b' },
        },
        timeScale: {
          timeVisible: true,
          secondsVisible: false,
        }
      });

      candlestickSeries = chart.addSeries(LightweightCharts.CandlestickSeries, {
        upColor: '#22c55e',
        downColor: '#ef4444',
        borderVisible: false,
        wickUpColor: '#22c55e',
        wickDownColor: '#ef4444',
      });

      window.addEventListener('resize', () => {
        chart.resize(window.innerWidth, window.innerHeight);
      });
    }

    // Initialize immediately
    initChart();

    // Handle messages from React Native
    document.addEventListener('message', handleMessage);
    window.addEventListener('message', handleMessage);

    function handleMessage(event) {
      try {
        const message = JSON.parse(event.data);
        if (message.type === 'SET_DATA') {
           const data = message.payload.map(d => ({
             ...d,
             time: typeof d.time === 'string' ? new Date(d.time).getTime() / 1000 : d.time
           }));
           candlestickSeries.setData(data);
           chart.timeScale().fitContent();
        }
        if (message.type === 'SET_MARKERS') {
           const newMarkers = message.payload.map(m => ({
             time: typeof m.time === 'string' ? new Date(m.time).getTime() / 1000 : m.time,
             position: m.side === 'BUY' ? 'belowBar' : 'aboveBar',
             color: m.side === 'BUY' ? '#22c55e' : '#ef4444',
             shape: m.side === 'BUY' ? 'arrowUp' : 'arrowDown',
             text: m.label || m.side,
           }));
           candlestickSeries.setMarkers(newMarkers);
        }
      } catch (e) {
        // console.log(e);
      }
    }
  </script>
</body>
</html>
`;

export function Chart({ data, trades, height = 300 }: ChartProps) {
  const webviewRef = useRef<WebView>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (loaded && data && data.length > 0) {
      webviewRef.current?.postMessage(JSON.stringify({
        type: 'SET_DATA',
        payload: data
      }));
    }
  }, [loaded, data]);

  useEffect(() => {
    if (loaded && trades && trades.length > 0) {
        webviewRef.current?.postMessage(JSON.stringify({
            type: 'SET_MARKERS',
            payload: trades
        }));
    }
  }, [loaded, trades]);

  return (
    <View style={{ height, overflow: 'hidden', borderRadius: 8, backgroundColor: '#0f172a' }}>
      {!loaded && (
        <View className="absolute inset-0 flex items-center justify-center z-10">
          <ActivityIndicator color="#22c55e" />
        </View>
      )}
      <WebView
        ref={webviewRef}
        originWhitelist={['*']}
        source={{ html: HTML }}
        onLoadEnd={() => setLoaded(true)}
        style={{ backgroundColor: '#0f172a' }}
        scrollEnabled={false}
      />
    </View>
  );
}
