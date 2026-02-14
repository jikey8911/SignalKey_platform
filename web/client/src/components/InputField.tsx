import React from 'react';
import { Eye, EyeOff } from 'lucide-react';

export function InputField({
  label,
  value,
  onChange,
  type = 'text',
  placeholder,
  showSecrets = false,
  setShowSecrets,
}: any) {
  const canToggle = type === 'password' && typeof setShowSecrets === 'function';

  return (
    <div className="flex-1">
      <label className="block text-xs font-semibold text-foreground mb-1">
        {label}
      </label>
      <div className="relative">
        <input
          type={canToggle && showSecrets ? 'text' : type}
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full px-3 py-1.5 border border-border rounded bg-background text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
        />
        {canToggle && (
          <button
            type="button"
            onClick={() => setShowSecrets(!showSecrets)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            {showSecrets ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        )}
      </div>
    </div>
  );
}
