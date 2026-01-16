import React, { useState } from 'react';
import { SignalsKeiLayout } from '@/components/SignalsKeiLayout';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { trpc } from '@/lib/trpc';
import { Eye, EyeOff, Save, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

export default function Settings() {
  const { data: config, isLoading } = trpc.trading.getConfig.useQuery();
  const updateConfigMutation = trpc.trading.updateConfig.useMutation();
  const [showSecrets, setShowSecrets] = useState(false);
  const [availableChannels, setAvailableChannels] = useState<any[]>([]);

  const [formData, setFormData] = useState({
    demoMode: true,
    geminiApiKey: '',
    gmgnApiKey: '',
    telegramBotToken: '',
    telegramChatId: '',
    telegramChannels: { allow: [] as string[], deny: [] as string[] },
    exchanges: [{
      exchangeId: 'binance',
      apiKey: '',
      secret: '',
      password: '',
      uid: '',
      isActive: true
    }],
    dexConfig: {
      walletPrivateKey: '',
      rpcUrl: 'https://api.mainnet-beta.solana.com'
    },
    investmentLimits: {
      cexMaxAmount: 100,
      dexMaxAmount: 1
    }
  });

  React.useEffect(() => {
    if (config) {
      setFormData({
        demoMode: config.demoMode ?? true,
        geminiApiKey: config.geminiApiKey || '',
        gmgnApiKey: config.gmgnApiKey || '',
        telegramBotToken: config.telegramBotToken || '',
        telegramChatId: config.telegramChatId || '',
        telegramChannels: config.telegramChannels || { allow: [], deny: [] },
        exchanges: config.exchanges?.length ? config.exchanges : [{
          exchangeId: 'binance',
          apiKey: '',
          secret: '',
          password: '',
          uid: '',
          isActive: true
        }],
        dexConfig: {
          walletPrivateKey: config.dexConfig?.walletPrivateKey || '',
          rpcUrl: config.dexConfig?.rpcUrl || 'https://api.mainnet-beta.solana.com'
        },
        investmentLimits: {
          cexMaxAmount: config.investmentLimits?.cexMaxAmount ?? 100,
          dexMaxAmount: config.investmentLimits?.dexMaxAmount ?? 1
        }
      });
    }
  }, [config]);

  const handleSave = async () => {
    try {
      await updateConfigMutation.mutateAsync(formData);
      toast.success('Configuración guardada correctamente');
    } catch (error) {
      toast.error('Error al guardar la configuración');
    }
  };

  const addExchange = () => {
    setFormData({
      ...formData,
      exchanges: [...formData.exchanges, {
        exchangeId: 'binance',
        apiKey: '',
        secret: '',
        password: '',
        uid: '',
        isActive: true
      }]
    });
  };

  const removeExchange = (index: number) => {
    const newExchanges = [...formData.exchanges];
    newExchanges.splice(index, 1);
    setFormData({ ...formData, exchanges: newExchanges });
  };

  const updateExchange = (index: number, field: string, value: any) => {
    const newExchanges = [...formData.exchanges];
    (newExchanges[index] as any)[field] = value;
    setFormData({ ...formData, exchanges: newExchanges });
  };

  const InputField = ({ label, value, onChange, type = 'text', placeholder }: any) => (
    <div className="flex-1">
      <label className="block text-xs font-semibold text-foreground mb-1">
        {label}
      </label>
      <div className="relative">
        <input
          type={showSecrets && type === 'password' ? 'text' : type}
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full px-3 py-1.5 border border-border rounded bg-background text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
        />
        {type === 'password' && (
          <button
            onClick={() => setShowSecrets(!showSecrets)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            {showSecrets ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        )}
      </div>
    </div>
  );

  return (
    <SignalsKeiLayout currentPage="/settings">
      <div className="space-y-6 max-w-5xl pb-10">
        <div className="flex justify-between items-center">
          <div>
            <h2 className="text-3xl font-bold text-foreground mb-2">Configuración</h2>
            <p className="text-muted-foreground">Gestiona tus credenciales y límites de inversión</p>
          </div>
          <Button onClick={handleSave} disabled={updateConfigMutation.isPending} className="flex items-center gap-2">
            <Save size={18} />
            {updateConfigMutation.isPending ? 'Guardando...' : 'Guardar Todo'}
          </Button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* AI & API Keys */}
          <div className="space-y-6">
            <Card className="p-6">
              <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">🤖 Inteligencia Artificial</h3>
              <InputField
                label="Gemini API Key"
                value={formData.geminiApiKey}
                onChange={(v: string) => setFormData({ ...formData, geminiApiKey: v })}
                type="password"
              />
            </Card>

            <Card className="p-6">
              <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">📱 Telegram Bot</h3>
              <div className="space-y-4">
                <InputField
                  label="Bot Token"
                  value={formData.telegramBotToken}
                  onChange={(v: string) => setFormData({ ...formData, telegramBotToken: v })}
                  type="password"
                />

                {/* Channel Selection */}
                <div className="pt-2">
                  <div className="flex justify-between items-center mb-2">
                    <label className="block text-xs font-semibold text-foreground">Canales Permitidos</label>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={async () => {
                        try {
                          const res = await fetch('http://localhost:8000/telegram/dialogs');
                          const dialogs = await res.json();
                          if (Array.isArray(dialogs)) {
                            setAvailableChannels(dialogs);
                            toast.success(`Cargados ${dialogs.length} canales`);
                          } else {
                            toast.error("Format de respuesta inválido");
                          }
                        } catch (e) {
                          toast.error("Error cargando canales");
                          console.error(e);
                        }
                      }}
                    >
                      Cargar Canales
                    </Button>
                  </div>

                  {availableChannels.length > 0 && (
                    <div className="max-h-60 overflow-y-auto border border-border rounded p-2 text-sm bg-background space-y-1">
                      {availableChannels.map((channel: any) => (
                        <label key={channel.id} className="flex items-center gap-2 p-1 hover:bg-muted/50 rounded cursor-pointer">
                          <input
                            type="checkbox"
                            checked={formData.telegramChannels.allow.includes(channel.id)}
                            onChange={(e) => {
                              const newAllow = e.target.checked
                                ? [...formData.telegramChannels.allow, channel.id]
                                : formData.telegramChannels.allow.filter(id => id !== channel.id);
                              setFormData({
                                ...formData,
                                telegramChannels: { ...formData.telegramChannels, allow: newAllow }
                              });
                            }}
                            className="rounded border-gray-300 text-primary focus:ring-primary h-4 w-4"
                          />
                          <span className="truncate">{channel.name || "Sin Nombre"} <span className="text-xs text-muted-foreground">({channel.id})</span></span>
                        </label>
                      ))}
                    </div>
                  )}

                  <div className="text-xs text-muted-foreground mt-2 p-2 bg-muted/20 rounded border border-border/50">
                    {formData.telegramChannels.allow.length === 0
                      ? "⚠️ Lista vacía: Se analizarán mensajes de TODOS los canales."
                      : `✅ ${formData.telegramChannels.allow.length} canales seleccionados. El resto será ignorado.`}
                  </div>
                </div>
              </div>
            </Card>

            <Card className="p-6">
              <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">💰 Límites de Inversión</h3>
              <div className="grid grid-cols-2 gap-4">
                <InputField
                  label="Máximo CEX (USDT)"
                  value={formData.investmentLimits.cexMaxAmount}
                  onChange={(v: string) => setFormData({ ...formData, investmentLimits: { ...formData.investmentLimits, cexMaxAmount: parseFloat(v) } })}
                  type="number"
                />
                <InputField
                  label="Máximo DEX (SOL)"
                  value={formData.investmentLimits.dexMaxAmount}
                  onChange={(v: string) => setFormData({ ...formData, investmentLimits: { ...formData.investmentLimits, dexMaxAmount: parseFloat(v) } })}
                  type="number"
                />
              </div>
            </Card>
          </div>

          {/* DEX & General */}
          <div className="space-y-6">
            <Card className="p-6">
              <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">🔄 DEX Config (GMGN)</h3>
              <div className="space-y-4">
                <InputField
                  label="GMGN API Key"
                  value={formData.gmgnApiKey}
                  onChange={(v: string) => setFormData({ ...formData, gmgnApiKey: v })}
                  type="password"
                />
                <InputField
                  label="Wallet Private Key"
                  value={formData.dexConfig.walletPrivateKey}
                  onChange={(v: string) => setFormData({ ...formData, dexConfig: { ...formData.dexConfig, walletPrivateKey: v } })}
                  type="password"
                />
                <InputField
                  label="RPC URL"
                  value={formData.dexConfig.rpcUrl}
                  onChange={(v: string) => setFormData({ ...formData, dexConfig: { ...formData.dexConfig, rpcUrl: v } })}
                />
              </div>
            </Card>

            <Card className="p-6">
              <h3 className="text-lg font-semibold mb-4">⚙️ Modo de Operación</h3>
              <div className="flex items-center gap-4">
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.demoMode}
                    onChange={(e) => setFormData({ ...formData, demoMode: e.target.checked })}
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary/20 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
                  <span className="ml-3 text-sm font-medium text-foreground">Modo Demo (Simulación)</span>
                </label>
              </div>
            </Card>
          </div>
        </div>

        {/* CEX Exchanges */}
        <Card className="p-6">
          <div className="flex justify-between items-center mb-6">
            <h3 className="text-lg font-semibold flex items-center gap-2">💱 Exchanges Centralizados (CEX)</h3>
            <Button onClick={addExchange} variant="outline" size="sm" className="flex items-center gap-1">
              <Plus size={16} /> Añadir Exchange
            </Button>
          </div>

          <div className="space-y-6">
            {formData.exchanges.map((ex, index) => (
              <div key={index} className="p-4 border border-border rounded-lg bg-muted/30 relative">
                <button
                  onClick={() => removeExchange(index)}
                  className="absolute top-4 right-4 text-muted-foreground hover:text-destructive"
                >
                  <Trash2 size={18} />
                </button>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                  <div>
                    <label className="block text-xs font-semibold text-foreground mb-1">Exchange</label>
                    <select
                      value={ex.exchangeId}
                      onChange={(e) => updateExchange(index, 'exchangeId', e.target.value)}
                      className="w-full px-3 py-1.5 border border-border rounded bg-background text-sm text-foreground"
                    >
                      <option value="binance">Binance</option>
                      <option value="okx">OKX</option>
                      <option value="kucoin">KuCoin</option>
                      <option value="bybit">Bybit</option>
                      <option value="gateio">Gate.io</option>
                    </select>
                  </div>
                  <InputField
                    label="API Key"
                    value={ex.apiKey}
                    onChange={(v: string) => updateExchange(index, 'apiKey', v)}
                    type="password"
                  />
                  <InputField
                    label="API Secret"
                    value={ex.secret}
                    onChange={(v: string) => updateExchange(index, 'secret', v)}
                    type="password"
                  />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <InputField
                    label="Passphrase (OKX/KuCoin)"
                    value={ex.password}
                    onChange={(v: string) => updateExchange(index, 'password', v)}
                    type="password"
                  />
                  <InputField
                    label="UID"
                    value={ex.uid}
                    onChange={(v: string) => updateExchange(index, 'uid', v)}
                  />
                  <div className="flex items-end pb-2">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={ex.isActive}
                        onChange={(e) => updateExchange(index, 'isActive', e.target.checked)}
                      />
                      <span className="text-sm">Activo</span>
                    </label>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </SignalsKeiLayout>
  );
}
