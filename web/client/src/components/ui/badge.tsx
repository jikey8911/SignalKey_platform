import React from 'react';

type BadgeVariant = 'default' | 'secondary' | 'destructive' | 'success' | 'outline';

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  children: React.ReactNode;
  variant?: BadgeVariant;
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({ children, variant = 'default', className = '', ...props }) => {
  const variants: Record<BadgeVariant, string> = {
    default: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
    secondary: 'bg-slate-700 text-slate-300 border-white/5',
    destructive: 'bg-red-500/10 text-red-500 border-red-500/20',
    success: 'bg-green-500/10 text-green-500 border-green-500/20',
    outline: 'border-white/10 text-slate-400'
  };

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-bold border uppercase tracking-wider ${variants[variant]} ${className}`} {...props}>
      {children}
    </span>
  );
};
