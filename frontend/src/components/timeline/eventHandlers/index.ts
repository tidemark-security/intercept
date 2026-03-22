/**
 * Event Handlers Index
 * 
 * Central export point for all timeline item handlers.
 * Automatically registers all handlers with the factory.
 */

import { registerHandler } from '../TimelineCardFactory';

// Import all handlers
import { handleNoteItem } from './noteHandler';
import { handleTaskItem } from './taskHandler';
import { handleObservableItem } from './observableHandler';
import { handleTTPItem } from './ttpHandler';
import { handleSystemItem } from './systemHandler';
import {
  handleInternalActorItem,
  handleExternalActorItem,
  handleThreatActorItem,
} from './actorHandlers';
import { handleAttachmentItem } from './attachmentHandler';
import { handleEmailItem } from './emailHandler';
import { handleLinkItem } from './linkHandler';
import { handleForensicArtifactItem } from './forensicArtifactHandler';
import { handleAlertItem } from './alertHandler';
import { handleCaseItem } from './caseHandler';
import { handleNetworkTrafficItem } from './networkTrafficHandler';
import { handleProcessItem } from './processHandler';
import { handleRegistryChangeItem } from './registryChangeHandler';

// Register all handlers
registerHandler('note', handleNoteItem);
registerHandler('task', handleTaskItem);
registerHandler('observable', handleObservableItem);
registerHandler('ttp', handleTTPItem);
registerHandler('system', handleSystemItem);
registerHandler('internal_actor', handleInternalActorItem);
registerHandler('external_actor', handleExternalActorItem);
registerHandler('threat_actor', handleThreatActorItem);
registerHandler('attachment', handleAttachmentItem);
registerHandler('email', handleEmailItem);
registerHandler('link', handleLinkItem);
registerHandler('forensic_artifact', handleForensicArtifactItem);
registerHandler('alert', handleAlertItem);
registerHandler('case', handleCaseItem);
registerHandler('network_traffic', handleNetworkTrafficItem);
registerHandler('process', handleProcessItem);
registerHandler('registry_change', handleRegistryChangeItem);

// Export all handlers for testing and direct use
export {
  handleNoteItem,
  handleTaskItem,
  handleObservableItem,
  handleTTPItem,
  handleSystemItem,
  handleInternalActorItem,
  handleExternalActorItem,
  handleThreatActorItem,
  handleAttachmentItem,
  handleEmailItem,
  handleLinkItem,
  handleForensicArtifactItem,
  handleAlertItem,
  handleCaseItem,
  handleNetworkTrafficItem,
  handleProcessItem,
  handleRegistryChangeItem,
};

// Export type guards
export {
  isNoteItem,
} from './noteHandler';

export {
  isTaskItem,
} from './taskHandler';

export {
  isObservableItem,
} from './observableHandler';

export {
  isTTPItem,
} from './ttpHandler';

export {
  isSystemItem,
} from './systemHandler';

export {
  isInternalActorItem,
  isExternalActorItem,
  isThreatActorItem,
} from './actorHandlers';

export {
  isAttachmentItem,
} from './attachmentHandler';

export {
  isEmailItem,
} from './emailHandler';

export {
  isLinkItem,
} from './linkHandler';

export {
  isForensicArtifactItem,
} from './forensicArtifactHandler';

export {
  isAlertItem,
} from './alertHandler';

export {
  isCaseItem,
} from './caseHandler';

export {
  isNetworkTrafficItem,
} from './networkTrafficHandler';

export {
  isProcessItem,
} from './processHandler';

export {
  isRegistryChangeItem,
} from './registryChangeHandler';
