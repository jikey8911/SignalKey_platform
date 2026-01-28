import React, { useState, useEffect } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { Eye, EyeOff, CheckCircle, XCircle, AlertCircle } from 'lucide-react';
import { CONFIG } from '@/config';

interface TelegramConfigProps {
    userId: string;
    telegramApiId?: string;
    telegramApiHash?: string;
    telegramPhoneNumber?: string;
}

interface TelegramStatus {
    connected: boolean;
    phone_number?: string;
    last_connected?: string;
}

export function TelegramConfig({ userId, telegramApiId: initialApiId, telegramApiHash: initialApiHash, telegramPhoneNumber: initialPhone }: TelegramConfigProps) {
    const [telegramApiId, setTelegramApiId] = useState(initialApiId || '');
    const [telegramApiHash, setTelegramApiHash] = useState(initialApiHash || '');
    const [telegramPhone, setTelegramPhone] = useState(initialPhone || '');
    const [showApiHash, setShowApiHash] = useState(false);
    const [status, setStatus] = useState<TelegramStatus | null>(null);
    const [loading, setLoading] = useState(false);
    const [showCodeModal, setShowCodeModal] = useState(false);
    const [verificationCode, setVerificationCode] = useState('');
    const [timeLeft, setTimeLeft] = useState(0);
    const [modalMessage, setModalMessage] = useState<{ type: 'info' | 'error', text: string } | null>(null);

    // Cargar estado de Telegram
    useEffect(() => {
        fetchTelegramStatus();
    }, [userId]);

    // Actualizar estado si llegan props de configuración (ej. al cargar desde DB)
    useEffect(() => {
        if (initialApiId) setTelegramApiId(initialApiId);
        if (initialApiHash) setTelegramApiHash(initialApiHash);
        if (initialPhone) setTelegramPhone(initialPhone);
    }, [initialApiId, initialApiHash, initialPhone]);

    // Cuenta regresiva para el código
    useEffect(() => {
        let interval: NodeJS.Timeout;
        if (showCodeModal && timeLeft > 0) {
            interval = setInterval(() => {
                setTimeLeft((prev) => prev - 1);
            }, 1000);
        } else if (showCodeModal && timeLeft === 0) {
            // Mostrar mensaje cuando el tiempo se agota
            setModalMessage((prev) => {
                if (prev?.type === 'error' || prev?.text?.includes('finalizado')) return prev;
                return { 
                    type: 'info', 
                    text: 'El tiempo ha finalizado. Puedes solicitar un nuevo código.' 
                };
            });
        }
        return () => clearInterval(interval);
    }, [showCodeModal, timeLeft]);

    const formatTime = (seconds: number) => {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    const fetchTelegramStatus = async () => {
        try {
            const response = await fetch(`${CONFIG.API_BASE_URL}/telegram/status/${userId}`);
            const data = await response.json();
            setStatus(data);
        } catch (error) {
            console.error('Error fetching Telegram status:', error);
        }
    };

    const handleConnect = async (forceSMS: boolean | any = false) => {
        const isForceSMS = typeof forceSMS === 'boolean' ? forceSMS : false;

        if (!telegramApiId || !telegramApiHash || !telegramPhone) {
            toast.error('Por favor completa todos los campos');
            return;
        }

        setLoading(true);
        try {
            const response = await fetch(`${CONFIG.API_BASE_URL}/telegram/auth/start?user_id=${userId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    phone_number: telegramPhone,
                    api_id: telegramApiId,
                    api_hash: telegramApiHash,
                    force_sms: isForceSMS
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Error al conectar');
            }

            toast.success(isForceSMS ? 'Código enviado por SMS' : 'Código de verificación enviado a tu Telegram');
            setShowCodeModal(true);
            setTimeLeft(120); // 2 minutos
            setModalMessage(null);
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
            const response = await fetch(`${CONFIG.API_BASE_URL}/telegram/auth/verify?user_id=${userId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    code: verificationCode
                })
            });

            if (!response.ok) {
                const error = await response.json();
                // Manejo específico para código expirado
                if (error.detail === "CODE_EXPIRED" || error.message === "CODE_EXPIRED") {
                    toast.warning("El código ha expirado. Se ha enviado uno nuevo automáticamente.");
                    setVerificationCode(''); // Limpiar para que el usuario ingrese el nuevo
                    setTimeLeft(120); // Reiniciar timer
                    setModalMessage({ 
                        type: 'error', 
                        text: 'El código expiró. Se ha enviado uno nuevo por SMS.' 
                    });
                    return;
                }
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
            const response = await fetch(`${CONFIG.API_BASE_URL}/telegram/disconnect?user_id=${userId}`, {
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
                            onClick={() => handleConnect(false)}
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

                        <div className="mb-4 space-y-2">
                            <div className="flex justify-between items-center text-sm">
                                <span className="text-muted-foreground">Expira en:</span>
                                <span className={`font-mono font-bold ${timeLeft < 30 ? 'text-red-500' : 'text-foreground'}`}>
                                    {formatTime(timeLeft)}
                                </span>
                            </div>
                            
                            {modalMessage && (
                                <div className={`p-3 rounded-md text-xs font-medium ${
                                    modalMessage.type === 'error' 
                                        ? 'bg-red-50 text-red-900 border border-red-200 dark:bg-red-900/20 dark:text-red-300' 
                                        : 'bg-blue-50 text-blue-900 border border-blue-200'
                                }`}>
                                    {modalMessage.text}
                                </div>
                            )}
                        </div>

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
                            {timeLeft === 0 && (
                                <Button onClick={() => handleConnect(true)} disabled={loading} variant="secondary">
                                    Reenviar SMS
                                </Button>
                            )}
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
