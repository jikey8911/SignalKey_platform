import React from 'react';
import { View, ViewProps, Text } from 'react-native';

interface CardProps extends ViewProps {
  title?: string;
  description?: string;
}

export function Card({ title, description, children, className, ...props }: CardProps) {
  return (
    <View className={`bg-card rounded-lg border border-border p-4 shadow-sm ${className}`} {...props}>
      {(title || description) && (
        <View className="mb-4">
          {title && <Text className="text-lg font-semibold text-card-foreground">{title}</Text>}
          {description && <Text className="text-sm text-muted-foreground">{description}</Text>}
        </View>
      )}
      {children}
    </View>
  );
}
