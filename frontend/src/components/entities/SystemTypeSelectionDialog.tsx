
"use client";

import React from "react";

import { cn } from "@/utils/cn";
import { Accordion } from "@/components/misc/Accordion";
import { Badge } from "@/components/data-display/Badge";
import { IconWithBackground } from "@/components/misc/IconWithBackground";
import { RadioCardGroup } from "@/components/forms/RadioCardGroup";

import {
  Activity,
  Apple,
  Archive,
  ArrowRightLeft,
  ArrowUpRight,
  BarChart,
  BarChart3,
  Bot,
  Camera,
  Car,
  Cpu,
  Database,
  Factory,
  Folder,
  GitBranch,
  Globe,
  HardDrive,
  Heart,
  HelpCircle,
  Home,
  Laptop,
  Lock,
  Mail,
  Monitor,
  MoreHorizontal,
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
} from "lucide-react";
interface SystemTypeSelectionDialogRootProps extends Omit<
  React.HTMLAttributes<HTMLDivElement>,
  "title"
> {
  title?: React.ReactNode;
  searchField?: React.ReactNode;
  compact?: boolean;
  className?: string;
}

const SystemTypeSelectionDialogRoot = React.forwardRef<
  HTMLDivElement,
  SystemTypeSelectionDialogRootProps
>(function SystemTypeSelectionDialogRoot(
  {
    title,
    searchField,
    compact = false,
    className,
    ...otherProps
  }: SystemTypeSelectionDialogRootProps,
  ref,
) {
  return (
    <div
      className={cn(
        "group/5b56ce43 flex h-full w-full flex-col items-start",
        { "flex-col flex-nowrap gap-4": compact },
        className,
      )}
      ref={ref}
      {...otherProps}
    >
      <div
        className={cn(
          "flex w-full flex-col items-start gap-4 border-b border-solid border-neutral-border px-6 py-6",
          { "px-0 py-0": compact },
        )}
      >
        <div className="flex w-full items-center gap-4">
          {title ? (
            <span
              className={cn(
                "grow shrink-0 basis-0 text-heading-3 font-heading-3 text-default-font",
                { "text-caption-bold font-caption-bold": compact },
              )}
            >
              {title}
            </span>
          ) : null}
        </div>
        <div className="flex w-full items-center gap-2">
          {searchField ? (
            <div className="flex grow shrink-0 basis-0 items-center gap-2">
              {searchField}
            </div>
          ) : null}
        </div>
      </div>
      <div
        className={cn(
          "flex w-full flex-col items-start px-6 py-6 overflow-auto",
          { "px-0 py-0": compact },
        )}
      >
        <RadioCardGroup className="h-auto w-full flex-none">
          <div className="flex grow shrink-0 basis-0 flex-col items-start gap-4">
            <div className="flex w-full items-start gap-2">
              <RadioCardGroup.RadioCard
                className="h-16 w-40 flex-none"
                hideRadio={true}
                value="28ee692f"
              >
                <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                  <HelpCircle className="text-body font-body text-default-font" />
                  <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                    Other/Unknown
                  </span>
                </div>
              </RadioCardGroup.RadioCard>
            </div>
            <div className="flex w-full flex-col items-start rounded-md bg-neutral-50">
              <Accordion
                trigger={
                  <div className="flex w-full items-center gap-4 px-2 py-2">
                    <IconWithBackground
                      size={compact ? "small" : "medium"}
                      icon={<Laptop />}
                      bevel={false}
                    />
                    <span
                      className={cn(
                        "grow shrink-0 basis-0 text-heading-3 font-heading-3 text-default-font",
                        { "text-caption-bold font-caption-bold": compact },
                      )}
                    >
                      Enterprise Systems: End User
                    </span>
                    <Badge variant="neutral">5</Badge>
                    <Accordion.Chevron />
                  </div>
                }
                defaultOpen={compact ? false : true}
              >
                <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2 px-2 py-2">
                  <div className="flex grow shrink-0 basis-0 flex-wrap items-center gap-2">
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="327a9ada"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Monitor className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Workstation
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="ca814db9"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Laptop className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Laptop
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="8ddef915"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Apple className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          iOS Mobile
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="c1cfbd5e"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Bot className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Android Mobile
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="16eb5fe6"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Smartphone className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Other Mobile
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                  </div>
                </div>
              </Accordion>
            </div>
            <div className="flex w-full flex-col items-start bg-neutral-50">
              <Accordion
                trigger={
                  <div className="flex w-full items-center gap-4 px-2 py-2">
                    <IconWithBackground
                      size={compact ? "small" : "medium"}
                      icon={<Server />}
                      bevel={false}
                    />
                    <span
                      className={cn(
                        "grow shrink-0 basis-0 text-heading-3 font-heading-3 text-default-font",
                        { "text-caption-bold font-caption-bold": compact },
                      )}
                    >
                      Enterprise Systems: Server
                    </span>
                    <Badge variant="neutral">16</Badge>
                    <Accordion.Chevron />
                  </div>
                }
                defaultOpen={compact ? false : true}
              >
                <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2 px-2 py-2">
                  <div className="flex grow shrink-0 basis-0 flex-wrap items-center gap-2">
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="d1c7da47"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Globe className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Web Server
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="16113466"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Database className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Database Server
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="b8d1f931"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Package className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Application Server
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="4acc1313"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Folder className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          File Server
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="dd91fcf5"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Mail className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Mail Server
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="974786eb"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Navigation className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Dns Server
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="740fbf8f"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Settings className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Domain Controller
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="ca416079"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Wifi className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Router
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="d7710676"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Shuffle className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Switch
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="6b6920dc"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Shield className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Firewall
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="23bd13e7"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <BarChart3 className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Load Balancer
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="94a4c484"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <ArrowRightLeft className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Proxy Server
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="b7428d2f"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <ArrowUpRight className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Jump Host
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="7cf7dff6"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Lock className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Vpn Server
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="8030de9f"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <HardDrive className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Mainframe
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="dceadc1a"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Printer className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Printer
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                  </div>
                </div>
              </Accordion>
            </div>
            <div className="flex w-full flex-col items-start rounded-md bg-neutral-50">
              <Accordion
                trigger={
                  <div className="flex w-full items-center gap-4 px-2 py-2">
                    <IconWithBackground
                      size={compact ? "small" : "medium"}
                      icon={<Factory />}
                      bevel={false}
                    />
                    <span
                      className={cn(
                        "grow shrink-0 basis-0 text-heading-3 font-heading-3 text-default-font",
                        { "text-caption-bold font-caption-bold": compact },
                      )}
                    >
                      ICS: Industrial Control Systems
                    </span>
                    <Badge variant="neutral">9</Badge>
                    <Accordion.Chevron />
                  </div>
                }
                defaultOpen={compact ? false : true}
              >
                <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2 px-2 py-2">
                  <div className="flex grow shrink-0 basis-0 flex-wrap items-center gap-2">
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="f3675777"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Server className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Control Server
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="6f2edf6c"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Monitor className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          HMI
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="2c3843dd"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Cpu className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          PLC
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="eb3dd6c6"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Radio className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          RTU
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="80fe0630"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Zap className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          IED
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="cbb3518a"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Archive className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Data Historian
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="dd58863f"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <GitBranch className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Data Gateway
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="def0d586"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <ShieldCheck className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Safety Controller
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="ad1e42d0"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Activity className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Field IO
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                  </div>
                </div>
              </Accordion>
            </div>
            <div className="flex w-full flex-col items-start rounded-md bg-neutral-50">
              <Accordion
                trigger={
                  <div className="flex w-full items-center gap-4 px-2 py-2">
                    <IconWithBackground
                      size={compact ? "small" : "medium"}
                      icon={<BarChart />}
                      bevel={false}
                    />
                    <span
                      className={cn(
                        "grow shrink-0 basis-0 text-heading-3 font-heading-3 text-default-font",
                        { "text-caption-bold font-caption-bold": compact },
                      )}
                    >
                      IOT: Internet of Things
                    </span>
                    <Badge variant="neutral">9</Badge>
                    <Accordion.Chevron />
                  </div>
                }
                defaultOpen={compact ? false : true}
              >
                <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2 px-2 py-2">
                  <div className="flex grow shrink-0 basis-0 flex-wrap items-center gap-2">
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="a996704f"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Thermometer className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Sensor
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="bb1c1fb9"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Camera className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Camera
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="09ebc8a0"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Home className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Smart Home
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="6f0f7e95"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Watch className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Wearable
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="ac23eea6"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Car className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Vehicle
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="497e2530"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Heart className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Medical
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="75dff672"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <Refrigerator className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Appliance
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="e4553315"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <GitBranch className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Gateway
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                    <RadioCardGroup.RadioCard
                      className="h-16 w-40 flex-none"
                      hideRadio={true}
                      value="fd7ed298"
                    >
                      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-2">
                        <MoreHorizontal className="text-body font-body text-default-font" />
                        <span className="w-full whitespace-nowrap text-heading-3 font-heading-3 text-default-font">
                          Other
                        </span>
                      </div>
                    </RadioCardGroup.RadioCard>
                  </div>
                </div>
              </Accordion>
            </div>
          </div>
        </RadioCardGroup>
      </div>
    </div>
  );
});

export const SystemTypeSelectionDialog = SystemTypeSelectionDialogRoot;
