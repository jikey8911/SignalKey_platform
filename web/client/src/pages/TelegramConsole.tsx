import React, { useEffect, useState } from 'react';
import { SignalsKeiLayout } from '@/components/SignalsKeiLayout';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { RefreshCw, Search, MessageSquare, AlertCircle, CheckCircle } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { useAuth } from '@/_core/hooks/useAuth';
import { useSocket } from '@/_core/hooks/useSocket';
import { CONFIG } from '@/config';

interface TelegramLog {
  _id: string;
  chatId: string;
  chatName: string;
  message: string;
  timestamp: string;
  status: 'received' | 'signal_detected' | 'processed' | 'ignored';
}

export default function TelegramConsole() {
  const { user } = useAuth({ redirectOnUnauthenticated: true });
  const [logs, setLogs] = useState<TelegramLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState<'all' | 'received' | 'signal_detected' | 'processed' | 'ignored'>('all');

  const { lastMessage } = useSocket(user?.openId);

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${CONFIG.API_BASE_URL}/telegram/logs?limit=100`);
      const data = await res.json();
      if (Array.isArray(data)) {
        setLogs(data);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, []);

  // Escuchar mensajes del socket
  useEffect(() => {
    if (lastMessage && lastMessage.event === 'telegram_log') {
      const newLog = lastMessage.data;
      setLogs(prev => [newLog, ...prev.slice(0, 99)]);

      // Feedback visual opcional
      if (newLog.status === 'signal_detected') {
        toast.info(`Nueva señal detectada de ${newLog.chatName}`);
      }
    }
  }, [lastMessage]);

  // Filtrar logs por búsqueda y estado
  const filteredLogs = logs.filter(log => {
    const matchesSearch = log.message.toLowerCase().includes(searchTerm.toLowerCase()) ||
      log.chatName.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesStatus = filterStatus === 'all' || log.status === filterStatus;
    return matchesSearch && matchesStatus;
  });

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'signal_detected':
        return <AlertCircle className="text-blue-600" size={16} />;
      case 'processed':
        return <CheckCircle className="text-green-600" size={16} />;
      case 'received':
        return <MessageSquare className="text-gray-600" size={16} />;
      default:
        return <MessageSquare className="text-gray-400" size={16} />;
    }
  };

  const getStatusBadgeColor = (status: string) => {
    switch (status) {
      case 'signal_detected':
        return 'bg-blue-100 text-blue-700 border border-blue-200';
      case 'processed':
        return 'bg-green-100 text-green-700 border border-green-200';
      case 'received':
        return 'bg-gray-100 text-gray-700 border border-gray-200';
      default:
        return 'bg-yellow-100 text-yellow-700 border border-yellow-200';
    }
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'signal_detected':
        return 'SEÑAL DETECTADA';
      case 'processed':
        return 'PROCESADO';
      case 'received':
        return 'RECIBIDO';
      default:
        return 'IGNORADO';
    }
  };

  const stats = {
    total: logs.length,
    signals: logs.filter(l => l.status === 'signal_detected').length,
    processed: logs.filter(l => l.status === 'processed').length,
    received: logs.filter(l => l.status === 'received').length,
  };

  return (
    <div className="p-6 space-y-6">
      <div className="space-y-6 max-w-7xl">
        {/* Header */}
        <div className="flex justify-between items-start">
          <div>
            <h2 className="text-3xl font-bold text-foreground mb-2">Consola de Telegram</h2>
            <p className="text-muted-foreground">Monitor de todos los mensajes entrantes en tiempo real (sin filtrar)</p>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2 px-3 py-1 bg-green-500/10 border border-green-500/20 rounded-full">
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
              <span className="text-[10px] font-bold text-green-600 uppercase tracking-wider">Live</span>
            </div>
            <Button
              variant="outline"
              size="icon"
              onClick={fetchLogs}
              disabled={loading}
            >
              <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            </Button>
          </div>
        </div>

        {/* Estadísticas */}
        <div className="grid grid-cols-4 gap-4">
          <Card className="p-4 border-l-4 border-l-gray-500">
            <div className="text-sm text-muted-foreground mb-1">Total Mensajes</div>
            <div className="text-2xl font-bold text-foreground">{stats.total}</div>
          </Card>
          <Card className="p-4 border-l-4 border-l-blue-500">
            <div className="text-sm text-muted-foreground mb-1">Señales Detectadas</div>
            <div className="text-2xl font-bold text-blue-600">{stats.signals}</div>
          </Card>
          <Card className="p-4 border-l-4 border-l-green-500">
            <div className="text-sm text-muted-foreground mb-1">Procesados</div>
            <div className="text-2xl font-bold text-green-600">{stats.processed}</div>
          </Card>
          <Card className="p-4 border-l-4 border-l-gray-400">
            <div className="text-sm text-muted-foreground mb-1">Recibidos</div>
            <div className="text-2xl font-bold text-gray-600">{stats.received}</div>
          </Card>
        </div>

        {/* Filtros */}
        <Card className="p-4 bg-muted/50">
          <div className="space-y-4">
            <div className="flex gap-3">
              <div className="flex-1">
                <Input
                  placeholder="Buscar en mensajes o chats..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full"
                />
              </div>
            </div>
            <div className="flex gap-2 flex-wrap">
              <Button
                variant={filterStatus === 'all' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setFilterStatus('all')}
              >
                Todos ({logs.length})
              </Button>
              <Button
                variant={filterStatus === 'signal_detected' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setFilterStatus('signal_detected')}
                className="gap-2"
              >
                <AlertCircle size={14} />
                Señales ({stats.signals})
              </Button>
              <Button
                variant={filterStatus === 'processed' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setFilterStatus('processed')}
                className="gap-2"
              >
                <CheckCircle size={14} />
                Procesados ({stats.processed})
              </Button>
              <Button
                variant={filterStatus === 'received' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setFilterStatus('received')}
                className="gap-2"
              >
                <MessageSquare size={14} />
                Recibidos ({stats.received})
              </Button>
            </div>
          </div>
        </Card>

        {/* Tabla de Mensajes */}
        <Card className="p-0 overflow-hidden border border-border">
          <div className="bg-muted/50 p-4 border-b border-border grid grid-cols-12 gap-4 text-xs font-semibold text-muted-foreground sticky top-0">
            <div className="col-span-1">Hora</div>
            <div className="col-span-2">Chat / Canal</div>
            <div className="col-span-7">Mensaje</div>
            <div className="col-span-2 text-right">Estado</div>
          </div>
          <div className="divide-y divide-border max-h-[70vh] overflow-y-auto bg-background">
            {filteredLogs.length === 0 ? (
              <div className="p-8 text-center text-muted-foreground col-span-12">
                {logs.length === 0 ? "Esperando mensajes..." : "No hay mensajes que coincidan con los filtros"}
              </div>
            ) : (
              filteredLogs.map((log) => (
                <div
                  key={log._id}
                  className="p-4 grid grid-cols-12 gap-4 text-sm hover:bg-muted/30 transition-colors border-l-4"
                  style={{
                    borderLeftColor: log.status === 'signal_detected' ? '#2563eb' :
                      log.status === 'processed' ? '#16a34a' :
                        log.status === 'received' ? '#6b7280' : '#d1d5db'
                  }}
                >
                  <div className="col-span-1 text-muted-foreground whitespace-nowrap text-xs">
                    {new Date(log.timestamp).toLocaleTimeString()}
                  </div>
                  <div className="col-span-2 font-medium truncate pr-2">
                    <div title={`${log.chatName} (${log.chatId})`} className="truncate">
                      {log.chatName}
                    </div>
                    <div className="text-[10px] text-muted-foreground opacity-70">{log.chatId}</div>
                  </div>
                  <div className="col-span-7 pr-4 whitespace-pre-wrap break-words font-mono text-xs text-foreground/90 max-h-24 overflow-hidden">
                    {log.message.slice(0, 500)}
                    {log.message.length > 500 && "..."}
                  </div>
                  <div className="col-span-2 text-right flex justify-end items-center gap-2">
                    {getStatusIcon(log.status)}
                    <span className={`px-2 py-1 rounded text-[10px] font-bold uppercase whitespace-nowrap ${getStatusBadgeColor(log.status)}`}>
                      {getStatusLabel(log.status)}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </Card>

        {/* Info */}
        <Card className="p-4 bg-blue-50 border-blue-200">
          <div className="flex gap-3">
            <AlertCircle className="text-blue-600 flex-shrink-0 mt-0.5" size={18} />
            <div className="text-sm text-blue-900">
              <strong>Nota:</strong> Esta consola muestra TODOS los mensajes recibidos sin filtrar.
              Los mensajes marcados como "SEÑAL DETECTADA" son aquellos que provienen de chats seleccionados en la configuración
              y serán procesados por la IA. Usa la página de "Señales" para ver solo las señales de trading procesadas.
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
