import React, { useState, useEffect } from 'react';
import { View, Text, ScrollView, Switch, Alert, TouchableOpacity, TextInput } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../../context/AuthContext';
import { Card } from '../../components/ui/Card';
import { fetchConfig, updateConfig } from '../../lib/api';

export default function SettingsScreen() {
  const { user, signOut } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [config, setConfig] = useState<any>({
    demoMode: true,
    aiProvider: 'gemini',
    geminiApiKey: '',
    openaiApiKey: '',
  });

  useEffect(() => {
    const loadConfig = async () => {
      try {
        const data = await fetchConfig(user?.openId);
        if (data) {
          setConfig({
            demoMode: data.demoMode ?? true,
            aiProvider: data.aiProvider || 'gemini',
            geminiApiKey: data.geminiApiKey || '',
            openaiApiKey: data.openaiApiKey || '',
          });
        }
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    loadConfig();
  }, [user]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateConfig(user?.openId, config);
      Alert.alert("Éxito", "Configuración guardada correctamente");
    } catch (e) {
      Alert.alert("Error", "No se pudo guardar la configuración");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView className="flex-1 bg-background">
      <ScrollView contentContainerStyle={{ padding: 16 }}>
        <View className="flex-row justify-between items-center mb-6">
          <Text className="text-2xl font-black text-white uppercase italic">Ajustes</Text>
          <TouchableOpacity
            onPress={handleSave}
            disabled={saving}
            className="bg-primary px-4 py-2 rounded-lg"
          >
            <Text className="text-white font-bold text-xs">{saving ? 'Guardando...' : 'Guardar'}</Text>
          </TouchableOpacity>
        </View>

        <Card className="mb-6 bg-slate-900 border-gray-800 p-4">
          <Text className="text-xs text-gray-500 uppercase font-bold mb-3">Perfil de Usuario</Text>
          <View className="flex-row items-center gap-3">
            <View className="h-12 w-12 rounded-full bg-slate-800 items-center justify-center border border-gray-700">
              <Text className="text-xl text-white font-bold">{user?.name?.charAt(0)}</Text>
            </View>
            <View>
              <Text className="text-lg text-white font-bold">{user?.name}</Text>
              <Text className="text-xs text-gray-500">{user?.openId}</Text>
            </View>
          </View>
        </Card>

        <Text className="text-xs text-gray-500 uppercase font-bold mb-3 px-1">Inteligencia Artificial</Text>
        <Card className="mb-6 bg-slate-900 border-gray-800 p-4">
          <View className="mb-4">
            <Text className="text-xs text-gray-400 mb-2">Proveedor Primario</Text>
            <View className="flex-row gap-2">
              {['gemini', 'openai'].map((provider) => (
                <TouchableOpacity
                  key={provider}
                  onPress={() => setConfig({ ...config, aiProvider: provider })}
                  className={`flex-1 py-2 rounded-lg border items-center ${config.aiProvider === provider ? 'bg-primary/20 border-primary' : 'bg-slate-800 border-gray-700'}`}
                >
                  <Text className={`text-xs font-bold capitalize ${config.aiProvider === provider ? 'text-primary' : 'text-gray-400'}`}>
                    {provider}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>

          <View className="mb-4">
            <Text className="text-xs text-gray-400 mb-2">Gemini API Key</Text>
            <TextInput
              value={config.geminiApiKey}
              onChangeText={(v) => setConfig({ ...config, geminiApiKey: v })}
              placeholder="AIzaSy..."
              placeholderTextColor="#4b5563"
              secureTextEntry
              className="bg-slate-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm"
            />
          </View>

          <View>
            <Text className="text-xs text-gray-400 mb-2">OpenAI API Key</Text>
            <TextInput
              value={config.openaiApiKey}
              onChangeText={(v) => setConfig({ ...config, openaiApiKey: v })}
              placeholder="sk-..."
              placeholderTextColor="#4b5563"
              secureTextEntry
              className="bg-slate-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm"
            />
          </View>
        </Card>

        <Text className="text-xs text-gray-500 uppercase font-bold mb-3 px-1">Operación</Text>
        <Card className="mb-6 bg-slate-900 border-gray-800 p-4">
          <View className="flex-row justify-between items-center">
            <View>
              <Text className="text-white font-bold">Modo Demo</Text>
              <Text className="text-[10px] text-gray-500 italic">Simular operaciones con balance virtual</Text>
            </View>
            <Switch
              value={config.demoMode}
              onValueChange={(v) => setConfig({ ...config, demoMode: v })}
              trackColor={{ false: '#1e293b', true: '#3b82f6' }}
            />
          </View>
        </Card>

        <TouchableOpacity
          onPress={signOut}
          className="bg-red-500/10 border border-red-500/20 py-4 rounded-xl items-center"
        >
          <Text className="text-red-500 font-bold">Cerrar Sesión</Text>
        </TouchableOpacity>

        <Text className="text-center text-[10px] text-gray-600 mt-8 mb-4">SignalKey Mobile v1.2.0 • Build 2024</Text>
      </ScrollView>
    </SafeAreaView>
  );
}
