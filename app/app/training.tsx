import React, { useState } from 'react';
import { View, Text, ScrollView, Alert } from 'react-native';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { startTraining } from '../lib/api';

export default function TrainingScreen() {
  const [modelName, setModelName] = useState('');
  const [epochs, setEpochs] = useState('100');
  const [batchSize, setBatchSize] = useState('32');
  const [loading, setLoading] = useState(false);

  const handleTrain = async () => {
      if (!modelName) {
          Alert.alert("Error", "Model name is required");
          return;
      }
      setLoading(true);
      try {
          const res = await startTraining({
              modelName,
              epochs: parseInt(epochs),
              batchSize: parseInt(batchSize)
          });
          Alert.alert("Success", res.message || "Training started");
      } catch (e) {
          Alert.alert("Error", "Failed to start training");
      } finally {
          setLoading(false);
      }
  };

  return (
    <ScrollView className="flex-1 bg-background p-4">
      <Card className="mb-4">
        <Text className="text-lg font-bold text-foreground mb-4">Model Training</Text>
        <Text className="text-muted-foreground mb-4">
           Train a new model using historical data. This process may take a while.
        </Text>

        <Input label="Model Name" placeholder="e.g. BTC_V1" value={modelName} onChangeText={setModelName} />
        <Input label="Epochs" placeholder="100" keyboardType="numeric" value={epochs} onChangeText={setEpochs} />
        <Input label="Batch Size" placeholder="32" keyboardType="numeric" value={batchSize} onChangeText={setBatchSize} />

        <Button title="Start Training" className="mt-2" onPress={handleTrain} isLoading={loading} />
      </Card>

      <Text className="text-lg font-bold text-foreground mb-2">Training History</Text>
      <Card>
         <Text className="text-muted-foreground text-center py-4">No models trained yet.</Text>
      </Card>
    </ScrollView>
  );
}
