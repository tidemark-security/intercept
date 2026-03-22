"""
Service for generating dummy/mock data for development and testing.
"""

import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.models.models import (
    UserAccount,
    Case,
    Alert,
    Task,
    CaseCreate,
    AlertCreate,
    TaskCreate,
    CaseTimelineItem,
    AlertTimelineItem,
    NoteItem,
    AttachmentItem,
    ObservableItem,
    LinkItem,
    AlertItem,
    TaskItem,
    ForensicArtifactItem,
    TTPItem,
    SystemItem,
    EmailItem,
    NetworkTrafficItem,
    ProcessItem,
    RegistryChangeItem,
    CaseItem,
)
from app.models.enums import (
    CaseStatus,
    Priority,
    AlertStatus,
    ObservableType,
    TaskStatus,
    SystemType,
    Protocol,
)
from app.services.case_service import case_service
from app.services.alert_service import alert_service
from app.services.task_service import task_service
from app.models.models import AlertTriageRequest


class DummyDataService:
    """Service for generating randomized dummy data."""

    CLOSURE_PRONE_ALERT_DEFAULT_COUNT = 5

    # Sample data pools for realistic generation
    CASE_TITLES = [
        "Advanced Persistent Threat Investigation",
        "Data Breach Response - Customer Portal",
        "Insider Threat Monitoring - Unusual Access Patterns",
        "Phishing Campaign Analysis",
        "Ransomware Incident Response",
        "Zero-Day Vulnerability Exploitation Attempt",
        "Cryptocurrency Mining Malware Detection",
        "SQL Injection Attack Investigation",
        "Business Email Compromise Investigation",
        "Suspicious Network Traffic Analysis",
        "Malware Command & Control Communication",
        "DDoS Attack Mitigation",
        "Cloud Infrastructure Breach",
        "Supply Chain Security Incident",
        "Nation-State Attribution Analysis",
    ]

    CASE_DESCRIPTIONS = [
        "Investigation into sophisticated APT group targeting critical infrastructure with custom malware and lateral movement techniques.",
        "Response to potential data breach affecting customer portal authentication system and personal data exposure.",
        "Investigation into suspicious employee behavior including unauthorized data access and potential intellectual property theft.",
        "Analysis of large-scale phishing campaign targeting financial services with credential harvesting focus.",
        "Active ransomware incident affecting production systems with file encryption and ransom demands.",
        "Critical vulnerability exploitation attempt using zero-day exploit against web application framework.",
        "Unauthorized cryptocurrency mining software detected on corporate workstations with network propagation.",
        "Database injection attempts detected on customer portal with potential data extraction.",
        "Executive-targeted email compromise with wire transfer fraud attempt and account takeover.",
        "Unusual outbound network traffic patterns indicating potential data exfiltration or C2 communication.",
        "Malware communication with external command and control servers detected on critical systems.",
        "Large-scale distributed denial of service attack targeting public-facing services.",
        "Unauthorized access to cloud infrastructure with potential data exposure and privilege escalation.",
        "Third-party vendor compromise affecting supply chain security and downstream customers.",
        "Advanced threat actor attribution analysis using tactics, techniques, and procedures correlation.",
    ]

    ALERT_TITLES = [
        "Suspicious Network Traffic Detected",
        "Failed Login Attempts",
        "Malware Signature Match",
        "Unauthorized File Access",
        "Port Scan Detected",
        "Critical Zero-Day Vulnerability Exploitation Attempt",
        "SQL Injection Attack",
        "Sophisticated Multi-Stage Phishing Campaign",
        "DNS Tunneling Activity",
        "Insider Threat Detection: Unusual Data Access Patterns",
        "Cryptocurrency Mining Malware",
        "Advanced Persistent Threat Group APT29 Attribution",
        "Privilege Escalation Attempt",
        "Data Exfiltration via Cloud Storage",
        "Ransomware Encryption Activity",
    ]

    ALERT_DESCRIPTIONS = [
        "Unusual outbound traffic patterns detected from server to external IP addresses",
        "Multiple failed login attempts detected for admin account from various IP addresses",
        "Known malware signature detected in email attachment",
        "Sensitive file accessed outside normal business hours",
        "Systematic port scanning activity detected from external source",
        "Advanced persistent threat attempting to exploit newly discovered vulnerability in outdated framework",
        "Database injection attempts detected on customer portal login form",
        "Coordinated phishing attack specifically targeting C-level executives with personalized emails",
        "Suspicious DNS queries indicating potential data exfiltration through DNS tunneling",
        "Privileged user account exhibiting unusual behavior patterns including bulk database queries",
        "Unauthorized cryptocurrency mining software detected on workstation",
        "Indicators matching known APT group tactics, techniques, and procedures including cloud C2",
        "Attempted privilege escalation using known exploit techniques on domain controller",
        "Large volume data upload to unauthorized cloud storage service detected",
        "File encryption activity detected on multiple network shares with ransom note deployment",
    ]

    # USERS list is now dynamically fetched from the API
    # Use DummyDataService._get_random_user() or DummyDataService._get_users_list()
    # to get user data when needed

    @staticmethod
    async def _get_users_list(db: AsyncSession) -> List[str]:
        """Fetch list of usernames from the database."""

        result = await db.execute(select(UserAccount))
        users = result.scalars().all()

        # Fallback to default users if no users in database
        if not users:
            return [
                "system",
            ]

        return [user.username for user in users]

    @staticmethod
    async def _get_random_user(db: AsyncSession) -> str:
        """Get a random username from the database."""
        users = await DummyDataService._get_users_list(db)
        return random.choice(users)

    SYSTEMS = [
        "SRV-WEB-01",
        "SRV-DB-02",
        "SRV-DC-01",
        "SRV-EXCHANGE-01",
        "FW-PERIMETER-01",
        "SRV-PORTAL-01",
        "MAIL-GW-01",
        "WS-FINANCE-05",
        "SRV-WEB-LEGACY-01",
        "FILE-SRV-01",
        "DB-PROD-01",
        "AD-CONTROLLER-01",
    ]

    SOURCE_SYSTEMS = [
        "Network IDS",
        "Authentication System",
        "Email Security Gateway",
        "File Integrity Monitor",
        "Firewall",
        "Vulnerability Scanner",
        "Web Application Firewall",
        "Email Security",
        "DNS Monitor",
        "User Behavior Analytics",
        "Endpoint Detection",
        "Threat Intelligence",
    ]

    CATEGORIES = [
        "Network Security",
        "Access Control",
        "Malware",
        "Data Protection",
        "Reconnaissance",
        "Vulnerability Exploitation",
        "Web Security",
        "Phishing",
        "Data Exfiltration",
        "Insider Threat",
        "APT Activity",
    ]

    TAGS = [
        "apt",
        "malware",
        "infrastructure",
        "data-breach",
        "customer-data",
        "authentication",
        "insider-threat",
        "data-access",
        "ip-theft",
        "phishing",
        "financial",
        "credentials",
        "ransomware",
        "production",
        "encryption",
        "urgent",
        "security",
        "critical",
    ]

    @staticmethod
    def _random_datetime(days_back: int = 30) -> datetime:
        """Generate a random timezone-aware datetime within the last N days."""
        start = datetime.now(timezone.utc) - timedelta(days=days_back)
        end = datetime.now(timezone.utc)
        return start + timedelta(
            seconds=random.randint(0, int((end - start).total_seconds()))
        )

    @staticmethod
    def _random_ip() -> str:
        """Generate a random IP address."""
        return f"{random.randint(1, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"

    @staticmethod
    def _generate_case_number() -> str:
        """Generate a unique case number."""
        year = datetime.now().year
        num = random.randint(1, 9999)
        return f"CASE-{year}-{num:04d}"

    @staticmethod
    def _generate_alert_id() -> str:
        """Generate a unique alert ID."""
        year = datetime.now().year
        num = random.randint(1, 9999)
        return f"ALT-{year}-{num:04d}"

    @staticmethod
    def _generate_reply_note(parent_id: str, reply_index: int, users: List[str], parent_time: datetime) -> Dict[str, Any]:
        """Generate a single reply note."""
        reply_time = parent_time + timedelta(minutes=random.randint(5, 120))
        reply_notes = [
            "Thanks for the update, continuing investigation",
            "Confirmed - I see the same indicators on my end",
            "Good catch, escalating this to the security team",
            "I've reviewed the logs and this looks legitimate",
            "Let's schedule a call to discuss findings",
            "Updated the ticket with additional context",
            "This is likely a false positive based on user behavior",
            "Agreed, marking this for follow-up tomorrow",
        ]
        
        return {
            "id": f"{parent_id}-reply-{reply_index}",
            "type": "note",
            "description": random.choice(reply_notes),
            "created_at": reply_time.isoformat(),
            "timestamp": reply_time.isoformat(),
            "created_by": random.choice(users),
            "tags": [],
            "flagged": False,
            "highlighted": False,
            "replies": [],  # Replies cannot have nested replies (max depth 1)
        }

    @staticmethod
    def _generate_timeline_items_for_case(
        item_id_prefix: str, users: List[str], num_items: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Generate timeline items for a case."""
        if num_items is None:
            num_items = random.randint(3, 12)

        items = []
        # Case timeline items: excludes task (created as real DB entities) and case (no case-to-case linking)
        item_types = [
            "note",
            "observable",
            "attachment",
            "link",
            "alert",
            "forensic_artifact",
            "ttp",
            "system",
            "email",
            "network_traffic",
            "process",
            "registry_change",
        ]

        for i in range(num_items):
            item_type = random.choice(item_types)
            base_time = DummyDataService._random_datetime(7)

            base_item = {
                "id": f"{item_id_prefix}-timeline-{i+1}",
                "type": item_type,
                "created_at": base_time.isoformat(),
                "timestamp": base_time.isoformat(),
                "created_by": random.choice(users),
                "tags": random.sample(DummyDataService.TAGS, random.randint(0, 3)),
                "flagged": random.random() < 0.15,  # 15% chance of being flagged
                "highlighted": random.random() < 0.1,  # 10% chance of being highlighted
            }

            # Add type-specific fields and descriptions
            if item_type == "note":
                notes = [
                    "Analyst notes: Initial triage indicates potential malicious activity",
                    "Update: Contacted system owner for additional context",
                    "Investigation progress: Reviewed logs and identified suspicious patterns",
                    "Follow-up required: Need to escalate to tier 2 for deeper analysis",
                    "Resolution notes: Confirmed false positive after investigation",
                ]
                base_item["description"] = random.choice(notes)
                
                # 40% chance of having replies (1-3 replies)
                if random.random() < 0.4:
                    num_replies = random.randint(1, 3)
                    base_item["replies"] = [
                        DummyDataService._generate_reply_note(
                            base_item["id"], j+1, users, base_time
                        )
                        for j in range(num_replies)
                    ]
                else:
                    base_item["replies"] = []

            elif item_type == "observable":
                obs_type = random.choice(list(ObservableType))
                base_item["observable_type"] = obs_type.value

                if obs_type == ObservableType.IP:
                    base_item["observable_value"] = DummyDataService._random_ip()
                    base_item["description"] = (
                        f"Suspicious IP address detected: {base_item['observable_value']}"
                    )
                elif obs_type == ObservableType.DOMAIN:
                    domain = f"malicious-{random.randint(100, 999)}.com"
                    base_item["observable_value"] = domain
                    base_item["description"] = f"Malicious domain observed: {domain}"
                elif obs_type == ObservableType.HASH:
                    hash_val = uuid.uuid4().hex[:32]
                    base_item["observable_value"] = hash_val
                    base_item["description"] = f"File hash SHA256: {hash_val}"
                elif obs_type == ObservableType.EMAIL:
                    email = f"attacker{random.randint(1, 50)}@malicious.com"
                    base_item["observable_value"] = email
                    base_item["description"] = f"Suspicious email address: {email}"
                else:
                    base_item["observable_value"] = (
                        f"{obs_type.value}_value_{random.randint(100, 999)}"
                    )
                    base_item["description"] = (
                        f"Observable of type {obs_type.value} detected"
                    )

            elif item_type == "attachment":
                file_types = [
                    (
                        "evidence_report.pdf",
                        "application/pdf",
                        "Evidence collection report",
                    ),
                    (
                        "screenshot.png",
                        "image/png",
                        "Screenshot of suspicious activity",
                    ),
                    (
                        "memory_dump.dmp",
                        "application/octet-stream",
                        "Memory dump from affected system",
                    ),
                    (
                        "network_capture.pcap",
                        "application/vnd.tcpdump.pcap",
                        "Network traffic capture",
                    ),
                    (
                        "malware_sample.bin",
                        "application/octet-stream",
                        "Quarantined malware sample",
                    ),
                ]
                file_name, mime_type, desc = random.choice(file_types)
                base_item.update(
                    {
                        "file_name": f"{i+1}_{file_name}",
                        "mime_type": mime_type,
                        "file_size": random.randint(1024, 52428800),  # 1KB to 50MB
                        "url": f"/uploads/{item_id_prefix}/{i+1}_{file_name}",
                        "description": desc,
                    }
                )

            elif item_type == "link":
                links = [
                    (
                        "https://attack.mitre.org/techniques/T1059/",
                        "MITRE ATT&CK Technique Reference",
                    ),
                    (
                        "https://www.virustotal.com/gui/file/abc123",
                        "VirusTotal Analysis Report",
                    ),
                    (
                        "https://threatintel.example.com/report/2024",
                        "Threat Intelligence Report",
                    ),
                    (
                        "https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-1234",
                        "CVE Database Entry",
                    ),
                    (
                        "https://wiki.internal.example.com/runbook",
                        "Internal Investigation Runbook",
                    ),
                ]
                url, desc = random.choice(links)
                base_item.update({"url": url, "description": desc})

            elif item_type == "alert":
                base_item.update(
                    {
                        "alert_id": random.randint(1, 100),
                        "title": random.choice(DummyDataService.ALERT_TITLES),
                        "priority": random.choice(list(Priority)).value,
                        "assignee": random.choice(users),
                        "description": "Related alert linked to this case",
                    }
                )

            # Note: task items are no longer generated here - they are created as 
            # real Task entities in the database via generate_cases()

            elif item_type == "forensic_artifact":
                artifacts = [
                    ("disk_image.dd", "sha256", uuid.uuid4().hex[:32]),
                    ("memory_dump.raw", "md5", uuid.uuid4().hex[:32]),
                    ("event_logs.evtx", "sha256", uuid.uuid4().hex[:32]),
                    ("registry_hive.dat", "sha256", uuid.uuid4().hex[:32]),
                ]
                file_name, hash_type, hash_val = random.choice(artifacts)
                base_item.update(
                    {
                        "file_name": file_name,
                        "hash": hash_val,
                        "hash_type": hash_type,
                        "url": f"/evidence/{item_id_prefix}/{file_name}",
                        "description": f"Forensic artifact: {file_name}",
                    }
                )

            elif item_type == "ttp":
                ttps = [
                    (
                        "T1059",
                        "Command and Scripting Interpreter",
                        "Execution",
                        "Command Line Interface",
                    ),
                    (
                        "T1071",
                        "Application Layer Protocol",
                        "Command and Control",
                        "Web Protocols",
                    ),
                    ("T1566", "Phishing", "Initial Access", "Spearphishing Attachment"),
                    ("T1486", "Data Encrypted for Impact", "Impact", "Ransomware"),
                    ("T1055", "Process Injection", "Defense Evasion", "DLL Injection"),
                ]
                mitre_id, title, tactic, technique = random.choice(ttps)
                base_item.update(
                    {
                        "mitre_id": mitre_id,
                        "title": title,
                        "tactic": tactic,
                        "technique": technique,
                        "url": f"https://attack.mitre.org/techniques/{mitre_id}/",
                        "description": f"MITRE ATT&CK Technique: {mitre_id} - {title}",
                    }
                )

            elif item_type == "system":
                system = random.choice(DummyDataService.SYSTEMS)
                sys_type = random.choice(list(SystemType))
                base_item.update(
                    {
                        "hostname": system,
                        "ip_address": DummyDataService._random_ip(),
                        "system_type": sys_type.value,
                        "is_critical": random.random() < 0.2,
                        "is_internet_facing": random.random() < 0.3,
                        "is_high_risk": random.random() < 0.15,
                        "is_legacy": random.random() < 0.1,
                        "is_privileged": random.random() < 0.25,
                        "description": f"Affected system: {system} ({sys_type.value})",
                    }
                )

            elif item_type == "email":
                senders = [
                    "attacker@malicious.com",
                    "phishing@fake-bank.com",
                    "ceo-impersonation@evil.com",
                ]
                subjects = [
                    "Urgent: Wire Transfer Required",
                    "Your Account Has Been Suspended",
                    "RE: Invoice Payment Overdue",
                    "Security Alert: Verify Your Identity",
                ]
                base_item.update(
                    {
                        "sender": random.choice(senders),
                        "recipient": f"{random.choice(users)}@company.com",
                        "subject": random.choice(subjects),
                        "message_id": f"<{uuid.uuid4()}@malicious.com>",
                        "description": "Suspicious email communication",
                    }
                )

            elif item_type == "network_traffic":
                protocols = [Protocol.TCP, Protocol.UDP, Protocol.ICMP]
                base_item.update(
                    {
                        "source_ip": DummyDataService._random_ip(),
                        "destination_ip": DummyDataService._random_ip(),
                        "source_port": random.randint(1024, 65535),
                        "destination_port": random.choice(
                            [80, 443, 8080, 3389, 445, 22]
                        ),
                        "protocol": random.choice(protocols).value,
                        "bytes_sent": random.randint(1024, 10485760),
                        "bytes_received": random.randint(512, 5242880),
                        "duration": random.randint(1, 300),
                        "description": "Suspicious network traffic observed",
                    }
                )

            elif item_type == "process":
                processes = [
                    ("powershell.exe", "powershell.exe -encodedcommand ABCD1234..."),
                    ("cmd.exe", "cmd.exe /c whoami && net user"),
                    ("rundll32.exe", "rundll32.exe malicious.dll,EntryPoint"),
                    ("svchost.exe", "svchost.exe -k netsvcs -p"),
                ]
                proc_name, cmd_line = random.choice(processes)
                base_item.update(
                    {
                        "process_name": proc_name,
                        "process_id": random.randint(1000, 9999),
                        "parent_process_id": random.randint(100, 999),
                        "command_line": cmd_line,
                        "user_account": random.choice(users),
                        "duration": random.randint(1, 120),
                        "exit_code": random.choice([0, 1, -1]),
                        "description": f"Suspicious process execution: {proc_name}",
                    }
                )

            elif item_type == "registry_change":
                keys = [
                    "HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
                    "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce",
                    "HKLM\\System\\CurrentControlSet\\Services",
                ]
                base_item.update(
                    {
                        "registry_key": random.choice(keys),
                        "registry_value": f"MaliciousEntry{random.randint(1, 100)}",
                        "old_data": None,
                        "new_data": "C:\\Windows\\Temp\\malware.exe",
                        "operation": random.choice(["CREATE", "MODIFY", "DELETE"]),
                        "user_account": random.choice(users),
                        "description": "Suspicious registry modification detected",
                    }
                )

            # Ensure all non-note items have empty replies array
            if "replies" not in base_item:
                base_item["replies"] = []

            items.append(base_item)

        return items

    @staticmethod
    def _generate_timeline_items_for_alert(
        item_id_prefix: str, users: List[str], num_items: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Generate timeline items for an alert."""
        if num_items is None:
            num_items = random.randint(2, 8)

        items = []
        # Alert timeline items: subset of case items, no tasks/forensic artifacts/alerts
        item_types = [
            "note",
            "observable",
            "attachment",
            "link",
            "ttp",
            "system",
            "email",
            "network_traffic",
            "process",
            "registry_change",
            "case",
        ]

        for i in range(num_items):
            item_type = random.choice(item_types)
            base_time = DummyDataService._random_datetime(7)

            base_item = {
                "id": f"{item_id_prefix}-timeline-{i+1}",
                "type": item_type,
                "created_at": base_time.isoformat(),
                "timestamp": base_time.isoformat(),
                "created_by": random.choice(users),
                "tags": random.sample(DummyDataService.TAGS, random.randint(0, 2)),
                "flagged": random.random() < 0.1,
                "highlighted": random.random() < 0.05,
            }

            # Use similar logic as case items, but simplified
            if item_type == "note":
                base_item["description"] = (
                    "Triage note: Investigating potential security incident"
                )
                
                # 30% chance of having replies (1-2 replies)
                if random.random() < 0.3:
                    num_replies = random.randint(1, 2)
                    base_item["replies"] = [
                        DummyDataService._generate_reply_note(
                            base_item["id"], j+1, users, base_time
                        )
                        for j in range(num_replies)
                    ]
                else:
                    base_item["replies"] = []
            elif item_type == "observable":
                obs_type = random.choice(list(ObservableType))
                base_item.update(
                    {
                        "observable_type": obs_type.value,
                        "observable_value": (
                            DummyDataService._random_ip()
                            if obs_type == ObservableType.IP
                            else f"{obs_type.value}_value"
                        ),
                        "description": f"IOC detected: {obs_type.value}",
                    }
                )
            elif item_type == "system":
                system = random.choice(DummyDataService.SYSTEMS)
                base_item.update(
                    {
                        "hostname": system,
                        "ip_address": DummyDataService._random_ip(),
                        "system_type": random.choice(list(SystemType)).value,
                        "description": f"Alert source system: {system}",
                    }
                )
            elif item_type == "network_traffic":
                base_item.update(
                    {
                        "source_ip": DummyDataService._random_ip(),
                        "destination_ip": DummyDataService._random_ip(),
                        "source_port": random.randint(1024, 65535),
                        "destination_port": random.choice([80, 443, 8080]),
                        "protocol": random.choice([Protocol.TCP, Protocol.UDP]).value,
                        "description": "Network traffic event",
                    }
                )
            elif item_type == "case":
                base_item.update(
                    {
                        "case_id": random.randint(1, 50),
                        "title": random.choice(DummyDataService.CASE_TITLES),
                        "priority": random.choice(list(Priority)).value,
                        "description": "Alert escalated to case",
                    }
                )
            else:
                base_item["description"] = f"Alert timeline item: {item_type}"

            # Ensure all non-note items have empty replies array
            if "replies" not in base_item:
                base_item["replies"] = []

            items.append(base_item)

        return items

    @staticmethod
    async def _create_task_for_timeline(
        db: AsyncSession,
        case_id: int,
        users: List[str],
        base_time: datetime
    ) -> Task:
        """Create a real Task entity in the database for timeline items."""
        task_titles = [
            "Review system logs for additional IOCs",
            "Contact system owner for incident details",
            "Perform forensic analysis on affected endpoint",
            "Update firewall rules to block malicious IPs",
            "Prepare incident report for management",
            "Collect and preserve evidence",
            "Interview affected users",
            "Document timeline of events",
            "Assess impact and scope",
            "Implement containment measures",
        ]
        
        task_data = TaskCreate(
            title=random.choice(task_titles),
            description=f"Task created for case investigation",
            priority=random.choice(list(Priority)),
            status=random.choice(list(TaskStatus)),
            assignee=random.choice(users),
            case_id=case_id,
            due_date=base_time + timedelta(days=random.randint(1, 14)),
        )
        
        created_by = random.choice(users)
        task = await task_service.create_task(db, task_data, created_by)
        return task

    @staticmethod
    async def generate_cases(db: AsyncSession, count: int = 10) -> List[Case]:
        """Generate random cases by first creating alerts and then triaging/escalating them.
        
        Cases are ONLY created through the alert triage workflow, ensuring proper
        alert-to-case conversion process is followed.
        """
        cases = []
        
        # Get list of users from database
        users = await DummyDataService._get_users_list(db)

        for i in range(count):
            # First create an alert
            alert_title = random.choice(DummyDataService.ALERT_TITLES)
            alert_description = random.choice(DummyDataService.ALERT_DESCRIPTIONS)
            
            alert_data = AlertCreate(
                title=alert_title,
                description=alert_description,
                priority=random.choice(list(Priority)),
                source=random.choice(DummyDataService.SOURCE_SYSTEMS),
            )
            
            alert = await alert_service.create_alert(db, alert_data)
            alert.tags = random.sample(DummyDataService.TAGS, random.randint(0, 4))
            alert.created_at = DummyDataService._random_datetime(15)
            alert.updated_at = alert.created_at + timedelta(minutes=random.randint(5, 1440))
            
            # Generate timeline items for the alert
            alert_timeline_items = DummyDataService._generate_timeline_items_for_alert(
                f"alert-{alert.id}", users
            )
            alert.timeline_items = alert_timeline_items
            
            await db.commit()
            await db.refresh(alert)
            
            # Now triage the alert and escalate to case
            case_title = random.choice(DummyDataService.CASE_TITLES)
            case_description = random.choice(DummyDataService.CASE_DESCRIPTIONS)
            created_by = random.choice(users)
            
            triage_request = AlertTriageRequest(
                status=AlertStatus.ESCALATED,
                triage_notes=f"Escalated to case for investigation: {alert_title}",
                escalate_to_case=True,
                case_title=case_title,
                case_description=case_description,
            )
            
            # Triage the alert - this creates the case
            assert alert.id is not None, "Alert must have an ID after creation"
            await alert_service.triage_alert(db, alert.id, triage_request, created_by)
            
            # Refresh alert to get the case_id
            await db.refresh(alert)
            
            # Get the created case
            assert alert.case_id is not None, "Alert must have a case_id after escalation"
            case = await case_service.get_case(db, alert.case_id)
            assert case is not None, "Case must exist after triage escalation"

            # Generate timeline items (excluding task type - we'll add those separately)
            timeline_items = DummyDataService._generate_timeline_items_for_case(
                f"case-{case.id}", users
            )
            
            # Filter out task items (we'll create real tasks instead)
            # Alert items referencing the source alert are already handled by triage
            non_entity_items = [item for item in timeline_items if item["type"] not in ("task", "alert")]
            
            # Create real Task entities for this case (0-5 tasks per case)
            # Tasks are linked to the case via case_id and will appear in the timeline
            # through the denormalization process - no need to add them to timeline_items JSON
            num_tasks = random.randint(0, 5)
            assert case.id is not None, "Case must have an ID after creation"
            for j in range(num_tasks):
                base_time = DummyDataService._random_datetime(7)
                await DummyDataService._create_task_for_timeline(
                    db, case.id, users, base_time
                )

            # Update case with timeline items
            case.timeline_items = non_entity_items
            case.status = random.choice(list(CaseStatus))

            if case.status == CaseStatus.CLOSED:
                case.closed_at = case.updated_at

            await db.commit()
            await db.refresh(case)
            cases.append(case)

        return cases

    @staticmethod
    async def generate_alerts(
        db: AsyncSession,
        count: int = 20,
        include_closure_prone: bool = True,
        closure_prone_count: int = CLOSURE_PRONE_ALERT_DEFAULT_COUNT,
    ) -> List[Alert]:
        """Generate random alerts and optionally add closure-prone alert scenarios."""
        alerts = []
        
        # Get list of users from database
        users = await DummyDataService._get_users_list(db)

        for i in range(count):
            title = random.choice(DummyDataService.ALERT_TITLES)
            description = random.choice(DummyDataService.ALERT_DESCRIPTIONS)

            alert_data = AlertCreate(
                title=title,
                description=description,
                priority=random.choice(list(Priority)),
                source=random.choice(DummyDataService.SOURCE_SYSTEMS),
            )

            alert = await alert_service.create_alert(db, alert_data)

            # Add tags
            alert.tags = random.sample(DummyDataService.TAGS, random.randint(0, 4))

            # Generate timeline items
            timeline_items = DummyDataService._generate_timeline_items_for_alert(
                f"alert-{alert.id}", users
            )
            alert.timeline_items = timeline_items

            # Randomly assign status and triage info
            # Weight the statuses - most alerts should be NEW, some closed
            # NOTE: ESCALATED status is NOT assigned here - it's only set when 
            # an alert is actually linked to a case in populate_dummy_data()
            status_choices = [
                AlertStatus.NEW,  # 50% new alerts
                AlertStatus.IN_PROGRESS,  # 20% in progress
                AlertStatus.CLOSED_TP,  # 10% true positives
                AlertStatus.CLOSED_FP,  # 10% false positives
                AlertStatus.CLOSED_BP,  # 5% benign positives
                AlertStatus.CLOSED_UNRESOLVED,  # 3% unresolved
                AlertStatus.CLOSED_DUPLICATE,  # 2% duplicates
            ]
            status_weights = [0.5, 0.2, 0.1, 0.1, 0.05, 0.03, 0.02]

            alert.status = random.choices(status_choices, weights=status_weights)[0]

            alert.created_at = DummyDataService._random_datetime(15)
            alert.updated_at = alert.created_at + timedelta(
                minutes=random.randint(5, 1440)
            )

            # Add triage info for processed alerts
            if alert.status != AlertStatus.NEW:
                alert.triage_notes = f"Triage: {random.choice(['True positive - remediated', 'False positive - benign', 'Duplicate alert', 'Unresolved'])}"
                alert.triaged_at = alert.created_at + timedelta(
                    minutes=random.randint(5, 720)
                )

            await db.commit()
            await db.refresh(alert)
            alerts.append(alert)

        if include_closure_prone and closure_prone_count > 0:
            closure_alerts = await DummyDataService.generate_closure_prone_alerts(
                db,
                count=closure_prone_count,
            )
            alerts.extend(closure_alerts)

        return alerts

    @staticmethod
    def _build_closure_prone_alert_scenarios(users: List[str]) -> List[Dict[str, Any]]:
        """Build deterministic alert scenarios likely to produce closure recommendations."""
        analyst = random.choice(users)
        scanner_host = random.choice(DummyDataService.SYSTEMS)

        return [
            {
                "title": "Scheduled Vulnerability Scan Activity Detected",
                "description": (
                    "High-volume probe activity from approved scanner during documented maintenance "
                    "window CHG-2026-0215. Target systems are known patch-validation assets."
                ),
                "priority": Priority.LOW,
                "source": "Vulnerability Scanner",
                "tags": ["vuln_scan", "approved_change", "maintenance_window", "network"],
                "timeline_items": [
                    {
                        "id": "closure-1-note",
                        "type": "note",
                        "description": "Change ticket CHG-2026-0215 confirms scheduled Nessus scan.",
                        "created_at": DummyDataService._random_datetime(2).isoformat(),
                        "timestamp": DummyDataService._random_datetime(2).isoformat(),
                        "created_by": analyst,
                        "tags": ["change_control", "approved"],
                        "flagged": False,
                        "highlighted": False,
                        "replies": [],
                    },
                    {
                        "id": "closure-1-system",
                        "type": "system",
                        "hostname": scanner_host,
                        "ip_address": "10.10.20.15",
                        "system_type": SystemType.ENT_APPLICATION_SERVER.value,
                        "description": "Authorized scanner host from security operations subnet.",
                        "created_at": DummyDataService._random_datetime(2).isoformat(),
                        "timestamp": DummyDataService._random_datetime(2).isoformat(),
                        "created_by": analyst,
                        "tags": ["approved_scanner"],
                        "flagged": False,
                        "highlighted": False,
                        "replies": [],
                    },
                ],
            },
            {
                "title": "Administrative PowerShell Execution on Domain Controller",
                "description": (
                    "PowerShell activity observed from privileged admin account on domain controller "
                    "during patch window with approved maintenance runbook reference OPS-RBK-44."
                ),
                "priority": Priority.MEDIUM,
                "source": "Endpoint Detection",
                "tags": ["endpoint", "admin_activity", "maintenance_window"],
                "timeline_items": [
                    {
                        "id": "closure-2-note",
                        "type": "note",
                        "description": (
                            "On-call SRE confirmed command set matches monthly patch compliance script."
                        ),
                        "created_at": DummyDataService._random_datetime(2).isoformat(),
                        "timestamp": DummyDataService._random_datetime(2).isoformat(),
                        "created_by": analyst,
                        "tags": ["sre", "approved"],
                        "flagged": False,
                        "highlighted": False,
                        "replies": [],
                    },
                    {
                        "id": "closure-2-process",
                        "type": "process",
                        "process_name": "powershell.exe",
                        "process_id": random.randint(2000, 9000),
                        "parent_process_id": random.randint(100, 999),
                        "command_line": "powershell.exe -File C:\\Ops\\PatchCompliance.ps1",
                        "user_account": "svc_patching",
                        "duration": random.randint(20, 180),
                        "exit_code": 0,
                        "description": "Approved patch compliance script execution",
                        "created_at": DummyDataService._random_datetime(2).isoformat(),
                        "timestamp": DummyDataService._random_datetime(2).isoformat(),
                        "created_by": analyst,
                        "tags": ["admin_tooling"],
                        "flagged": False,
                        "highlighted": False,
                        "replies": [],
                    },
                ],
            },
            {
                "title": "Impossible Travel Login Alert from Corporate VPN Egress",
                "description": (
                    "Authentication anomaly appears to be geolocation drift caused by shared VPN egress "
                    "nodes. MFA satisfied and no suspicious follow-on activity in endpoint telemetry."
                ),
                "priority": Priority.LOW,
                "source": "Authentication System",
                "tags": ["identity", "vpn", "noisy_alert"],
                "timeline_items": [
                    {
                        "id": "closure-3-note",
                        "type": "note",
                        "description": (
                            "User confirmed active session from corporate VPN; SOC found no lateral movement indicators."
                        ),
                        "created_at": DummyDataService._random_datetime(2).isoformat(),
                        "timestamp": DummyDataService._random_datetime(2).isoformat(),
                        "created_by": analyst,
                        "tags": ["mfa", "vpn"],
                        "flagged": False,
                        "highlighted": False,
                        "replies": [],
                    },
                    {
                        "id": "closure-3-network",
                        "type": "network_traffic",
                        "source_ip": "10.2.40.9",
                        "destination_ip": "10.10.50.11",
                        "source_port": 443,
                        "destination_port": 443,
                        "protocol": Protocol.TCP.value,
                        "bytes_sent": random.randint(2048, 65536),
                        "bytes_received": random.randint(4096, 131072),
                        "duration": random.randint(30, 240),
                        "description": "Normal VPN control-plane traffic",
                        "created_at": DummyDataService._random_datetime(2).isoformat(),
                        "timestamp": DummyDataService._random_datetime(2).isoformat(),
                        "created_by": analyst,
                        "tags": ["vpn"],
                        "flagged": False,
                        "highlighted": False,
                        "replies": [],
                    },
                ],
            },
            {
                "title": "DNS Beacon Pattern - finance-app01",
                "description": (
                    "Repeated low-volume DNS beacon pattern from finance-app01 to telemetry-update.internal. "
                    "Recent triage indicates recurring non-malicious endpoint telemetry heartbeat."
                ),
                "priority": Priority.LOW,
                "source": "DNS Monitor",
                "tags": ["network", "dns", "possible_duplicate", "noisy_alert"],
                "timeline_items": [
                    {
                        "id": "closure-4-note",
                        "type": "note",
                        "description": "Pattern matches recurring heartbeat from approved telemetry agent.",
                        "created_at": DummyDataService._random_datetime(1).isoformat(),
                        "timestamp": DummyDataService._random_datetime(1).isoformat(),
                        "created_by": analyst,
                        "tags": ["known_pattern"],
                        "flagged": False,
                        "highlighted": False,
                        "replies": [],
                    },
                    {
                        "id": "closure-4-observable",
                        "type": "observable",
                        "observable_type": ObservableType.DOMAIN.value,
                        "observable_value": "telemetry-update.internal",
                        "description": "Internal telemetry endpoint",
                        "created_at": DummyDataService._random_datetime(1).isoformat(),
                        "timestamp": DummyDataService._random_datetime(1).isoformat(),
                        "created_by": analyst,
                        "tags": ["internal_domain"],
                        "flagged": False,
                        "highlighted": False,
                        "replies": [],
                    },
                ],
            },
            {
                "title": "DNS Beacon Pattern - finance-app01",
                "description": (
                    "Second alert with same source/title and matching internal domain IOC. "
                    "Likely duplicate of an already-handled noisy telemetry heartbeat."
                ),
                "priority": Priority.LOW,
                "source": "DNS Monitor",
                "tags": ["network", "dns", "duplicate_candidate", "noisy_alert"],
                "timeline_items": [
                    {
                        "id": "closure-5-note",
                        "type": "note",
                        "description": "Triggered within minutes of earlier equivalent DNS heartbeat alert.",
                        "created_at": DummyDataService._random_datetime(1).isoformat(),
                        "timestamp": DummyDataService._random_datetime(1).isoformat(),
                        "created_by": analyst,
                        "tags": ["repeat_alert"],
                        "flagged": False,
                        "highlighted": False,
                        "replies": [],
                    },
                    {
                        "id": "closure-5-observable",
                        "type": "observable",
                        "observable_type": ObservableType.DOMAIN.value,
                        "observable_value": "telemetry-update.internal",
                        "description": "Internal telemetry endpoint",
                        "created_at": DummyDataService._random_datetime(1).isoformat(),
                        "timestamp": DummyDataService._random_datetime(1).isoformat(),
                        "created_by": analyst,
                        "tags": ["internal_domain"],
                        "flagged": False,
                        "highlighted": False,
                        "replies": [],
                    },
                ],
            },
        ]

    @staticmethod
    async def generate_closure_prone_alerts(db: AsyncSession, count: int = 5) -> List[Alert]:
        """Generate alerts likely to receive closure-oriented triage recommendations."""
        if count <= 0:
            return []

        users = await DummyDataService._get_users_list(db)
        scenarios = DummyDataService._build_closure_prone_alert_scenarios(users)
        alerts: List[Alert] = []

        for i in range(count):
            scenario = scenarios[i % len(scenarios)]
            alert_data = AlertCreate(
                title=scenario["title"],
                description=scenario["description"],
                priority=scenario["priority"],
                source=scenario["source"],
            )

            alert = await alert_service.create_alert(db, alert_data)
            alert.tags = scenario["tags"]
            alert.timeline_items = scenario["timeline_items"]
            alert.created_at = DummyDataService._random_datetime(2)
            alert.updated_at = alert.created_at + timedelta(minutes=random.randint(1, 90))

            await db.commit()
            await db.refresh(alert)
            alerts.append(alert)

        return alerts

    @staticmethod
    def _generate_indicators() -> List[str]:
        """Generate realistic threat indicators."""
        indicator_types = [
            lambda: DummyDataService._random_ip(),
            lambda: f"malicious-domain-{random.randint(1, 100)}.com",
            lambda: f"SHA256:{uuid.uuid4().hex[:32]}",
            lambda: f"trojan_{random.randint(1, 50)}.exe",
            lambda: f"TCP:{random.randint(1, 65535)}",
            lambda: f"suspicious_user_{random.randint(1, 20)}",
            lambda: f"CVE-2024-{random.randint(1000, 9999)}",
        ]

        num_indicators = random.randint(1, 5)
        return [random.choice(indicator_types)() for _ in range(num_indicators)]

    @staticmethod
    async def populate_dummy_data(
        db: AsyncSession,
        cases_count: int = 10,
        alerts_count: int = 20,
        link_some_alerts: bool = True,
        closure_prone_alert_count: int = CLOSURE_PRONE_ALERT_DEFAULT_COUNT,
    ) -> Dict[str, Any]:
        """
        Populate the database with dummy data.

        Args:
            db: Database session
            cases_count: Number of cases to create
            alerts_count: Number of alerts to create
            link_some_alerts: Whether to link some alerts to cases

        Returns:
            Summary of created data
        """
        try:
            # Generate cases
            cases = await DummyDataService.generate_cases(db, cases_count)

            # Generate alerts
            alerts = await DummyDataService.generate_alerts(
                db,
                alerts_count,
                include_closure_prone=closure_prone_alert_count > 0,
                closure_prone_count=closure_prone_alert_count,
            )

            # Link some alerts to cases if requested
            linked_count = 0
            if link_some_alerts and cases and alerts:
                # Link about 30% of alerts to random cases
                alerts_to_link = random.sample(
                    alerts, min(len(alerts), max(1, int(len(alerts) * 0.3)))
                )

                for alert in alerts_to_link:
                    case = random.choice(cases)
                    alert.case_id = case.id
                    alert.status = AlertStatus.ESCALATED
                    linked_count += 1

                await db.commit()

            return {
                "success": True,
                "message": "Dummy data populated successfully",
                "data": {
                    "cases_created": len(cases),
                    "alerts_created": len(alerts),
                    "random_alerts_created": alerts_count,
                    "closure_prone_alerts_created": min(
                        len(alerts),
                        max(0, closure_prone_alert_count),
                    ),
                    "alerts_linked_to_cases": linked_count,
                    "case_ids": [case.id for case in cases],
                    "alert_ids": [alert.id for alert in alerts],
                },
            }

        except Exception as e:
            await db.rollback()
            return {
                "success": False,
                "message": f"Error populating dummy data: {str(e)}",
                "data": None,
            }

    @staticmethod
    async def clear_all_data(db: AsyncSession) -> Dict[str, Any]:
        """Clear all cases and alerts from the database."""
        try:
            from sqlalchemy import text

            # Delete in proper order due to foreign key constraints
            await db.execute(text("DELETE FROM audit_logs"))
            await db.execute(text("DELETE FROM alerts"))
            await db.execute(text("DELETE FROM cases"))
            await db.commit()

            return {"success": True, "message": "All data cleared successfully"}
        except Exception as e:
            await db.rollback()
            return {"success": False, "message": f"Error clearing data: {str(e)}"}


# Create instance for easy importing
dummy_data_service = DummyDataService()
