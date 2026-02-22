import { Link as RouterLink, LinkProps } from 'react-router-dom'
import { forwardRef } from 'react'

/**
 * A wrapper around React Router's Link that enables view transitions by default.
 * This provides smooth fade transitions between route changes using the
 * native View Transitions API.
 */
export const Link = forwardRef<HTMLAnchorElement, LinkProps>(
  ({ viewTransition = true, ...props }, ref) => {
    return <RouterLink ref={ref} viewTransition={viewTransition} {...props} />
  }
)

Link.displayName = 'Link'
