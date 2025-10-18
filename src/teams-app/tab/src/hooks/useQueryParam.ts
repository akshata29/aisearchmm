import { useEffect, useState } from 'react';

export function useQueryParam(key: string): string | undefined {
  const [value, setValue] = useState<string | undefined>(() => getValue(key));

  useEffect(() => {
    const listener = () => {
      setValue(getValue(key));
    };

    window.addEventListener('popstate', listener);
    return () => window.removeEventListener('popstate', listener);
  }, [key]);

  return value;
}

function getValue(key: string): string | undefined {
  if (typeof window === 'undefined') {
    return undefined;
  }
  const params = new URLSearchParams(window.location.search);
  const raw = params.get(key);
  return raw ? decodeURIComponent(raw) : undefined;
}
