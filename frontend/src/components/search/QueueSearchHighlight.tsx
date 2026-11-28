import { Children, cloneElement, isValidElement, useMemo, type ReactNode } from "react";
import { SearchHighlight } from "./SearchHighlight";
import { buildQueueSearchPattern, QueueSearchPatternContext, splitQueueSearchText, useQueueSearchPattern } from "./queueSearchMatches";

export function QueueSearchHighlightScope({ query, children }: { query: string; children: ReactNode }) {
  const pattern = useMemo(() => buildQueueSearchPattern(query), [query]);
  return <QueueSearchPatternContext.Provider value={pattern}>{children}</QueueSearchPatternContext.Provider>;
}

function decorate(node: ReactNode, pattern: RegExp): ReactNode {
  if (typeof node === "string" || typeof node === "number") {
    const parts = splitQueueSearchText(String(node), pattern);
    return parts ? parts.map(({ text, match }, index) => match
      ? <SearchHighlight key={index}>{text}</SearchHighlight>
      : text) : node;
  }
  if (Array.isArray(node)) return Children.map(node, (child) => decorate(child, pattern));
  if (isValidElement<{ children?: ReactNode; "aria-hidden"?: boolean | "true" | "false" }>(node)
    && node.props.children != null && node.props["aria-hidden"] !== true && node.props["aria-hidden"] !== "true") {
    return cloneElement(node, undefined, decorate(node.props.children, pattern));
  }
  return node;
}

/** Only decorate display text. Raw values are still used for links, editing and copying. */
export function QueueSearchText({ children }: { children: ReactNode }) {
  const pattern = useQueueSearchPattern();
  return <>{pattern ? decorate(children, pattern) : children}</>;
}
