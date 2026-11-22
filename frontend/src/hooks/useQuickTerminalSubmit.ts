import { useMutation } from '@tanstack/react-query';
import { v4 as uuidv4 } from 'uuid';
import type { EntityType } from '@/components/forms/QuickTerminal';
import { useTimelineItemCreate } from './useTimelineItemCreate';

interface UseQuickTerminalSubmitParams {
  entityId: number | null;
  entityType: EntityType;
}

interface QuickTerminalNote {
  noteText: string;
  parentItemId?: string;
}

export function useQuickTerminalSubmit({ entityId, entityType }: UseQuickTerminalSubmitParams) {
  const createTimelineItem = useTimelineItemCreate(entityId, {
    context: entityType,
    deleteDraftOnSuccess: false,
  });

  return useMutation({
    retry: false,
    mutationFn: async ({ noteText, parentItemId }: QuickTerminalNote) => {
      if (!entityId) {
        throw new Error(`No ${entityType} selected`);
      }

      const id = uuidv4();
      const { response, itemId } = await createTimelineItem.mutateAsync({
        id,
        type: 'note',
        description: noteText,
        timestamp: new Date().toISOString(),
        parent_id: parentItemId || null,
      });

      return { response, itemId: itemId ?? id };
    },
  });
}
