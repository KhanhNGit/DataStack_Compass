import { useState, useCallback } from 'react';

export interface UserPreferences {
  defaultTimeRange: number;
  sidebarCollapsed: boolean;
  tablePageSize: number;
  preferredSeverityFilter: string;
}

const DEFAULT_PREFERENCES: UserPreferences = {
  defaultTimeRange: 30,
  sidebarCollapsed: false,
  tablePageSize: 20,
  preferredSeverityFilter: 'All',
};

const PREFERENCES_KEY = 'datastack_compass_preferences';

export function usePreferences() {
  const [preferences, setPreferences] = useState<UserPreferences>(() => {
    try {
      const stored = localStorage.getItem(PREFERENCES_KEY);
      if (stored) {
        return { ...DEFAULT_PREFERENCES, ...JSON.parse(stored) };
      }
    } catch (e) {
      console.warn('Failed to load preferences from localStorage', e);
    }
    return DEFAULT_PREFERENCES;
  });

  const updatePreference = useCallback(<K extends keyof UserPreferences>(key: K, value: UserPreferences[K]) => {
    setPreferences((prev) => {
      const next = { ...prev, [key]: value };
      try {
        localStorage.setItem(PREFERENCES_KEY, JSON.stringify(next));
      } catch (e) {
        console.warn('Failed to save preference to localStorage', e);
      }
      return next;
    });
  }, []);

  return { preferences, updatePreference };
}
