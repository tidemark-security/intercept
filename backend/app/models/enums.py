from enum import Enum


class CaseStatus(str, Enum):
    NEW = "NEW"
    IN_PROGRESS = "IN_PROGRESS"
    CLOSED = "CLOSED"


class Priority(str, Enum):
    INFO = "INFO" #P5
    LOW = "LOW" #P4
    MEDIUM = "MEDIUM" #P3
    HIGH = "HIGH" #P2
    CRITICAL = "CRITICAL" #P1
    EXTREME = "EXTREME" #P0
    

class AlertStatus(str, Enum):
    NEW = "NEW" # Awaiting triage
    IN_PROGRESS = "IN_PROGRESS" # Under investigation
    ESCALATED = "ESCALATED" # Linked to a case. When a case is closed, this needs to cascade to a closed status.
    CLOSED_TP = "CLOSED_TP" # Closed as true positive
    CLOSED_BP = "CLOSED_BP" # Closed as benign positive
    CLOSED_FP = "CLOSED_FP" # Closed as false positive
    CLOSED_UNRESOLVED = "CLOSED_UNRESOLVED" # Closed without resolution
    CLOSED_DUPLICATE = "CLOSED_DUPLICATE" # Closed as duplicate of another alert


class ObservableType(str, Enum):
    IP = "IP"
    DOMAIN = "DOMAIN"
    HASH = "HASH"
    FILENAME = "FILENAME"
    URL = "URL"
    EMAIL = "EMAIL"
    REGISTRY_KEY = "REGISTRY_KEY"
    PROCESS_NAME = "PROCESS_NAME"


class TaskStatus(str, Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"


class ActorType(str, Enum):
    INTERNAL = "INTERNAL"
    EXTERNAL = "EXTERNAL"
    EXTERNAL_THREAT = "EXTERNAL_THREAT"


class SystemType(str, Enum):
    """System type classifications aligned with MITRE ATT&CK frameworks."""
    
    # Enterprise systems
    ENT_WORKSTATION = "ENT_WORKSTATION"
    ENT_LAPTOP = "ENT_LAPTOP"
    ENT_WEB_SERVER = "ENT_WEB_SERVER"
    ENT_DATABASE_SERVER = "ENT_DATABASE_SERVER"
    ENT_APPLICATION_SERVER = "ENT_APPLICATION_SERVER"
    ENT_FILE_SERVER = "ENT_FILE_SERVER"
    ENT_MAIL_SERVER = "ENT_MAIL_SERVER"
    ENT_DNS_SERVER = "ENT_DNS_SERVER"
    ENT_DOMAIN_CONTROLLER = "ENT_DOMAIN_CONTROLLER"
    ENT_ROUTER = "ENT_ROUTER"
    ENT_SWITCH = "ENT_SWITCH"
    ENT_FIREWALL = "ENT_FIREWALL"
    ENT_LOAD_BALANCER = "ENT_LOAD_BALANCER"
    ENT_PROXY_SERVER = "ENT_PROXY_SERVER"
    ENT_JUMP_HOST = "ENT_JUMP_HOST"
    ENT_VPN_SERVER = "ENT_VPN_SERVER"
    ENT_MAINFRAME = "ENT_MAINFRAME"
    ENT_PRINTER = "ENT_PRINTER"
    
    # Mobile systems
    MOBILE_IOS = "MOBILE_IOS"
    MOBILE_ANDROID = "MOBILE_ANDROID"
    MOBILE_OTHER = "MOBILE_OTHER"
    
    # ICS/OT systems (from MITRE ATT&CK ICS)
    ICS_CONTROL_SERVER = "ICS_CONTROL_SERVER"
    ICS_HMI = "ICS_HMI"  # Human-Machine Interface
    ICS_PLC = "ICS_PLC"  # Programmable Logic Controller
    ICS_RTU = "ICS_RTU"  # Remote Terminal Unit
    ICS_IED = "ICS_IED"  # Intelligent Electronic Device
    ICS_DATA_HISTORIAN = "ICS_DATA_HISTORIAN"
    ICS_DATA_GATEWAY = "ICS_DATA_GATEWAY"
    ICS_SAFETY_CONTROLLER = "ICS_SAFETY_CONTROLLER"
    ICS_FIELD_IO = "ICS_FIELD_IO"
    
    # IoT systems
    IOT_SENSOR = "IOT_SENSOR"  # Temperature, humidity, motion, etc.
    IOT_CAMERA = "IOT_CAMERA"  # Security cameras, webcams
    IOT_SMART_HOME = "IOT_SMART_HOME"  # Smart thermostats, lights, locks
    IOT_WEARABLE = "IOT_WEARABLE"  # Fitness trackers, smartwatches
    IOT_VEHICLE = "IOT_VEHICLE"  # Connected cars, fleet trackers
    IOT_MEDICAL = "IOT_MEDICAL"  # Patient monitors, insulin pumps
    IOT_APPLIANCE = "IOT_APPLIANCE"  # Smart fridges, washing machines
    IOT_GATEWAY = "IOT_GATEWAY"  # IoT hubs, edge gateways
    IOT_OTHER = "IOT_OTHER"
    
    # General/Other
    OTHER = "OTHER"

class RealtimeEventType(str, Enum):
    """Event types for WebSocket real-time notifications."""
    TIMELINE_ITEM_ADDED = "timeline_item_added"
    TIMELINE_ITEM_UPDATED = "timeline_item_updated"
    TIMELINE_ITEM_DELETED = "timeline_item_deleted"
    TIMELINE_GRAPH_UPDATED = "timeline_graph_updated"
    ENTITY_UPDATED = "entity_updated"
    TRIAGE_COMPLETED = "triage_completed"


class Protocol(str, Enum):
    """Internet Protocol Numbers from IANA registry."""
    
    # 0-9
    HOPOPT = "HOPOPT"  # 0 - IPv6 Hop-by-Hop Option
    ICMP = "ICMP"  # 1 - Internet Control Message
    IGMP = "IGMP"  # 2 - Internet Group Management
    GGP = "GGP"  # 3 - Gateway-to-Gateway
    IPV4 = "IPV4"  # 4 - IPv4 encapsulation
    ST = "ST"  # 5 - Stream
    TCP = "TCP"  # 6 - Transmission Control
    CBT = "CBT"  # 7 - CBT
    EGP = "EGP"  # 8 - Exterior Gateway Protocol
    IGP = "IGP"  # 9 - any private interior gateway (used by Cisco for their IGRP)
    
    # 10-19
    BBN_RCC_MON = "BBN_RCC_MON"  # 10 - BBN RCC Monitoring
    NVP_II = "NVP_II"  # 11 - Network Voice Protocol
    PUP = "PUP"  # 12 - PUP
    ARGUS = "ARGUS"  # 13 - ARGUS (deprecated)
    EMCON = "EMCON"  # 14 - EMCON
    XNET = "XNET"  # 15 - Cross Net Debugger
    CHAOS = "CHAOS"  # 16 - Chaos
    UDP = "UDP"  # 17 - User Datagram
    MUX = "MUX"  # 18 - Multiplexing
    DCN_MEAS = "DCN_MEAS"  # 19 - DCN Measurement Subsystems
    
    # 20-29
    HMP = "HMP"  # 20 - Host Monitoring
    PRM = "PRM"  # 21 - Packet Radio Measurement
    XNS_IDP = "XNS_IDP"  # 22 - XEROX NS IDP
    TRUNK_1 = "TRUNK_1"  # 23 - Trunk-1
    TRUNK_2 = "TRUNK_2"  # 24 - Trunk-2
    LEAF_1 = "LEAF_1"  # 25 - Leaf-1
    LEAF_2 = "LEAF_2"  # 26 - Leaf-2
    RDP = "RDP"  # 27 - Reliable Data Protocol
    IRTP = "IRTP"  # 28 - Internet Reliable Transaction
    ISO_TP4 = "ISO_TP4"  # 29 - ISO Transport Protocol Class 4
    
    # 30-39
    NETBLT = "NETBLT"  # 30 - Bulk Data Transfer Protocol
    MFE_NSP = "MFE_NSP"  # 31 - MFE Network Services Protocol
    MERIT_INP = "MERIT_INP"  # 32 - MERIT Internodal Protocol
    DCCP = "DCCP"  # 33 - Datagram Congestion Control Protocol
    PC3 = "3PC"  # 34 - Third Party Connect Protocol
    IDPR = "IDPR"  # 35 - Inter-Domain Policy Routing Protocol
    XTP = "XTP"  # 36 - XTP
    DDP = "DDP"  # 37 - Datagram Delivery Protocol
    IDPR_CMTP = "IDPR_CMTP"  # 38 - IDPR Control Message Transport Proto
    TP_PLUS_PLUS = "TP_PLUS_PLUS"  # 39 - TP++ Transport Protocol
    
    # 40-49
    IL = "IL"  # 40 - IL Transport Protocol
    IPV6 = "IPV6"  # 41 - IPv6 encapsulation
    SDRP = "SDRP"  # 42 - Source Demand Routing Protocol
    IPV6_ROUTE = "IPV6_ROUTE"  # 43 - Routing Header for IPv6
    IPV6_FRAG = "IPV6_FRAG"  # 44 - Fragment Header for IPv6
    IDRP = "IDRP"  # 45 - Inter-Domain Routing Protocol
    RSVP = "RSVP"  # 46 - Reservation Protocol
    GRE = "GRE"  # 47 - Generic Routing Encapsulation
    DSR = "DSR"  # 48 - Dynamic Source Routing Protocol
    BNA = "BNA"  # 49 - BNA
    
    # 50-59
    ESP = "ESP"  # 50 - Encap Security Payload
    AH = "AH"  # 51 - Authentication Header
    I_NLSP = "I_NLSP"  # 52 - Integrated Net Layer Security TUBA
    SWIPE = "SWIPE"  # 53 - IP with Encryption (deprecated)
    NARP = "NARP"  # 54 - NBMA Address Resolution Protocol
    MIN_IPV4 = "MIN_IPV4"  # 55 - Minimal IPv4 Encapsulation
    TLSP = "TLSP"  # 56 - Transport Layer Security Protocol using Kryptonet key management
    SKIP = "SKIP"  # 57 - SKIP
    IPV6_ICMP = "IPV6_ICMP"  # 58 - ICMP for IPv6
    IPV6_NONXT = "IPV6_NONXT"  # 59 - No Next Header for IPv6
    
    # 60-69
    IPV6_OPTS = "IPV6_OPTS"  # 60 - Destination Options for IPv6
    HOST_INTERNAL = "HOST_INTERNAL"  # 61 - any host internal protocol
    CFTP = "CFTP"  # 62 - CFTP
    LOCAL_NETWORK = "LOCAL_NETWORK"  # 63 - any local network
    SAT_EXPAK = "SAT_EXPAK"  # 64 - SATNET and Backroom EXPAK
    KRYPTOLAN = "KRYPTOLAN"  # 65 - Kryptolan
    RVD = "RVD"  # 66 - MIT Remote Virtual Disk Protocol
    IPPC = "IPPC"  # 67 - Internet Pluribus Packet Core
    DISTRIBUTED_FS = "DISTRIBUTED_FS"  # 68 - any distributed file system
    SAT_MON = "SAT_MON"  # 69 - SATNET Monitoring
    
    # 70-79
    VISA = "VISA"  # 70 - VISA Protocol
    IPCV = "IPCV"  # 71 - Internet Packet Core Utility
    CPNX = "CPNX"  # 72 - Computer Protocol Network Executive
    CPHB = "CPHB"  # 73 - Computer Protocol Heart Beat
    WSN = "WSN"  # 74 - Wang Span Network
    PVP = "PVP"  # 75 - Packet Video Protocol
    BR_SAT_MON = "BR_SAT_MON"  # 76 - Backroom SATNET Monitoring
    SUN_ND = "SUN_ND"  # 77 - SUN ND PROTOCOL-Temporary
    WB_MON = "WB_MON"  # 78 - WIDEBAND Monitoring
    WB_EXPAK = "WB_EXPAK"  # 79 - WIDEBAND EXPAK
    
    # 80-89
    ISO_IP = "ISO_IP"  # 80 - ISO Internet Protocol
    VMTP = "VMTP"  # 81 - VMTP
    SECURE_VMTP = "SECURE_VMTP"  # 82 - SECURE-VMTP
    VINES = "VINES"  # 83 - VINES
    IPTM = "IPTM"  # 84 - Internet Protocol Traffic Manager
    NSFNET_IGP = "NSFNET_IGP"  # 85 - NSFNET-IGP
    DGP = "DGP"  # 86 - Dissimilar Gateway Protocol
    TCF = "TCF"  # 87 - TCF
    EIGRP = "EIGRP"  # 88 - EIGRP
    OSPFIGP = "OSPFIGP"  # 89 - OSPFIGP
    
    # 90-99
    SPRITE_RPC = "SPRITE_RPC"  # 90 - Sprite RPC Protocol
    LARP = "LARP"  # 91 - Locus Address Resolution Protocol
    MTP = "MTP"  # 92 - Multicast Transport Protocol
    AX25 = "AX25"  # 93 - AX.25 Frames
    IPIP = "IPIP"  # 94 - IP-within-IP Encapsulation Protocol
    MICP = "MICP"  # 95 - Mobile Internetworking Control Pro. (deprecated)
    SCC_SP = "SCC_SP"  # 96 - Semaphore Communications Sec. Pro.
    ETHERIP = "ETHERIP"  # 97 - Ethernet-within-IP Encapsulation
    ENCAP = "ENCAP"  # 98 - Encapsulation Header
    PRIVATE_ENCRYPTION = "PRIVATE_ENCRYPTION"  # 99 - any private encryption scheme
    
    # 100-109
    GMTP = "GMTP"  # 100 - GMTP
    IFMP = "IFMP"  # 101 - Ipsilon Flow Management Protocol
    PNNI = "PNNI"  # 102 - PNNI over IP
    PIM = "PIM"  # 103 - Protocol Independent Multicast
    ARIS = "ARIS"  # 104 - ARIS
    SCPS = "SCPS"  # 105 - SCPS
    QNX = "QNX"  # 106 - QNX
    A_N = "A_N"  # 107 - Active Networks
    IPCOMP = "IPCOMP"  # 108 - IP Payload Compression Protocol
    SNP = "SNP"  # 109 - Sitara Networks Protocol
    
    # 110-119
    COMPAQ_PEER = "COMPAQ_PEER"  # 110 - Compaq Peer Protocol
    IPX_IN_IP = "IPX_IN_IP"  # 111 - IPX in IP
    VRRP = "VRRP"  # 112 - Virtual Router Redundancy Protocol
    PGM = "PGM"  # 113 - PGM Reliable Transport Protocol
    ZERO_HOP = "ZERO_HOP"  # 114 - any 0-hop protocol
    L2TP = "L2TP"  # 115 - Layer Two Tunneling Protocol
    DDX = "DDX"  # 116 - D-II Data Exchange (DDX)
    IATP = "IATP"  # 117 - Interactive Agent Transfer Protocol
    STP = "STP"  # 118 - Schedule Transfer Protocol
    SRP = "SRP"  # 119 - SpectraLink Radio Protocol
    
    # 120-129
    UTI = "UTI"  # 120 - UTI
    SMP = "SMP"  # 121 - Simple Message Protocol
    SM = "SM"  # 122 - Simple Multicast Protocol (deprecated)
    PTP = "PTP"  # 123 - Performance Transparency Protocol
    ISIS_OVER_IPV4 = "ISIS_OVER_IPV4"  # 124 - ISIS over IPv4
    FIRE = "FIRE"  # 125 - FIRE
    CRTP = "CRTP"  # 126 - Combat Radio Transport Protocol
    CRUDP = "CRUDP"  # 127 - Combat Radio User Datagram
    SSCOPMCE = "SSCOPMCE"  # 128 - SSCOPMCE
    IPLT = "IPLT"  # 129 - IPLT
    
    # 130-139
    SPS = "SPS"  # 130 - Secure Packet Shield
    PIPE = "PIPE"  # 131 - Private IP Encapsulation within IP
    SCTP = "SCTP"  # 132 - Stream Control Transmission Protocol
    FC = "FC"  # 133 - Fibre Channel
    RSVP_E2E_IGNORE = "RSVP_E2E_IGNORE"  # 134 - RSVP-E2E-IGNORE
    MOBILITY_HEADER = "MOBILITY_HEADER"  # 135 - Mobility Header
    UDPLITE = "UDPLITE"  # 136 - UDPLite
    MPLS_IN_IP = "MPLS_IN_IP"  # 137 - MPLS-in-IP
    MANET = "MANET"  # 138 - MANET Protocols
    HIP = "HIP"  # 139 - Host Identity Protocol
    
    # 140-147
    SHIM6 = "SHIM6"  # 140 - Shim6 Protocol
    WESP = "WESP"  # 141 - Wrapped Encapsulating Security Payload
    ROHC = "ROHC"  # 142 - Robust Header Compression
    ETHERNET = "ETHERNET"  # 143 - Ethernet
    AGGFRAG = "AGGFRAG"  # 144 - AGGFRAG encapsulation payload for ESP
    NSH = "NSH"  # 145 - Network Service Header
    HOMA = "HOMA"  # 146 - Homa
    BIT_EMU = "BIT_EMU"  # 147 - Bit-stream Emulation
    
    # Experimental and reserved
    EXPERIMENTAL_1 = "EXPERIMENTAL_1"  # 253 - Use for experimentation and testing
    EXPERIMENTAL_2 = "EXPERIMENTAL_2"  # 254 - Use for experimentation and testing
    RESERVED = "RESERVED"  # 255 - Reserved
    
    # Catch-all for unlisted protocols
    OTHER = "OTHER"


class UserRole(str, Enum):
    ANALYST = "ANALYST"
    ADMIN = "ADMIN"
    AUDITOR = "AUDITOR"


class UserStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    LOCKED = "LOCKED"


class SessionRevokedReason(str, Enum):
    USER_LOGOUT = "USER_LOGOUT"
    ADMIN_FORCE = "ADMIN_FORCE"
    SESSION_TIMEOUT = "SESSION_TIMEOUT"
    RESET_REQUIRED = "RESET_REQUIRED"


class AuditEventType(str, Enum):
    """Audit event types for persisted system actions."""

    AUTH_LOGIN_SUCCESS = "auth.login.success"
    AUTH_LOGIN_FAILURE = "auth.login.failure"
    AUTH_LOGOUT = "auth.logout"
    AUTH_LOCKOUT = "auth.lockout"
    AUTH_OIDC_LOGIN_SUCCESS = "auth.oidc.login.success"
    AUTH_OIDC_LOGIN_FAILURE = "auth.oidc.login.failure"
    AUTH_OIDC_ACCOUNT_LINKED = "auth.oidc.account_linked"
    AUTH_OIDC_ACCOUNT_PROVISIONED = "auth.oidc.account_provisioned"
    AUTH_PASSWORD_CHANGED = "auth.password_changed"
    AUTH_ADMIN_USER_CREATED = "auth.admin.user_created"
    AUTH_ADMIN_USER_STATUS_CHANGED = "auth.admin.user_status_changed"
    AUTH_ADMIN_PASSWORD_RESET_ISSUED = "auth.admin.password_reset_issued"
    AUTH_ADMIN_RESET_ISSUED = "auth.admin.reset_issued"
    AUTH_API_KEY_CREATED = "auth.api_key.created"
    AUTH_API_KEY_REVOKED = "auth.api_key.revoked"
    AUTH_API_KEY_AUTH_SUCCESS = "auth.api_key.auth_success"
    AUTH_API_KEY_AUTH_FAILURE = "auth.api_key.auth_failure"
    AUTH_NHI_ACCOUNT_CREATED = "auth.nhi.account_created"
    TIMELINE_ITEM_ADDED = "timeline.item.added"
    TIMELINE_ITEM_UPDATED = "timeline.item.updated"
    TIMELINE_ITEM_DELETED = "timeline.item.deleted"
    ENTITY_UPDATED = "entity.updated"
    ENTITY_DELETED = "entity.deleted"
    CASE_CREATED = "case.created"
    CASE_STATUS_CHANGED = "case.status_changed"
    CASE_PRIORITY_CHANGED = "case.priority_changed"
    CASE_ASSIGNEE_CHANGED = "case.assignee_changed"
    CASE_TITLE_CHANGED = "case.title_changed"
    CASE_DESCRIPTION_CHANGED = "case.description_changed"
    CASE_TAGS_CHANGED = "case.tags_changed"
    CASE_LINKED_ITEMS_CLOSED = "case.linked_items_closed"
    CASE_DELETED = "case.deleted"
    SETTINGS_CREATED = "settings.created"
    SETTINGS_UPDATED = "settings.updated"
    SETTINGS_DELETED = "settings.deleted"


class UploadStatus(str, Enum):
    """Upload state for attachment files"""
    UPLOADING = "UPLOADING"  # Initial state, upload in progress
    COMPLETE = "COMPLETE"    # Upload succeeded and verified
    FAILED = "FAILED"        # Upload failed or timed out


class SettingType(str, Enum):
    """Type of setting value for validation and coercion"""
    STRING = "STRING"
    NUMBER = "NUMBER"
    BOOLEAN = "BOOLEAN"
    JSON = "JSON"


class LangFlowContextType(str, Enum):
    """Context type for LangFlow chat sessions - determines which flow to use"""
    general = "general"
    case = "case"
    task = "task"
    alert = "alert"


class SessionStatus(str, Enum):
    """LangFlow session status"""
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


class MessageRole(str, Enum):
    """Role of message sender in AI conversation"""
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"


class AccountType(str, Enum):
    """Type of user account"""
    HUMAN = "HUMAN"  # Human user with email/password authentication
    NHI = "NHI"  # Non-Human Identity (service account) with API key authentication only


class RecommendationStatus(str, Enum):
    """Status of AI triage recommendation"""
    QUEUED = "QUEUED"  # Job enqueued, waiting for worker
    PENDING = "PENDING"  # Recommendation ready for review
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    FAILED = "FAILED"  # Triage job failed


class TriageDisposition(str, Enum):
    """Triage disposition for alerts"""
    TRUE_POSITIVE = "TRUE_POSITIVE"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    BENIGN = "BENIGN"
    NEEDS_INVESTIGATION = "NEEDS_INVESTIGATION"
    DUPLICATE = "DUPLICATE"
    UNKNOWN = "UNKNOWN"


class RejectionCategory(str, Enum):
    """Category for AI triage recommendation rejection"""
    INCORRECT_DISPOSITION = "INCORRECT_DISPOSITION"
    WRONG_SUGGESTED_STATUS = "WRONG_SUGGESTED_STATUS"
    WRONG_PRIORITY = "WRONG_PRIORITY"
    MISSING_CONTEXT = "MISSING_CONTEXT"
    INCOMPLETE_ANALYSIS = "INCOMPLETE_ANALYSIS"
    PREFER_MANUAL_REVIEW = "PREFER_MANUAL_REVIEW"
    FALSE_REASONING = "FALSE_REASONING"
    OTHER = "OTHER"
    SUPERSEDED_MANUAL_TRIAGE = "SUPERSEDED_MANUAL_TRIAGE"  # Auto-rejected when alert manually triaged


class MessageFeedback(str, Enum):
    """Feedback for AI chat messages"""
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"

