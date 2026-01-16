import React, { useState } from 'react';
import { SignalsKeiLayout } from '@/components/SignalsKeiLayout';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Play, BarChart3 } from 'lucide-react';
import { toast } from 'sonner';

export default function Backtest() {
  const [symbol, setSymbol] = useState('BTC-USDT');
  const [timeframe, setTimeframe] = useState('1h');
  const [days, setDays] = useState(30);
  const [isRunning, setIsRunning] = useState(false);
  const [results, setResults] = useState<any>(null);

  const handleRunBacktest = async () => {
    setIsRunning(true);
    try {
      toast.loading('Ejecutando backtesting...');
      
      // Simular resultados de backtesting
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      const mockResults = {
        symbol,
        timeframe,
        days,
        totalTrades: Math.floor(Math.random() * 50) + 10,
        winRate: Math.floor(Math.random() * 60) + 30,
        profitFactor: (Math.random() * 2 + 0.5).toFixed(2),
        maxDrawdown: (Math.random() * 30 + 5).toFixed(2),
        totalReturn: (Math.random() * 100 - 20).toFixed(2),
        sharpeRatio: (Math.random() * 2 + 0.5).toFixed(2),
      };
      
      setResults(mockResults);
      toast.success('Backtesting completado');
    } catch (error) {
      toast.error('Error al ejecutar backtesting');
    } finally {
      setIsRunning(false);
    }
  };

  const StatBox = ({ label, value, unit = '' }: any) => (
    <div className="p-4 bg-muted rounded-lg">
      <p className="text-xs text-muted-foreground mb-1">{label}</p>
      <p className="text-2xl font-bold text-foreground">
        {value}{unit}
      </p>
    </div>
  );

  return (
    <SignalsKeiLayout currentPage="/backtest">
      <div className="space-y-6 max-w-4xl">
        <div>
          <h2 className="text-3xl font-bold text-foreground mb-2">Backtesting</h2>
          <p className="text-muted-foreground">
            Prueba tus estrategias con datos históricos
          </p>
        </div>

        {/* Configuration */}
        <Card className="p-6">
          <h3 className="text-lg font-semibold text-foreground mb-4">Configuración</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div>
              <label className="block text-sm font-semibold text-foreground mb-2">
                Símbolo
              </label>
              <input
                type="text"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                placeholder="BTC-USDT"
                className="w-full px-4 py-2 border border-border rounded-lg bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div>
              <label className="block text-sm font-semibold text-foreground mb-2">
                Timeframe
              </label>
              <select
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                className="w-full px-4 py-2 border border-border rounded-lg bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="1m">1 minuto</option>
                <option value="5m">5 minutos</option>
                <option value="15m">15 minutos</option>
                <option value="1h">1 hora</option>
                <option value="4h">4 horas</option>
                <option value="1d">1 día</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-semibold text-foreground mb-2">
                Días históricos
              </label>
              <input
                type="number"
                value={days}
                onChange={(e) => setDays(parseInt(e.target.value))}
                min="1"
                max="365"
                className="w-full px-4 py-2 border border-border rounded-lg bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
          </div>
          <Button
            onClick={handleRunBacktest}
            disabled={isRunning}
            className="flex items-center gap-2 w-full md:w-auto"
          >
            <Play size={18} />
            {isRunning ? 'Ejecutando...' : 'Ejecutar Backtesting'}
          </Button>
        </Card>

        {/* Results */}
        {results && (
          <Card className="p-6">
            <div className="flex items-center gap-2 mb-6">
              <BarChart3 className="text-primary" size={24} />
              <h3 className="text-lg font-semibold text-foreground">Resultados</h3>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
              <StatBox label="Total de Trades" value={results.totalTrades} />
              <StatBox label="Win Rate" value={results.winRate} unit="%" />
              <StatBox label="Profit Factor" value={results.profitFactor} />
              <StatBox label="Max Drawdown" value={results.maxDrawdown} unit="%" />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <StatBox label="Retorno Total" value={results.totalReturn} unit="%" />
              <StatBox label="Sharpe Ratio" value={results.sharpeRatio} />
            </div>

            {/* Chart Placeholder */}
            <div className="mt-6 p-6 bg-muted rounded-lg">
              <p className="text-center text-muted-foreground">
                📊 Gráfico de equity curve (próximamente)
              </p>
            </div>
          </Card>
        )}

        {!results && (
          <Card className="p-12 text-center">
            <BarChart3 className="mx-auto mb-4 text-muted-foreground" size={48} />
            <p className="text-lg text-muted-foreground">
              Configura los parámetros y ejecuta un backtesting para ver los resultados
            </p>
          </Card>
        )}
      </div>
    </SignalsKeiLayout>
  );
}
