import React from 'react';
import { TouchableOpacity, Text, ActivityIndicator, TouchableOpacityProps } from 'react-native';

interface ButtonProps extends TouchableOpacityProps {
  title: string;
  variant?: 'primary' | 'secondary' | 'destructive' | 'outline' | 'ghost';
  isLoading?: boolean;
}

export function Button({ title, variant = 'primary', isLoading, className, ...props }: ButtonProps) {
  const baseStyle = "px-4 py-3 rounded-md flex-row justify-center items-center";

  let variantStyle = "";
  let textStyle = "font-bold text-center";

  switch (variant) {
    case 'primary':
      variantStyle = "bg-primary";
      textStyle += " text-primary-foreground";
      break;
    case 'secondary':
      variantStyle = "bg-secondary";
      textStyle += " text-secondary-foreground";
      break;
    case 'destructive':
      variantStyle = "bg-destructive";
      textStyle += " text-destructive-foreground";
      break;
    case 'outline':
      variantStyle = "border border-border bg-transparent";
      textStyle += " text-foreground";
      break;
    case 'ghost':
      variantStyle = "bg-transparent";
      textStyle += " text-foreground";
      break;
  }

  return (
    <TouchableOpacity
      className={`${baseStyle} ${variantStyle} ${className}`}
      disabled={isLoading || props.disabled}
      {...props}
    >
      {isLoading ? (
        <ActivityIndicator color={variant === 'outline' || variant === 'ghost' ? 'white' : 'black'} />
      ) : (
        <Text className={textStyle}>{title}</Text>
      )}
    </TouchableOpacity>
  );
}
