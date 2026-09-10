# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: full-flow.spec.ts >> Sobes mode >> starts sobes and shows first question
- Location: tests/e2e/full-flow.spec.ts:115:3

# Error details

```
Error: locator.click: Target page, context or browser has been closed
Call log:
  - waiting for getByRole('button', { name: /Начать собеседование|Начать/ })
    - locator resolved to <button class="_button_yhby6_1 _success_yhby6_62 ">Начать собеседование</button>
  - attempting click action
    2 × waiting for element to be visible, enabled and stable
      - element is not stable
    - retrying click action
    - waiting 20ms
    - waiting for element to be visible, enabled and stable
    - element is not stable
  - retrying click action
    - waiting 100ms

```

```
Error: write EPIPE
```