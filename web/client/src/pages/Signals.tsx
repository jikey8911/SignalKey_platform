import React, { useEffect, useState } from 'react';
import { SignalsKeiLayout } from '@/components/SignalsKeiLayout';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { trpc } from '@/lib/trpc';
import {
  AlertCircle,
  CheckCircle,
  Clock,
  XCircle,
  Zap,
  TrendingUp,
  TrendingDown,
  RefreshCw,
  Filter
} from 'lucide-react';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/_core/hooks/useAuth';
import { useSocket } from '@/_core/hooks/useSocket';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { CONFIG } from '@/config';

interface Signal {
  id: string; // Cambiado a string para compatibilidad con MongoDB
  userId: string;
  source: string;
  rawText: string;
  decision: string;
  symbol: string;
  marketType: string;
  confidence: number;
  reasoning: string;
  status: string;
  createdAt: string;
}

export default function Signals() {
  const { user } = useAuth({ redirectOnUnauthenticated: true });
  const queryClient = useQueryClient();
  const { data: signals, isLoading, refetch } = trpc.trading.getSignals.useQuery();
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState<'all' | 'processing' | 'accepted' | 'rejected' | 'executing' | 'completed' | 'failed' | 'error'>('all');
  const [filterMarketType, setFilterMarketType] = useState<'all' | 'CEX' | 'DEX' | 'SPOT' | 'FUTURES'>('all');
  const [filterDecision, setFilterDecision] = useState<'all' | 'BUY' | 'SELL' | 'HOLD'>('all');

  const { lastMessage } = useSocket(user?.openId);

  // Escuchar mensajes del socket
  useEffect(() => {
    if (lastMessage && lastMessage.event === 'signal_update') {
      const updatedSignal = lastMessage.data;

      // Actualizar el cache de react-query directamente para reflejar el cambio al instante
      queryClient.setQueryData(['trading.getSignals'], (oldData: Signal[] | undefined) => {
        if (!oldData) return [updatedSignal];

        const exists = oldData.find(s => s.id === updatedSignal.id);
        if (exists) {
          // Actualizar señal existente
          return oldData.map(s => s.id === updatedSignal.id ? { ...s, ...updatedSignal } : s);
        } else {
          // Nueva señal al inicio
          return [updatedSignal, ...oldData];
        }
      });
    }
  }, [lastMessage, queryClient]);

  const getDecisionIcon = (decision: string) => {
    switch (decision) {
      case 'BUY':
        return <TrendingUp className="text-green-600" size={18} />;
      case 'SELL':
        return <TrendingDown className="text-red-600" size={18} />;
      case 'HOLD':
        return <Clock className="text-yellow-600" size={18} />;
      default:
        return <AlertCircle className="text-gray-600" size={18} />;
    }
  };

  const getDecisionColor = (decision: string) => {
    switch (decision) {
      case 'BUY':
        return 'bg-green-500/20 text-green-400 border border-green-500/30';
      case 'SELL':
        return 'bg-red-500/20 text-red-400 border border-red-500/30';
      case 'HOLD':
        return 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30';
      default:
        return 'bg-slate-800 text-slate-300 border border-white/10';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'processing':
        return <Clock className="text-blue-600 animate-spin" size={18} />;
      case 'accepted':
        return <CheckCircle className="text-green-600" size={18} />;
      case 'rejected':
        return <XCircle className="text-red-600" size={18} />;
      case 'executing':
        return <Zap className="text-orange-600 animate-pulse" size={18} />;
      case 'completed':
        return <CheckCircle className="text-green-600" size={18} />;
      case 'failed':
        return <AlertCircle className="text-red-600" size={18} />;
      case 'error':
        return <AlertCircle className="text-red-600" size={18} />;
      default:
        return <Clock className="text-gray-600" size={18} />;
    }
  };

  const getStatusBadgeColor = (status: string) => {
    switch (status) {
      case 'processing':
        return 'bg-blue-500/20 text-blue-400 border border-blue-500/30';
      case 'accepted':
        return 'bg-green-500/20 text-green-400 border border-green-500/30';
      case 'rejected':
        return 'bg-red-500/20 text-red-400 border border-red-500/30';
      case 'executing':
        return 'bg-orange-500/20 text-orange-400 border border-orange-500/30';
      case 'completed':
        return 'bg-green-500/20 text-green-400 border border-green-500/30';
      case 'failed':
        return 'bg-red-500/20 text-red-400 border border-red-500/30';
      case 'error':
        return 'bg-red-500/20 text-red-400 border border-red-500/30';
      default:
        return 'bg-slate-800 text-slate-300 border border-white/10';
    }
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'processing':
        return 'Procesando';
      case 'accepted':
        return 'Aceptada';
      case 'rejected':
        return 'Rechazada';
      case 'executing':
        return 'En Ejecución';
      case 'completed':
        return 'Completada';
      case 'failed':
        return 'Fallida';
      case 'error':
        return 'Error';
      default:
        return 'Pendiente';
    }
  };

  const getMarketTypeColor = (marketType: string) => {
    switch (marketType) {
      case 'CEX':
        return 'bg-purple-500/20 text-purple-400 border border-purple-500/30';
      case 'DEX':
        return 'bg-indigo-500/20 text-indigo-400 border border-indigo-500/30';
      case 'SPOT':
        return 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30';
      case 'FUTURES':
        return 'bg-pink-500/20 text-pink-400 border border-pink-500/30';
      default:
        return 'bg-slate-800 text-slate-300 border border-white/10';
    }
  };

  // Filtrar señales
  const filteredSignals = (signals || []).filter((signal: Signal) => {
    const matchesSearch = (signal.symbol?.toLowerCase() || "").includes(searchTerm.toLowerCase()) ||
      (signal.source?.toLowerCase() || "").includes(searchTerm.toLowerCase()) ||
      (signal.rawText?.toLowerCase() || "").includes(searchTerm.toLowerCase());
    const matchesStatus = filterStatus === 'all' || signal.status === filterStatus;
    const matchesMarketType = filterMarketType === 'all' || signal.marketType === filterMarketType;
    const matchesDecision = filterDecision === 'all' || signal.decision === filterDecision;
    return matchesSearch && matchesStatus && matchesMarketType && matchesDecision;
  });

  // Estadísticas
  const stats = {
    total: signals?.length || 0,
    processing: signals?.filter((s: Signal) => s.status === 'processing').length || 0,
    accepted: signals?.filter((s: Signal) => s.status === 'accepted').length || 0,
    executing: signals?.filter((s: Signal) => s.status === 'executing').length || 0,
    completed: signals?.filter((s: Signal) => s.status === 'completed').length || 0,
    failed: signals?.filter((s: Signal) => s.status === 'failed' || s.status === 'error').length || 0,
  };

  const handleApprove = async (signalId: string) => {
    try {
      const res = await fetch(`${CONFIG.API_BASE_URL}/signals/${signalId}/approve`, {
        method: 'POST',
      });
      const data = await res.json();
      if (!data.success) {
        toast.error('Error', { description: data.message });
      }
    } catch (e: any) {
      toast.error('Error', { description: e.message });
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="space-y-6">
        {/* Header */}
        <div className="flex justify-between items-start">
          <div>
            <h2 className="text-3xl font-bold text-foreground mb-2">Feed de Señales de Trading</h2>
            <p className="text-muted-foreground">
              Señales analizadas por Gemini AI en tiempo real con estado de procesamiento
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2 px-3 py-1 bg-green-500/10 border border-green-500/20 rounded-full">
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
              <span className="text-[10px] font-bold text-green-600 uppercase tracking-wider">Live</span>
            </div>
            <Button
              variant="outline"
              size="icon"
              onClick={() => refetch()}
              disabled={isLoading}
            >
              <RefreshCw size={16} className={isLoading ? "animate-spin" : ""} />
            </Button>
          </div>
        </div>

        {/* Estadísticas */}
        <div className="grid grid-cols-6 gap-3">
          <Card className="p-3 border-l-4 border-l-gray-500">
            <div className="text-xs text-muted-foreground mb-1">Total</div>
            <div className="text-xl font-bold text-foreground">{stats.total}</div>
          </Card>
          <Card className="p-3 border-l-4 border-l-blue-500">
            <div className="text-xs text-muted-foreground mb-1">Procesando</div>
            <div className="text-xl font-bold text-blue-600">{stats.processing}</div>
          </Card>
          <Card className="p-3 border-l-4 border-l-green-500">
            <div className="text-xs text-muted-foreground mb-1">Aceptadas</div>
            <div className="text-xl font-bold text-green-600">{stats.accepted}</div>
          </Card>
          <Card className="p-3 border-l-4 border-l-orange-500">
            <div className="text-xs text-muted-foreground mb-1">Ejecutando</div>
            <div className="text-xl font-bold text-orange-600">{stats.executing}</div>
          </Card>
          <Card className="p-3 border-l-4 border-l-emerald-500">
            <div className="text-xs text-muted-foreground mb-1">Completadas</div>
            <div className="text-xl font-bold text-emerald-600">{stats.completed}</div>
          </Card>
          <Card className="p-3 border-l-4 border-l-red-500">
            <div className="text-xs text-muted-foreground mb-1">Fallidas</div>
            <div className="text-xl font-bold text-red-600">{stats.failed}</div>
          </Card>
        </div>

        {/* Filtros */}
        <Card className="p-4 bg-slate-900/40 border-white/5 shadow-inner backdrop-blur-xl">
          <div className="space-y-4">
            <div className="flex gap-3">
              <div className="flex-1">
                <Input
                  placeholder="Buscar por símbolo, fuente o contenido..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full"
                />
              </div>
            </div>
            <div className="space-y-3">
              <div>
                <div className="text-xs font-semibold text-muted-foreground mb-2">Estado de Procesamiento</div>
                <div className="flex gap-2 flex-wrap">
                  <Button
                    variant={filterStatus === 'all' ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => setFilterStatus('all')}
                  >
                    Todos
                  </Button>
                  <Button
                    variant={filterStatus === 'processing' ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => setFilterStatus('processing')}
                    className="gap-2"
                  >
                    <Clock size={14} />
                    Procesando
                  </Button>
                  <Button
                    variant={filterStatus === 'accepted' ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => setFilterStatus('accepted')}
                    className="gap-2"
                  >
                    <CheckCircle size={14} />
                    Aceptadas
                  </Button>
                  <Button
                    variant={filterStatus === 'executing' ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => setFilterStatus('executing')}
                    className="gap-2"
                  >
                    <Zap size={14} />
                    Ejecutando
                  </Button>
                  <Button
                    variant={filterStatus === 'completed' ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => setFilterStatus('completed')}
                    className="gap-2"
                  >
                    <CheckCircle size={14} />
                    Completadas
                  </Button>
                  <Button
                    variant={filterStatus === 'failed' ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => setFilterStatus('failed')}
                    className="gap-2"
                  >
                    <XCircle size={14} />
                    Fallidas
                  </Button>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-xs font-semibold text-muted-foreground mb-2">Tipo de Mercado</div>
                  <div className="flex gap-2 flex-wrap">
                    <Button
                      variant={filterMarketType === 'all' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setFilterMarketType('all')}
                    >
                      Todos
                    </Button>
                    <Button
                      variant={filterMarketType === 'CEX' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setFilterMarketType('CEX')}
                    >
                      CEX
                    </Button>
                    <Button
                      variant={filterMarketType === 'DEX' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setFilterMarketType('DEX')}
                    >
                      DEX
                    </Button>
                  </div>
                </div>
                <div>
                  <div className="text-xs font-semibold text-muted-foreground mb-2">Decisión</div>
                  <div className="flex gap-2 flex-wrap">
                    <Button
                      variant={filterDecision === 'all' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setFilterDecision('all')}
                    >
                      Todos
                    </Button>
                    <Button
                      variant={filterDecision === 'BUY' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setFilterDecision('BUY')}
                      className="gap-2"
                    >
                      <TrendingUp size={14} />
                      BUY
                    </Button>
                    <Button
                      variant={filterDecision === 'SELL' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setFilterDecision('SELL')}
                      className="gap-2"
                    >
                      <TrendingDown size={14} />
                      SELL
                    </Button>
                    <Button
                      variant={filterDecision === 'HOLD' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setFilterDecision('HOLD')}
                    >
                      HOLD
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </Card>

        {/* Señales */}
        {isLoading ? (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-40 bg-muted animate-pulse rounded-lg" />
            ))}
          </div>
        ) : filteredSignals.length > 0 ? (
          <div className="space-y-4">
            {filteredSignals.map((signal: Signal) => (
              <Card
                key={signal.id}
                className="p-6 border-l-4 hover:shadow-lg transition-shadow overflow-hidden"
                style={{
                  borderLeftColor: signal.status === 'processing' ? '#2563eb' :
                    signal.status === 'accepted' ? '#16a34a' :
                      signal.status === 'executing' ? '#ea580c' :
                        signal.status === 'completed' ? '#059669' :
                          signal.status === 'failed' || signal.status === 'error' ? '#dc2626' : '#6b7280'
                }}
              >
                {/* Header */}
                <div className="flex items-start justify-between mb-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-3 flex-wrap">
                      <h3 className="text-2xl font-bold text-foreground">
                        {signal.symbol}
                      </h3>
                      <div className={`px-3 py-1 rounded-full text-sm font-semibold flex items-center gap-2 ${getDecisionColor(signal.decision)}`}>
                        {getDecisionIcon(signal.decision)}
                        {signal.decision}
                      </div>
                      <div className={`px-3 py-1 rounded-full text-sm font-semibold ${getMarketTypeColor(signal.marketType)}`}>
                        {signal.marketType}
                      </div>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {signal.source} • {new Date(signal.createdAt).toLocaleString()}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-2">
                    <div className="flex items-center gap-2 bg-muted p-3 rounded-lg">
                      {getStatusIcon(signal.status)}
                      <span className={`text-sm font-semibold capitalize px-2 py-1 rounded border ${getStatusBadgeColor(signal.status)}`}>
                        {getStatusLabel(signal.status)}
                      </span>
                    </div>
                    {['processing', 'accepted', 'rejected', 'failed', 'error'].includes(signal.status) && (
                      <Button
                        size="sm"
                        className="w-full gap-2"
                        onClick={() => handleApprove(signal.id)}
                      >
                        <Zap size={14} />
                        Aprobar y Ejecutar
                      </Button>
                    )}
                  </div>
                </div>

                {/* Detalles */}
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
                      {getStatusLabel(signal.status)}
                    </p>
                  </div>
                </div>

                {/* Análisis */}
                {signal.reasoning && (
                  <div className="mb-4">
                    <p className="text-xs text-muted-foreground mb-2 font-semibold">Análisis de Gemini AI</p>
                    <p className="text-sm text-foreground bg-muted p-3 rounded-lg border border-border">
                      {signal.reasoning}
                    </p>
                  </div>
                )}

                {/* Señal Original */}
                <div className="pt-4 border-t border-border">
                  <p className="text-xs text-muted-foreground mb-2 font-semibold">Señal Original</p>
                  <p className="text-sm text-foreground bg-muted p-3 rounded-lg italic border border-border max-h-24 overflow-hidden">
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
              {signals?.length === 0
                ? "No hay señales aún. Las señales aparecerán aquí cuando se reciban desde Telegram o webhooks."
                : "No hay señales que coincidan con los filtros seleccionados."}
            </p>
          </Card>
        )}
      </div>
    </div>
  );
}
