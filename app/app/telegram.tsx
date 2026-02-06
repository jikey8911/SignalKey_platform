import React, { useState, useEffect } from 'react';
import { View, Text, ScrollView, FlatList, Alert } from 'react-native';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { useAuth } from '../context/AuthContext';
import { fetchConfig, updateConfig } from '../lib/api';

export default function TelegramScreen() {
  const { user } = useAuth();
  const [config, setConfig] = useState<any>({});
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
     // Fetch logs and config
     fetchConfig().then(c => {
         if (c?.config) setConfig(c.config);
     });
  }, []);

  const handleConnect = async () => {
      setLoading(true);
      try {
          // Update config which triggers connection attempt in backend if supported,
          // or just saves keys. The backend 'login' or specific trigger handles the actual connection.
          // For now, we update the keys.
          await updateConfig({
              ...config,
              telegramIsConnected: true // Hint to backend
          });
          Alert.alert("Success", "Configuration updated. Restart may be required to connect.");
      } catch (e) {
          Alert.alert("Error", "Failed to update configuration");
      } finally {
          setLoading(false);
      }
  };

  return (
    <ScrollView className="flex-1 bg-background p-4">
      <Card className="mb-4">
        <Text className="text-lg font-bold text-foreground mb-4">Telegram Configuration</Text>
        <Input label="API ID" value={String(config.telegramApiId || '')} onChangeText={t => setConfig({...config, telegramApiId: t})} keyboardType="numeric" />
        <Input label="API Hash" value={config.telegramApiHash} onChangeText={t => setConfig({...config, telegramApiHash: t})} />
        <Input label="Phone Number" value={config.telegramPhoneNumber} onChangeText={t => setConfig({...config, telegramPhoneNumber: t})} keyboardType="phone-pad" />

        <Button title="Save & Connect" className="mt-2" onPress={handleConnect} isLoading={loading} />
      </Card>

      <Text className="text-lg font-bold text-foreground mb-2">Logs</Text>
      <View className="bg-card border border-border rounded-lg p-4 h-60">
         <FlatList
           data={logs}
           keyExtractor={(item, index) => index.toString()}
           renderItem={({ item }) => <Text className="text-xs font-mono text-foreground mb-1">{item}</Text>}
           ListEmptyComponent={<Text className="text-muted-foreground text-xs">No logs available.</Text>}
         />
      </View>
    </ScrollView>
  );
}
