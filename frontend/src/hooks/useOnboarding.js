import { useState, useEffect } from 'react'

const STORAGE_KEY = 'mwtn_onboarding_complete'

export function useOnboarding() {
  const [showOnboarding, setShowOnboarding] = useState(() => {
    try {
      const v = localStorage.getItem(STORAGE_KEY)
      return v !== 'true'
    } catch (e) {
      return true
    }
  })

  useEffect(() => {
    try {
      const v = localStorage.getItem(STORAGE_KEY)
      if (v === null) {
        setShowOnboarding(true)
      } else {
        setShowOnboarding(v !== 'true')
      }
    } catch (e) {
      // ignore localStorage errors (e.g. SSR or disabled storage)
    }
  }, [])

  function completeOnboarding() {
    try {
      localStorage.setItem(STORAGE_KEY, 'true')
    } catch (e) {
      // ignore
    }
    setShowOnboarding(false)
  }

  return { showOnboarding, completeOnboarding }
}
