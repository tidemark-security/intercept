/**
 * System Type Icon Mapping
 * 
 * Maps SystemType enum values to their corresponding Lucide icons.
 * Used by both SystemTypeSelector (form) and timeline card rendering.
 */

import type { SystemType } from '@/types/generated/models/SystemType';
import type { LucideIcon } from 'lucide-react';
import {
  Activity,
  Apple,
  Archive,
  ArrowRightLeft,
  ArrowUpRight,
  BarChart3,
  Bot,
  Camera,
  Car,
  CircuitBoard,
  Cpu,
  Database,
  Folder,
  GitBranch,
  Globe,
  HardDrive,
  Heart,
  Home,
  Laptop,
  Lock,
  Mail,
  Monitor,
  Navigation,
  Package,
  Printer,
  Radio,
  Refrigerator,
  Server,
  Settings,
  Shield,
  ShieldCheck,
  Shuffle,
  Smartphone,
  Thermometer,
  Watch,
  Wifi,
  Zap,
} from 'lucide-react';

/**
 * Maps each SystemType to its corresponding icon component.
 * Default fallback is Cpu.
 */
export const SYSTEM_TYPE_ICONS: Record<SystemType, LucideIcon> = {
  // Enterprise: End User
  ENT_WORKSTATION: Monitor,
  ENT_LAPTOP: Laptop,
  
  // Enterprise: Server
  ENT_WEB_SERVER: Globe,
  ENT_DATABASE_SERVER: Database,
  ENT_APPLICATION_SERVER: Package,
  ENT_FILE_SERVER: Folder,
  ENT_MAIL_SERVER: Mail,
  ENT_DNS_SERVER: Navigation,
  ENT_DOMAIN_CONTROLLER: Settings,
  ENT_ROUTER: Wifi,
  ENT_SWITCH: Shuffle,
  ENT_FIREWALL: Shield,
  ENT_LOAD_BALANCER: BarChart3,
  ENT_PROXY_SERVER: ArrowRightLeft,
  ENT_JUMP_HOST: ArrowUpRight,
  ENT_VPN_SERVER: Lock,
  ENT_MAINFRAME: HardDrive,
  ENT_PRINTER: Printer,
  
  // Mobile
  MOBILE_IOS: Apple,
  MOBILE_ANDROID: Bot,
  MOBILE_OTHER: Smartphone,
  
  // ICS: Industrial Control Systems
  ICS_CONTROL_SERVER: Server,
  ICS_HMI: Monitor,
  ICS_PLC: Cpu,
  ICS_RTU: Radio,
  ICS_IED: Zap,
  ICS_DATA_HISTORIAN: Archive,
  ICS_DATA_GATEWAY: GitBranch,
  ICS_SAFETY_CONTROLLER: ShieldCheck,
  ICS_FIELD_IO: Activity,
  
  // IoT: Internet of Things
  IOT_SENSOR: Thermometer,
  IOT_CAMERA: Camera,
  IOT_SMART_HOME: Home,
  IOT_WEARABLE: Watch,
  IOT_VEHICLE: Car,
  IOT_MEDICAL: Heart,
  IOT_APPLIANCE: Refrigerator,
  IOT_GATEWAY: GitBranch,
  IOT_OTHER: CircuitBoard,
  
  // General
  OTHER: Cpu,
};

/**
 * Maps each SystemType to its human-friendly label.
 * Used for display in cards and UI elements.
 */
export const SYSTEM_TYPE_LABELS: Record<SystemType, string> = {
  // Enterprise: End User
  ENT_WORKSTATION: 'Workstation',
  ENT_LAPTOP: 'Laptop',
  
  // Enterprise: Server
  ENT_WEB_SERVER: 'Web Server',
  ENT_DATABASE_SERVER: 'Database Server',
  ENT_APPLICATION_SERVER: 'Application Server',
  ENT_FILE_SERVER: 'File Server',
  ENT_MAIL_SERVER: 'Mail Server',
  ENT_DNS_SERVER: 'DNS Server',
  ENT_DOMAIN_CONTROLLER: 'Domain Controller',
  ENT_ROUTER: 'Router',
  ENT_SWITCH: 'Switch',
  ENT_FIREWALL: 'Firewall',
  ENT_LOAD_BALANCER: 'Load Balancer',
  ENT_PROXY_SERVER: 'Proxy Server',
  ENT_JUMP_HOST: 'Jump Host',
  ENT_VPN_SERVER: 'VPN Server',
  ENT_MAINFRAME: 'Mainframe',
  ENT_PRINTER: 'Printer',
  
  // Mobile
  MOBILE_IOS: 'iOS Mobile',
  MOBILE_ANDROID: 'Android Mobile',
  MOBILE_OTHER: 'Other Mobile',
  
  // ICS: Industrial Control Systems
  ICS_CONTROL_SERVER: 'Control Server',
  ICS_HMI: 'HMI',
  ICS_PLC: 'PLC',
  ICS_RTU: 'RTU',
  ICS_IED: 'IED',
  ICS_DATA_HISTORIAN: 'Data Historian',
  ICS_DATA_GATEWAY: 'Data Gateway',
  ICS_SAFETY_CONTROLLER: 'Safety Controller',
  ICS_FIELD_IO: 'Field IO',
  
  // IoT: Internet of Things
  IOT_SENSOR: 'Sensor',
  IOT_CAMERA: 'Camera',
  IOT_SMART_HOME: 'Smart Home',
  IOT_WEARABLE: 'Wearable',
  IOT_VEHICLE: 'Vehicle',
  IOT_MEDICAL: 'Medical Device',
  IOT_APPLIANCE: 'Appliance',
  IOT_GATEWAY: 'Gateway',
  IOT_OTHER: 'Other IoT',
  
  // General
  OTHER: 'Other/Unknown',
};

/**
 * Get the human-friendly label for a given system type.
 * Falls back to the raw type string for unknown types.
 */
export function getSystemTypeLabel(type: SystemType | null | undefined): string {
  if (!type) return 'Unknown';
  return SYSTEM_TYPE_LABELS[type] ?? type;
}

/**
 * Get the icon component for a given system type.
 * Falls back to Cpu for null, undefined, or unknown types.
 */
export function getSystemTypeIcon(type: SystemType | null | undefined): LucideIcon {
  if (!type) return Cpu;
  return SYSTEM_TYPE_ICONS[type] ?? Cpu;
}
