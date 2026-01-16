import React from 'react';
import { SignalsKeiLayout } from '@/components/SignalsKeiLayout';
import { Card } from '@/components/ui/card';
import { trpc } from '@/lib/trpc';
import { AlertCircle, CheckCircle, Clock } from 'lucide-react';

export default function Signals() {
  const { data: signals, isLoading } = trpc.trading.getSignals.useQuery();

  const getDecisionColor = (decision: string) => {
    switch (decision) {
      case 'BUY':
        return 'bg-green-100 text-green-800';
      case 'SELL':
        return 'bg-red-100 text-red-800';
      case 'HOLD':
        return 'bg-yellow-100 text-yellow-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const getStatusIcon = (status: string | null) => {
    switch (status) {
      case 'executed':
        return <CheckCircle className="text-green-600" size={18} />;
      case 'pending':
        return <Clock className="text-yellow-600" size={18} />;
      case 'failed':
        return <AlertCircle className="text-red-600" size={18} />;
      default:
        return <Clock className="text-gray-600" size={18} />;
    }
  };

  return (
    <SignalsKeiLayout currentPage="/signals">
      <div className="space-y-6">
        <div>
          <h2 className="text-3xl font-bold text-foreground mb-2">Feed de Señales</h2>
          <p className="text-muted-foreground">
            Señales de trading analizadas por Gemini AI en tiempo real
          </p>
        </div>

        {isLoading ? (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-32 bg-muted animate-pulse rounded-lg" />
            ))}
          </div>
        ) : signals && signals.length > 0 ? (
          <div className="space-y-4">
            {signals.map((signal: any) => (
              <Card
                key={signal.id}
                className="p-6 border-l-4 border-l-primary hover:shadow-lg transition-shadow"
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <h3 className="text-xl font-bold text-foreground">
                        {signal.symbol}
                      </h3>
                      <div className={`px-3 py-1 rounded-full text-sm font-semibold ${getDecisionColor(signal.decision)}`}>
                        {signal.decision}
                      </div>
                      <div className="px-3 py-1 rounded-full text-sm font-semibold border border-border text-foreground">
                        {signal.marketType}
                      </div>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {signal.source} • {new Date(signal.createdAt).toLocaleString()}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {getStatusIcon(signal.status)}
                    <span className="text-sm font-semibold text-muted-foreground capitalize">
                      {signal.status}
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4 pb-4 border-b border-border">
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">Confianza</p>
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                        <div
                          className="h-full bg-primary"
                          style={{
                            width: `${(signal.confidence || 0) * 100}%`,
                          }}
                        />
                      </div>
                      <span className="text-sm font-semibold">
                        {Math.round((signal.confidence || 0) * 100)}%
                      </span>
                    </div>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">Tipo de Mercado</p>
                    <p className="text-sm font-semibold text-foreground">
                      {signal.marketType}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">Fuente</p>
                    <p className="text-sm font-semibold text-foreground capitalize">
                      {signal.source}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">Estado</p>
                    <p className="text-sm font-semibold text-foreground capitalize">
                      {signal.status}
                    </p>
                  </div>
                </div>

                {signal.reasoning && (
                  <div>
                    <p className="text-xs text-muted-foreground mb-2">Análisis de Gemini AI</p>
                    <p className="text-sm text-foreground bg-muted p-3 rounded-lg">
                      {signal.reasoning}
                    </p>
                  </div>
                )}

                <div className="mt-4 pt-4 border-t border-border">
                  <p className="text-xs text-muted-foreground mb-2">Señal Original</p>
                  <p className="text-sm text-foreground bg-muted p-3 rounded-lg italic">
                    "{signal.rawText}"
                  </p>
                </div>
              </Card>
            ))}
          </div>
        ) : (
          <Card className="p-12 text-center">
            <AlertCircle className="mx-auto mb-4 text-muted-foreground" size={48} />
            <p className="text-lg text-muted-foreground">
              No hay señales aún. Las señales aparecerán aquí cuando se reciban desde Telegram o webhooks.
            </p>
          </Card>
        )}
      </div>
    </SignalsKeiLayout>
  );
}
