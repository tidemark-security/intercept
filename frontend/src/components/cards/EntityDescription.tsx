import { FileText } from "lucide-react";

import MarkdownContent from "@/components/data-display/MarkdownContent";
import { cn } from "@/utils/cn";

interface EntityDescriptionProps {
  description: string;
  className?: string;
  showFullCodeBlocks?: boolean;
}

export function EntityDescription({
  description,
  className,
  showFullCodeBlocks,
}: EntityDescriptionProps) {
  return (
    <section aria-label="Description" className={cn("flex min-w-0 flex-col gap-2", className)}>
      <h3 className="flex items-center gap-2 text-heading-3 font-heading-3 text-default-font">
        <FileText aria-hidden="true" className="h-4 w-4 shrink-0" />
        Description
      </h3>
      <MarkdownContent content={description} showFullCodeBlocks={showFullCodeBlocks} />
    </section>
  );
}
