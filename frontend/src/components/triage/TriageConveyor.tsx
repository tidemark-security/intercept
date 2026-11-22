import type { CSSProperties } from "react";
import { Bot, Cpu, Fingerprint, Network, ShieldCheck, Terminal, Zap } from "lucide-react";

import { IconWrapper } from "@/utils/IconWrapper";
import { cn } from "@/utils/cn";
import styles from "./TriageConveyor.module.css";

const conveyorIcons = [ShieldCheck, Terminal, Fingerprint, Cpu, Network, Zap];

export function TriageConveyor({ className }: { className: string }) {
  return (
    <span aria-hidden="true" data-robot-state="in-progress" className={cn(styles.conveyor, className)}>
      <span className={styles.track}>
        {conveyorIcons.map((Icon, index) => (
          <span key={index} className={styles.item} style={{ "--item-index": index } as CSSProperties}>
            <IconWrapper className="text-heading-3"><Icon /></IconWrapper>
          </span>
        ))}
      </span>
      <IconWrapper className={styles.robot}><Bot /></IconWrapper>
    </span>
  );
}
