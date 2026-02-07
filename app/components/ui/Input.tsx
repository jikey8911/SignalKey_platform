import React from 'react';
import { TextInput, TextInputProps, View, Text } from 'react-native';

interface InputProps extends TextInputProps {
  label?: string;
  error?: string;
}

export function Input({ label, error, className, ...props }: InputProps) {
  return (
    <View className="mb-4">
      {label && <Text className="text-foreground mb-1 font-medium">{label}</Text>}
      <TextInput
        className={`bg-input text-foreground px-3 py-2 rounded-md border border-border ${className}`}
        placeholderTextColor="#64748b"
        {...props}
      />
      {error && <Text className="text-destructive text-sm mt-1">{error}</Text>}
    </View>
  );
}
