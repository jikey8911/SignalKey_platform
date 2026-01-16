import React, { useEffect, useState } from 'react';
import { SignalsKeiLayout } from '@/components/SignalsKeiLayout';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { RefreshCw, Search } from 'lucide-react';
import { toast } from 'sonner';

export default function TelegramConsole() {
    const [logs, setLogs] = useState<any[]>([]);
    const [loading, setLoading] = useState(false);
    const [autoRefresh, setAutoRefresh] = useState(true);

    const fetchLogs = async () => {
        setLoading(true);
        try {
            const res = await fetch('http://localhost:8000/telegram/logs?limit=50');
            const data = await res.json();
            if (Array.isArray(data)) {
                setLogs(data);
            }
        } catch (e) {
            console.error(e);
            // Don't toast on auto-refresh to avoid spam
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchLogs();
        const interval = setInterval(() => {
            if (autoRefresh) fetchLogs();
        }, 3000); // 3 seconds refresh
        return () => clearInterval(interval);
    }, [autoRefresh]);

    return (
        <SignalsKeiLayout currentPage="/telegram-console">
            <div className="space-y-6 max-w-6xl">
                <div className="flex justify-between items-center">
                    <div>
                        <h2 className="text-3xl font-bold text-foreground mb-2">Telegram Console</h2>
                        <p className="text-muted-foreground">Monitor de mensajes entrantes en tiempo real</p>
                    </div>
                    <div className="flex items-center gap-2">
                        <Button
                            variant={autoRefresh ? "secondary" : "outline"}
                            size="sm"
                            onClick={() => setAutoRefresh(!autoRefresh)}
                            className="gap-2"
                        >
                            {autoRefresh ? "Auto-Refresh ON" : "Auto-Refresh OFF"}
                        </Button>
                        <Button variant="outline" size="icon" onClick={fetchLogs} disabled={loading}>
                            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
                        </Button>
                    </div>
                </div>

                <Card className="p-0 overflow-hidden border border-border">
                    <div className="bg-muted/50 p-3 border-b border-border flex justify-between text-xs font-semibold text-muted-foreground">
                        <div className="w-1/6">Hora</div>
                        <div className="w-1/6">Chat / Canal</div>
                        <div className="w-3/6">Mensaje</div>
                        <div className="w-1/6 text-right">Estado</div>
                    </div>
                    <div className="divide-y divide-border max-h-[70vh] overflow-y-auto bg-background">
                        {logs.length === 0 ? (
                            <div className="p-8 text-center text-muted-foreground">Esperando mensajes...</div>
                        ) : (
                            logs.map((log) => (
                                <div key={log._id} className="p-3 flex text-sm hover:bg-muted/20 transition-colors">
                                    <div className="w-1/6 text-muted-foreground whitespace-nowrap">
                                        {new Date(log.timestamp).toLocaleTimeString()}
                                    </div>
                                    <div className="w-1/6 font-medium truncate pr-2" title={`${log.chatName} (${log.chatId})`}>
                                        {log.chatName}
                                        <div className="text-[10px] text-muted-foreground opacity-70">{log.chatId}</div>
                                    </div>
                                    <div className="w-3/6 pr-4 whitespace-pre-wrap break-words font-mono text-xs text-foreground/90">
                                        {log.message.slice(0, 300)}
                                        {log.message.length > 300 && "..."}
                                    </div>
                                    <div className="w-1/6 text-right flex justify-end">
                                        <span className={`px-2 py-1 rounded text-[10px] font-bold uppercase ${log.status === 'processed'
                                                ? 'bg-green-100 text-green-700 border border-green-200'
                                                : 'bg-gray-100 text-gray-500 border border-gray-200'
                                            }`}>
                                            {log.status === 'processed' ? 'PROCESS' : 'IGNORE'}
                                        </span>
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                </Card>
            </div>
        </SignalsKeiLayout>
    );
}
