/**
 * Add TTP Form Component
 * 
 * Rich form for creating MITRE ATT&CK TTP timeline items with autocomplete search.
 * Features:
 * - Real-time MITRE ATT&CK technique search with autocomplete dropdown
 * - Auto-population of technique name, tactics, and URL when selected
 * - Review panel showing selected technique details before saving
 * - Description field for procedure details
 * - Timestamp and tag management
 * 
 * Uses the backend MITRE service for searching the ATT&CK database.
 */

import React, { useState, useEffect, useRef, useCallback } from "react";

import { TextArea } from "@/components/forms/TextArea";
import { TextField } from "@/components/forms/TextField";
import { Badge } from "@/components/data-display/Badge";
import { Button } from "@/components/buttons/Button";
import { TagsManager } from "@/components/forms/TagsManager";
import { DateTimeManager } from "@/components/forms/DateTimeManager";
import MarkdownContent from "@/components/data-display/MarkdownContent";
import { useTimelineForm } from "@/hooks/useTimelineForm";
import { useTimelineFormContext } from "@/contexts/TimelineFormContext";
import { TimelineFormLayout } from "@/components/timeline/TimelineFormLayout";
import { MitreService } from "@/types/generated/services/MitreService";
import type { TTPItem } from '@/types/generated/models/TTPItem';

import { Blocks, ExternalLink, Search, Target, X } from 'lucide-react';
/** Search result from MITRE API */
interface MitreSearchResult {
  attack_id: string;
  name: string;
  object_type: string;
  tactics?: string[];
}

/** Full technique details from MITRE API */
interface MitreTechniqueDetail {
  attack_id: string;
  name: string;
  description?: string;
  url: string;
  tactics: string[];
  is_subtechnique: boolean;
  parent_technique?: string;
}

export interface AddTTPFormProps {
  initialData?: TTPItem;
}

export function AddTTPForm({ initialData }: AddTTPFormProps) {
  const { editMode, onCancel } = useTimelineFormContext();
  const searchInputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  
  // Autocomplete state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<MitreSearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [hasSelectedTechnique, setHasSelectedTechnique] = useState(false);
  const [techniqueDescription, setTechniqueDescription] = useState<string>('');
  const debounceRef = useRef<NodeJS.Timeout | null>(null);
  
  const {
    formState,
    setFormState,
    handleSubmit,
    handleClear,
    isSubmitting,
    initialFlagHighlight,
  } = useTimelineForm<{
    mitreId: string;
    title: string;
    tactic: string;
    technique: string;
    url: string;
    description: string;
    timestamp: string;
    tags: string[];
  }, TTPItem>({
    initialData,
    defaultState: {
      mitreId: '',
      title: '',
      tactic: '',
      technique: '',
      url: '',
      description: '',
      timestamp: '',
      tags: [],
    },
    transformInitialData: (data) => ({
      mitreId: data.mitre_id || '',
      title: data.title || '',
      tactic: data.tactic || '',
      technique: data.technique || '',
      url: data.url || '',
      description: data.description || '',
      timestamp: data.timestamp || '',
      tags: data.tags || [],
    }),
    buildPayload: (state) => ({
      mitre_id: state.mitreId || undefined,
      title: state.title || undefined,
      tactic: state.tactic || undefined,
      technique: state.technique || undefined,
      url: state.url || undefined,
      description: state.description || undefined,
      timestamp: state.timestamp || undefined,
      tags: state.tags.length > 0 ? state.tags : undefined,
    }),
  });

  // Initialize search query from initial data
  useEffect(() => {
    if (initialData?.mitre_id) {
      setSearchQuery(initialData.mitre_id);
      setHasSelectedTechnique(true);
      // Pre-populate the MITRE description if available (enriched on read)
      if (initialData.mitre_description) {
        setTechniqueDescription(initialData.mitre_description);
      }
    }
  }, [initialData]);

  // Debounced search function
  const performSearch = useCallback(async (query: string) => {
    if (!query || query.length < 2) {
      setSearchResults([]);
      setShowDropdown(false);
      return;
    }

    setIsSearching(true);
    try {
      const response = await MitreService.searchAttackObjectsApiV1MitreSearchGet({
        q: query,
        types: ['technique'],
        limit: 10,
      });
      
      const results = response?.results || [];
      setSearchResults(results);
      setShowDropdown(results.length > 0);
      setSelectedIndex(0);
    } catch (error) {
      console.error('MITRE search failed:', error);
      setSearchResults([]);
    } finally {
      setIsSearching(false);
    }
  }, []);

  // Handle search input changes with debounce
  const handleSearchChange = useCallback((value: string) => {
    setSearchQuery(value);
    setHasSelectedTechnique(false);
    
    // Clear previous debounce timer
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    
    // Debounce search
    debounceRef.current = setTimeout(() => {
      performSearch(value);
    }, 300);
  }, [performSearch]);

  // Fetch full technique details and populate form
  const selectTechnique = useCallback(async (result: MitreSearchResult) => {
    setShowDropdown(false);
    setSearchQuery(`${result.attack_id} - ${result.name}`);
    setHasSelectedTechnique(true);
    
    // Immediately set what we have from search results
    setFormState(prev => ({
      ...prev,
      mitreId: result.attack_id,
      title: result.name,
      tactic: result.tactics?.join(', ') || '',
    }));

    // Fetch full details for URL and more info
    try {
      const details = await MitreService.getTechniqueApiV1MitreTechniquesAttackIdGet({
        attackId: result.attack_id,
      }) as MitreTechniqueDetail;
      
      if (details) {
        setFormState(prev => ({
          ...prev,
          url: details.url || '',
          tactic: details.tactics?.join(', ') || prev.tactic,
        }));
        setTechniqueDescription(details.description || '');
      }
    } catch (error) {
      console.error('Failed to fetch technique details:', error);
      // Build URL manually as fallback
      const url = result.attack_id.includes('.')
        ? `https://attack.mitre.org/techniques/${result.attack_id.split('.')[0]}/${result.attack_id.split('.')[1]}`
        : `https://attack.mitre.org/techniques/${result.attack_id}`;
      setFormState(prev => ({ ...prev, url }));
    }
  }, [setFormState]);

  // Handle keyboard navigation in dropdown
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (!showDropdown || searchResults.length === 0) {
      if (e.key === 'Enter') {
        e.preventDefault();
      }
      return;
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedIndex(prev => 
          prev < searchResults.length - 1 ? prev + 1 : 0
        );
        break;
      case 'ArrowUp':
        e.preventDefault();
        setSelectedIndex(prev => 
          prev > 0 ? prev - 1 : searchResults.length - 1
        );
        break;
      case 'Enter':
        e.preventDefault();
        if (searchResults[selectedIndex]) {
          selectTechnique(searchResults[selectedIndex]);
        }
        break;
      case 'Escape':
        e.preventDefault();
        setShowDropdown(false);
        break;
    }
  }, [showDropdown, searchResults, selectedIndex, selectTechnique]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    };
    
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Auto-focus search input when form appears (but not in edit mode)
  useEffect(() => {
    if (!editMode) {
      const timer = setTimeout(() => {
        searchInputRef.current?.focus();
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [editMode]);

  // Clear selection
  const clearSelection = useCallback(() => {
    setSearchQuery('');
    setHasSelectedTechnique(false);
    setTechniqueDescription('');
    setFormState(prev => ({
      ...prev,
      mitreId: '',
      title: '',
      tactic: '',
      url: '',
    }));
    searchInputRef.current?.focus();
  }, [setFormState]);

  // Determine if form is valid - requires a technique to be selected
  const isValid = hasSelectedTechnique && formState.mitreId.trim();

  return (
    <TimelineFormLayout
      icon={<Blocks className="text-neutral-600" />}
      title={editMode ? "Edit MITRE ATT&CK® Technique" : "Add MITRE ATT&CK® Technique"}
      onSubmit={handleSubmit}
      onCancel={onCancel}
      onClear={editMode ? undefined : handleClear}
      submitLabel={editMode ? "Update TTP" : "Add TTP"}
      submitDisabled={!isValid}
      isSubmitting={isSubmitting}
      useWell={false}
      editMode={editMode}
      initialFlagHighlight={initialFlagHighlight}
    >
      {/* Search / Select Section */}
      <div className="flex w-full flex-col items-start gap-4 rounded-md border border-solid border-neutral-border bg-neutral-50 px-4 py-4">
        <div className="flex w-full items-center gap-2">
          <span className="text-caption-bold text-default-font">
            Technique
          </span>
        </div>

        {/* Search Input with Autocomplete */}
        <div className="relative w-full h-10" ref={dropdownRef}>
          <TextField
            className="h-full w-full flex-none"
            label=""
            helpText={hasSelectedTechnique ? '' : 'Search by technique ID (T1059) or name (PowerShell)'}
            icon={isSearching ? undefined : <Search className="text-subtext-color" />}
          >
            <TextField.Input
              ref={searchInputRef}
              placeholder="Search MITRE ATT&CK techniques..."
              value={searchQuery}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleSearchChange(e.target.value)}
              onKeyDown={handleKeyDown}
              onFocus={() => {
                if (searchResults.length > 0 && !hasSelectedTechnique) {
                  setShowDropdown(true);
                }
              }}
            />
          </TextField>
          
          {/* Clear button when technique is selected */}
          {hasSelectedTechnique && (
            <Button
              variant="neutral-tertiary"
              size="small"
              onClick={clearSelection}
              className="absolute right-1 top-1"
              aria-label="Clear selection"
              icon={<X />}
            />
          )}
          
          {/* Loading indicator */}
          {isSearching && (
            <div className="absolute right-2 top-2">
              <div className="w-4 h-4 border-2 border-brand-primary border-t-transparent rounded-full animate-spin" />
            </div>
          )}

          {/* Autocomplete Dropdown */}
          {showDropdown && searchResults.length > 0 && (
            <div className="absolute top-full left-0 right-0 mt-1 max-h-64 overflow-y-auto rounded-md border border-solid border-neutral-border bg-default-background z-50">
              {searchResults.map((result, index) => (
                <button
                  key={result.attack_id}
                  type="button"
                  onClick={() => selectTechnique(result)}
                  className={`flex w-full items-start gap-3 px-4 py-3 text-left transition-colors border-b border-neutral-100 last:border-b-0 ${
                    index === selectedIndex
                      ? 'bg-neutral-200'
                      : 'hover:bg-neutral-50'
                  }`}
                >
                  <div className="flex flex-col items-start gap-1 flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <Badge variant="neutral">
                        {result.attack_id}
                      </Badge>
                      <span className="text-body-bold font-body-bold text-default-font truncate">
                        {result.name}
                      </span>
                    </div>
                    {result.tactics && result.tactics.length > 0 && (
                      <span className="text-caption font-caption text-subtext-color">
                        {result.tactics.join(' • ')}
                      </span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

      </div>

      {/* Review Details Well - shown when technique is selected */}
      {hasSelectedTechnique && formState.mitreId && (
        <div className="flex w-full flex-col items-start gap-4 rounded-md border border-solid border-brand-primary bg-default-background px-4 py-4">
          <div className="flex w-full flex-col gap-3">
            {/* Technique ID and Name */}
            <div className="flex items-center gap-3">
              <Badge variant="neutral">{formState.mitreId}</Badge>
              <span className="text-body-bold font-body-bold text-default-font">
              {formState.title}
              </span>
            </div>
            
            {/* Tactics */}
            {formState.tactic && (
              <div className="flex flex-col gap-1">
                <span className="text-caption-bold font-caption-bold text-subtext-color">
                  Tactics
                </span>
                <div className="flex flex-wrap gap-1">
                  {formState.tactic.split(', ').map((tactic, i) => (
                    <Badge key={i} variant="neutral">
                      {tactic}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
            
            {/* Technique Description */}
            {techniqueDescription && (
              <div className="flex flex-col gap-1">
                <span className="text-caption-bold font-caption-bold text-subtext-color">
                  Description
                </span>
                <div className="line-clamp-6">
                  <MarkdownContent content={techniqueDescription} className="text-caption text-default-font" />
                </div>
              </div>
            )}
            
            {/* Reference Link */}
            {formState.url && (
              <div className="flex flex-col gap-1">
                <span className="text-caption-bold font-caption-bold text-subtext-color">
                  Reference
                </span>
                <a
                  href={formState.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-caption text-brand-primary hover:underline"
                >
                  <ExternalLink className="w-4 h-4" />
                  View on MITRE ATT&CK
                </a>
              </div>
            )}

            {/* Copyright Notice */}
            {techniqueDescription && (
              <div className="text-caption text-subtext-color">
                © 2025 The MITRE Corporation. This work is reproduced and distributed with the permission of The MITRE Corporation.
              </div>
            )}
          </div>
        </div>
      )}

      {/* Description Section */}
      <div className="flex w-full flex-col items-start gap-4 rounded-md border border-solid border-neutral-border bg-default-background px-4 py-4">
        <TextArea
          className="h-auto w-full flex-none"
          label="Procedure Description"
          helpText="Describe how this technique was observed or used in this incident"
        >
          <TextArea.Input
            className="h-32 w-full flex-none resize-none"
            placeholder="e.g., Attacker used PowerShell Invoke-WebRequest to download second-stage payload from C2 server..."
            value={formState.description}
            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => 
              setFormState({ ...formState, description: e.target.value })
            }
          />
        </TextArea>

        <DateTimeManager
          value={formState.timestamp}
          onChange={(timestamp) => setFormState({ ...formState, timestamp })}
          label="Observed Timestamp"
          helpText="When this TTP was observed"
          showNowButton={true}
        />
        
        <TagsManager
          tags={formState.tags}
          onTagsChange={(tags) => setFormState({ ...formState, tags })}
          label="Tags"
          placeholder="Enter tags and press Enter"
        />
      </div>
    </TimelineFormLayout>
  );
}
