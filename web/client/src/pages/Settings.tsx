import React, { useState } from 'react';
import { SignalsKeiLayout } from '@/components/SignalsKeiLayout';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { trpc } from '@/lib/trpc';
import { Eye, EyeOff, Save } from 'lucide-react';
import { toast } from 'sonner';

export default function Settings() {
  const { data: config, isLoading } = trpc.trading.getConfig.useQuery();
  const updateConfigMutation = trpc.trading.updateConfig.useMutation();
  const [showSecrets, setShowSecrets] = useState(false);
  const [formData, setFormData] = useState({
    geminiApiKey: '',
    gmgnApiKey: '',
    telegramBotToken: '',
    exchangeId: 'binance',
    cexApiKey: '',
    cexSecret: '',
    cexPassword: '',
    cexUid: '',
    dexWalletPrivateKey: '',
  });

  React.useEffect(() => {
    if (config) {
      setFormData({
        geminiApiKey: config.geminiApiKey || '',
        gmgnApiKey: config.gmgnApiKey || '',
        telegramBotToken: config.telegramBotToken || '',
        exchangeId: config.exchangeId || 'binance',
        cexApiKey: config.cexApiKey || '',
        cexSecret: config.cexSecret || '',
        cexPassword: config.cexPassword || '',
        cexUid: config.cexUid || '',
        dexWalletPrivateKey: config.dexWalletPrivateKey || '',
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

  const InputField = ({ label, name, type = 'text', placeholder }: any) => (
    <div>
      <label className="block text-sm font-semibold text-foreground mb-2">
        {label}
      </label>
      <div className="relative">
        <input
          type={showSecrets && type === 'password' ? 'text' : type}
          name={name}
          placeholder={placeholder}
          value={(formData as any)[name]}
          onChange={(e) =>
            setFormData({ ...formData, [name]: e.target.value })
          }
          className="w-full px-4 py-2 border border-border rounded-lg bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
        />
        {type === 'password' && (
          <button
            onClick={() => setShowSecrets(!showSecrets)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            {showSecrets ? <EyeOff size={18} /> : <Eye size={18} />}
          </button>
        )}
      </div>
    </div>
  );

  return (
    <SignalsKeiLayout currentPage="/settings">
      <div className="space-y-6 max-w-4xl">
        <div>
          <h2 className="text-3xl font-bold text-foreground mb-2">Configuración</h2>
          <p className="text-muted-foreground">
            Configura tus API Keys y credenciales de exchanges
          </p>
        </div>

        {isLoading ? (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-20 bg-muted animate-pulse rounded-lg" />
            ))}
          </div>
        ) : (
          <>
            {/* Gemini AI */}
            <Card className="p-6">
              <h3 className="text-lg font-semibold text-foreground mb-4">🤖 Gemini AI</h3>
              <InputField
                label="API Key de Gemini"
                name="geminiApiKey"
                type="password"
                placeholder="Tu API Key de Google Gemini"
              />
              <p className="text-xs text-muted-foreground mt-2">
                Obtén tu API Key en{' '}
                <a
                  href="https://makersuite.google.com/app/apikey"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline"
                >
                  Google AI Studio
                </a>
              </p>
            </Card>

            {/* DEX (GMGN) */}
            <Card className="p-6">
              <h3 className="text-lg font-semibold text-foreground mb-4">🔄 DEX (GMGN)</h3>
              <InputField
                label="API Key de GMGN"
                name="gmgnApiKey"
                type="password"
                placeholder="Tu API Key de GMGN"
              />
              <p className="text-xs text-muted-foreground mt-2">
                Obtén tu API Key en{' '}
                <a
                  href="https://gmgn.ai"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline"
                >
                  GMGN.ai
                </a>
              </p>
            </Card>

            {/* Telegram */}
            <Card className="p-6">
              <h3 className="text-lg font-semibold text-foreground mb-4">📱 Telegram Bot</h3>
              <InputField
                label="Token del Bot de Telegram"
                name="telegramBotToken"
                type="password"
                placeholder="Tu token de bot de Telegram"
              />
              <p className="text-xs text-muted-foreground mt-2">
                Crea un bot con{' '}
                <a
                  href="https://t.me/BotFather"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline"
                >
                  BotFather
                </a>
              </p>
            </Card>

            {/* CEX Configuration */}
            <Card className="p-6">
              <h3 className="text-lg font-semibold text-foreground mb-4">💱 Configuración CEX</h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-semibold text-foreground mb-2">
                    Exchange
                  </label>
                  <select
                    value={formData.exchangeId}
                    onChange={(e) =>
                      setFormData({ ...formData, exchangeId: e.target.value })
                    }
                    className="w-full px-4 py-2 border border-border rounded-lg bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    <option value="binance">Binance</option>
                    <option value="okx">OKX</option>
                    <option value="kucoin">KuCoin</option>
                    <option value="bybit">Bybit</option>
                  </select>
                </div>
                <InputField
                  label="API Key"
                  name="cexApiKey"
                  type="password"
                  placeholder="Tu API Key del exchange"
                />
                <InputField
                  label="API Secret"
                  name="cexSecret"
                  type="password"
                  placeholder="Tu API Secret del exchange"
                />
                <InputField
                  label="Passphrase (si aplica)"
                  name="cexPassword"
                  type="password"
                  placeholder="Passphrase del API (OKX, KuCoin, etc)"
                />
                <InputField
                  label="UID (si aplica)"
                  name="cexUid"
                  type="password"
                  placeholder="UID del API (OKX, etc)"
                />
              </div>
            </Card>

            {/* DEX Wallet */}
            <Card className="p-6">
              <h3 className="text-lg font-semibold text-foreground mb-4">🔐 Wallet DEX</h3>
              <InputField
                label="Private Key de Wallet"
                name="dexWalletPrivateKey"
                type="password"
                placeholder="Tu private key de Solana wallet"
              />
              <p className="text-xs text-muted-foreground mt-2">
                ⚠️ Nunca compartas tu private key. Se almacena de forma segura.
              </p>
            </Card>

            {/* Save Button */}
            <div className="flex gap-4">
              <Button
                onClick={handleSave}
                disabled={updateConfigMutation.isPending}
                className="flex items-center gap-2"
              >
                <Save size={18} />
                {updateConfigMutation.isPending ? 'Guardando...' : 'Guardar Configuración'}
              </Button>
            </div>
          </>
        )}
      </div>
    </SignalsKeiLayout>
  );
}
