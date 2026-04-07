/**
 * Validation Service
 * 
 * Fetches validation rules from the backend API and provides
 * client-side validation with in-memory caching and local fallback.
 */

import { ValidationService } from '@/types/generated';

// Types for validation rules
export interface ValidationRule {
  key: string;
  label: string;
  pattern?: string;
  pattern_flags?: number;
  allowed_values?: string[];
  min_value?: number;  // For integer range validation (inclusive)
  max_value?: number;  // For integer range validation (inclusive)
  examples: string[];
  error_message: string;
}

export interface ValidationRulesResponse {
  rules: Record<string, ValidationRule>;
}

export interface ValidationResult {
  valid: boolean;
  error?: string;
}

// Cache configuration
const CACHE_KEY = 'validation_rules_cache';
const CACHE_TTL_MS = 60 * 60 * 1000; // 1 hour

interface CacheEntry {
  rules: Record<string, ValidationRule>;
  timestamp: number;
}

/**
 * Get cached rules from localStorage if not expired
 */
function getCachedRules(): Record<string, ValidationRule> | null {
  try {
    const cached = localStorage.getItem(CACHE_KEY);
    if (!cached) return null;

    const entry: CacheEntry = JSON.parse(cached);
    const now = Date.now();

    // Check if cache is expired
    if (now - entry.timestamp > CACHE_TTL_MS) {
      localStorage.removeItem(CACHE_KEY);
      return null;
    }

    return entry.rules;
  } catch {
    // Invalid cache, clear it
    localStorage.removeItem(CACHE_KEY);
    return null;
  }
}

/**
 * Store rules in localStorage with timestamp
 */
function setCachedRules(rules: Record<string, ValidationRule>): void {
  try {
    const entry: CacheEntry = {
      rules,
      timestamp: Date.now(),
    };
    localStorage.setItem(CACHE_KEY, JSON.stringify(entry));
  } catch {
    // localStorage might be full or unavailable, ignore
    console.warn('Failed to cache validation rules in localStorage');
  }
}

/**
 * Fetch validation rules from the API
 */
async function fetchRulesFromApi(): Promise<Record<string, ValidationRule>> {
  const data = await ValidationService.getValidationRulesApiV1ValidationRulesGet();
  return data.rules;
}

/**
 * In-memory cache for current session (faster than localStorage reads)
 */
let memoryCache: Record<string, ValidationRule> | null = null;
let fetchPromise: Promise<Record<string, ValidationRule>> | null = null;

/**
 * Get validation rules, preferring fresh backend rules.
 * Uses localStorage only as a fallback if the API is unavailable.
 */
export async function getValidationRules(): Promise<Record<string, ValidationRule>> {
  // Check memory cache first (fastest)
  if (memoryCache) {
    return memoryCache;
  }

  // Deduplicate concurrent fetches
  if (fetchPromise) {
    return fetchPromise;
  }

  const cachedRules = getCachedRules();

  // Fetch from API and fall back to cached rules only if the request fails.
  fetchPromise = fetchRulesFromApi()
    .then((rules) => {
      memoryCache = rules;
      setCachedRules(rules);
      fetchPromise = null;
      return rules;
    })
    .catch((error) => {
      fetchPromise = null;
      if (cachedRules) {
        console.warn('Using cached validation rules after API fetch failed:', error);
        memoryCache = cachedRules;
        return cachedRules;
      }
      throw error;
    });

  return fetchPromise;
}

/**
 * Validate a value against a rule
 * 
 * @param key - The validation rule key (e.g., "observable.IP", "network.src_port")
 * @param value - The value to validate
 * @returns ValidationResult with valid=true if valid, or valid=false with error
 */
export async function validateValue(key: string, value: string): Promise<ValidationResult> {
  try {
    const rules = await getValidationRules();
    return validateValueSync(rules, key, value);
  } catch (error) {
    // API failure with no cache - permissive fallback
    console.warn('Validation rules unavailable, skipping validation:', error);
    return { valid: true };
  }
}

/**
 * Synchronous validation using pre-fetched rules
 * Useful when rules are already loaded (e.g., in React hook)
 */
export function validateValueSync(
  rules: Record<string, ValidationRule>,
  key: string,
  value: string
): ValidationResult {
  const rule = rules[key];

  // Unknown rule - pass validation (permissive)
  if (!rule) {
    return { valid: true };
  }

  // Check allowed_values first (for enum-based validation)
  if (rule.allowed_values) {
    if (!rule.allowed_values.includes(value)) {
      return { valid: false, error: rule.error_message };
    }
    return { valid: true };
  }

  // Check integer range (for numeric validation like ports)
  if (rule.min_value !== undefined || rule.max_value !== undefined) {
    const numValue = parseInt(value, 10);
    if (isNaN(numValue)) {
      return { valid: false, error: rule.error_message };
    }
    if (rule.min_value !== undefined && numValue < rule.min_value) {
      return { valid: false, error: rule.error_message };
    }
    if (rule.max_value !== undefined && numValue > rule.max_value) {
      return { valid: false, error: rule.error_message };
    }
    return { valid: true };
  }

  // Check regex pattern
  if (rule.pattern) {
    try {
      // Build regex with flags if specified
      const flags = rule.pattern_flags ? buildFlagsString(rule.pattern_flags) : '';
      const regex = new RegExp(rule.pattern, flags);
      
      if (!regex.test(value)) {
        return { valid: false, error: rule.error_message };
      }
    } catch {
      // Invalid regex in rule - log and pass
      console.error(`Invalid regex pattern for rule ${key}:`, rule.pattern);
      return { valid: true };
    }
  }

  return { valid: true };
}

/**
 * Convert Python regex flags to JavaScript flags string
 * Python re.IGNORECASE = 2
 */
function buildFlagsString(flags: number): string {
  let result = '';
  if (flags & 2) result += 'i'; // re.IGNORECASE
  return result;
}

/**
 * Clear the validation rules cache
 * Useful for testing or forcing a refresh
 */
export function clearValidationCache(): void {
  memoryCache = null;
  localStorage.removeItem(CACHE_KEY);
}

/**
 * Prefetch validation rules in the background
 * Call this early in app initialization to warm the cache
 */
export function prefetchValidationRules(): void {
  getValidationRules().catch((error) => {
    console.warn('Failed to prefetch validation rules:', error);
  });
}
