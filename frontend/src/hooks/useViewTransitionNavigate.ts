import { useNavigate, NavigateOptions, To } from 'react-router-dom'
import { useCallback } from 'react'

/**
 * A wrapper around useNavigate that enables view transitions by default.
 * This provides smooth fade transitions between route changes using the
 * native View Transitions API supported by React Router.
 */
export function useViewTransitionNavigate() {
  const navigate = useNavigate()

  return useCallback(
    (to: To | number, options?: NavigateOptions) => {
      if (typeof to === 'number') {
        // For go(-1), go(1), etc. - can't add options
        navigate(to)
      } else {
        navigate(to, { viewTransition: true, ...options })
      }
    },
    [navigate]
  )
}
