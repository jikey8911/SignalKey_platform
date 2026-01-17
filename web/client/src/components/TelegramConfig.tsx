import React, { useState, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { Eye, EyeOff, CheckCircle, XCircle, AlertCircle } from 'lucide-react';

interface TelegramConfigProps {
    userId: string;
}

interface TelegramStatus {
    connected: boolean;
    phone_number?: string;
    last_connected?: string;
}

export function TelegramConfig({ userId }: TelegramConfigProps) {
    const [telegramApiId, setTelegramApiId] = useState('');
    const [telegramApiHash, setTelegramApiHash] = useState('');
    const [telegramPhone, setTelegramPhone] = useState('');
    const [showApiHash, setShowApiHash] = useState(false);
    const [status, setStatus] = useState<TelegramStatus | null>(null);
    const [loading, setLoading] = useState(false);
    const [showCodeModal, setShowCodeModal] = useState(false);
    const [verificationCode, setVerificationCode] = useState('');

    // Cargar estado de Telegram
    useEffect(() => {
        fetchTelegramStatus();
    }, [userId]);

    const fetchTelegramStatus = async () => {
        try {
            const response = await fetch(`http://localhost:8000/telegram/status/${userId}`);
            const data = await response.json();
            setStatus(data);
        } catch (error) {
            console.error('Error fetching Telegram status:', error);
        }
    };

    const handleConnect = async () => {
        if (!telegramApiId || !telegramApiHash || !telegramPhone) {
            toast.error('Por favor completa todos los campos');
            return;
        }

        setLoading(true);
        try {
            const response = await fetch(`http://localhost:8000/telegram/auth/start?user_id=${userId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    phone_number: telegramPhone,
                    api_id: telegramApiId,
                    api_hash: telegramApiHash
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Error al conectar');
            }

            toast.success('Código de verificación enviado a tu Telegram');
            setShowCodeModal(true);
        } catch (error: any) {
            toast.error(error.message || 'Error al conectar con Telegram');
        } finally {
            setLoading(false);
        }
    };

    const handleVerifyCode = async () => {
        if (!verificationCode) {
            toast.error('Por favor ingresa el código');
            return;
        }

        setLoading(true);
        try {
            const response = await fetch(`http://localhost:8000/telegram/auth/verify?user_id=${userId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    code: verificationCode
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Código inválido');
            }

            toast.success('¡Telegram conectado exitosamente!');
            setShowCodeModal(false);
            setVerificationCode('');
            fetchTelegramStatus();
        } catch (error: any) {
            toast.error(error.message || 'Error al verificar código');
        } finally {
            setLoading(false);
        }
    };

    const handleDisconnect = async () => {
        if (!confirm('¿Estás seguro de desconectar Telegram?')) {
            return;
        }

        setLoading(true);
        try {
            const response = await fetch(`http://localhost:8000/telegram/disconnect?user_id=${userId}`, {
                method: 'POST'
            });

            if (!response.ok) {
                throw new Error('Error al desconectar');
            }

            toast.success('Telegram desconectado');
            setStatus({ connected: false });
            setTelegramApiId('');
            setTelegramApiHash('');
            setTelegramPhone('');
        } catch (error: any) {
            toast.error(error.message || 'Error al desconectar');
        } finally {
            setLoading(false);
        }
    };

    return (
        <>
            <Card className="p-6">
                <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                    🔵 Configuración de Telegram
                    {status?.connected && <CheckCircle className="text-green-600" size={20} />}
                </h3>

                {!status?.connected ? (
                    <div className="space-y-4">
                        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
                            <div className="flex gap-2">
                                <AlertCircle className="text-blue-600 flex-shrink-0 mt-0.5" size={18} />
                                <div className="text-sm text-blue-900">
                                    <strong>Para obtener tus credenciales:</strong>
                                    <ol className="list-decimal ml-4 mt-2 space-y-1">
                                        <li>Ve a <a href="https://my.telegram.org" target="_blank" rel="noopener noreferrer" className="underline">my.telegram.org</a></li>
                                        <li>Inicia sesión con tu número de teléfono</li>
                                        <li>Ve a "API development tools"</li>
                                        <li>Crea una aplicación si no tienes una</li>
                                        <li>Copia tu API ID y API Hash</li>
                                    </ol>
                                </div>
                            </div>
                        </div>

                        <div>
                            <label className="block text-sm font-medium mb-2">Número de Teléfono</label>
                            <Input
                                type="tel"
                                placeholder="+1234567890"
                                value={telegramPhone}
                                onChange={(e) => setTelegramPhone(e.target.value)}
                            />
                            <p className="text-xs text-muted-foreground mt-1">Incluye el código de país (ej: +57)</p>
                        </div>

                        <div>
                            <label className="block text-sm font-medium mb-2">API ID</label>
                            <Input
                                type="text"
                                placeholder="12345678"
                                value={telegramApiId}
                                onChange={(e) => setTelegramApiId(e.target.value)}
                            />
                        </div>

                        <div>
                            <label className="block text-sm font-medium mb-2">API Hash</label>
                            <div className="relative">
                                <Input
                                    type={showApiHash ? 'text' : 'password'}
                                    placeholder="abcdef1234567890"
                                    value={telegramApiHash}
                                    onChange={(e) => setTelegramApiHash(e.target.value)}
                                    className="pr-10"
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowApiHash(!showApiHash)}
                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                                >
                                    {showApiHash ? <EyeOff size={18} /> : <Eye size={18} />}
                                </button>
                            </div>
                        </div>

                        <Button
                            onClick={handleConnect}
                            disabled={loading}
                            className="w-full"
                        >
                            {loading ? 'Conectando...' : 'Conectar Telegram'}
                        </Button>
                    </div>
                ) : (
                    <div className="space-y-4">
                        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                            <div className="flex items-center gap-2">
                                <CheckCircle className="text-green-600" size={20} />
                                <div>
                                    <p className="font-semibold text-green-900">Telegram Conectado</p>
                                    <p className="text-sm text-green-700">{status.phone_number}</p>
                                    {status.last_connected && (
                                        <p className="text-xs text-green-600 mt-1">
                                            Última conexión: {new Date(status.last_connected).toLocaleString()}
                                        </p>
                                    )}
                                </div>
                            </div>
                        </div>

                        <Button
                            onClick={handleDisconnect}
                            disabled={loading}
                            variant="destructive"
                            className="w-full"
                        >
                            {loading ? 'Desconectando...' : 'Desconectar Telegram'}
                        </Button>
                    </div>
                )}
            </Card>

            {/* Modal de Verificación de Código */}
            {showCodeModal && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <Card className="p-6 max-w-md w-full mx-4">
                        <h3 className="text-lg font-semibold mb-4">Código de Verificación</h3>
                        <p className="text-sm text-muted-foreground mb-4">
                            Ingresa el código que recibiste en tu aplicación de Telegram
                        </p>
                        <Input
                            type="text"
                            placeholder="12345"
                            value={verificationCode}
                            onChange={(e) => setVerificationCode(e.target.value)}
                            className="mb-4"
                            autoFocus
                        />
                        <div className="flex gap-2">
                            <Button
                                onClick={handleVerifyCode}
                                disabled={loading}
                                className="flex-1"
                            >
                                {loading ? 'Verificando...' : 'Verificar'}
                            </Button>
                            <Button
                                onClick={() => {
                                    setShowCodeModal(false);
                                    setVerificationCode('');
                                }}
                                variant="outline"
                                disabled={loading}
                            >
                                Cancelar
                            </Button>
                        </div>
                    </Card>
                </div>
            )}
        </>
    );
}
