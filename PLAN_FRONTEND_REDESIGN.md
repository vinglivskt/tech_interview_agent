# Frontend redesign

## Direction

Build a premium developer-tool interface without changing the interview flows,
API contracts, or persisted user data. The UI uses an adaptive app shell:
sidebar navigation on desktop and bottom navigation on mobile.

## Implementation

- Keep the existing state-based views and feature containers; add a shared shell
  for navigation, profile context, theme control, and the statistics shortcut.
- Refresh the dashboard, feature frames, setup cards, question cards, results,
  and statistics with a consistent token-based design system.
- Use semantic interactive elements, keyboard focus states, 44px touch targets,
  responsive layouts, and reduced-motion support.
- Keep all existing accessible names, test IDs, localStorage keys, API calls,
  and Playwright DOM contracts intact.

## Verification

- `npm run typecheck`
- `npm run lint`
- `npm run test`
- `npm run test:e2e` when the local API stack is running
