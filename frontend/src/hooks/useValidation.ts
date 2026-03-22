/**
 * useValidation Hook
 * 
 * React hook for validating form fields against server-defined rules.
 * Rules are fetched once and cached for 1 hour.
 * 
 * Usage:
 * ```tsx
 * const { validate, rules, loading, error } = useValidation();
 * 
 * const result = validate('observable.IP', ipValue);
 * if (!result.valid) {
 *   setError(result.error);
 * }
 * ```
 */

import { useState, useEffect, useCallback } from 'react';
import {
  getValidationRules,
  validateValueSync,
  type ValidationRule,
  type ValidationResult,
} from '@/services/validationService';

interface UseValidationReturn {
  /**
   * Validate a value against a rule (synchronous after rules are loaded)
   */
  validate: (key: string, value: string) => ValidationResult;
  
  /**
   * The loaded validation rules (null while loading)
   */
  rules: Record<string, ValidationRule> | null;
  
  /**
   * Whether rules are currently being fetched
   */
  loading: boolean;
  
  /**
   * Error message if rules failed to load
   */
  error: string | null;
  
  /**
   * Get a specific validation rule by key
   */
  getRule: (key: string) => ValidationRule | undefined;
}

/**
 * Hook for validating form field values against server-defined rules
 */
export function useValidation(): UseValidationReturn {
  const [rules, setRules] = useState<Record<string, ValidationRule> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch rules on mount
  useEffect(() => {
    let cancelled = false;

    getValidationRules()
      .then((fetchedRules) => {
        if (!cancelled) {
          setRules(fetchedRules);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          console.warn('Failed to load validation rules:', err);
          setError(err.message || 'Failed to load validation rules');
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // Validate function - permissive if rules not loaded
  const validate = useCallback(
    (key: string, value: string): ValidationResult => {
      if (!rules) {
        // Rules not loaded yet - permissive fallback
        return { valid: true };
      }
      return validateValueSync(rules, key, value);
    },
    [rules]
  );

  // Get a specific rule
  const getRule = useCallback(
    (key: string): ValidationRule | undefined => {
      return rules?.[key];
    },
    [rules]
  );

  return {
    validate,
    rules,
    loading,
    error,
    getRule,
  };
}

export default useValidation;
