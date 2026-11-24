---
name: frontend-fix-and-report
description: Fix a frontend bug on a new branch, test the real UI interactively, capture before-and-after screenshots and short videos, and publish a mobile-friendly HTML test report on ChatGPT Sites. Use for frontend changes that call for browser evidence and a hosted report.
---

# Frontend fix and report

Take a frontend issue from a verified base revision through a tested change and a shareable report. Use the repository, base branch, bug description, and test environment supplied in the request. Resolve routine details from the active checkout and existing project setup.

## 1. Branch from the requested base

- Read the repository's instructions, check its remote and working tree, and preserve existing changes. Fetch the requested base from the remote when the task calls for its current revision. For a request such as “current release branch,” use the project's release conventions and remote refs to identify it. Record the ref and full commit SHA.
- Create a descriptive feature branch from that SHA. Use a separate worktree or checkout if switching branches would affect existing work. When the request calls for delivery on GitHub, use the connected GitHub tools when suitable and verify the remote branch base. Keep later pushes scoped to the new branch.
- Turn the request into a short set of user-visible checks. Include any navigation, refresh, browser-tab, device, or account behavior that is part of the issue.

## 2. Reproduce and record the baseline

- Run the app as the project documents. Use its existing test environment, seeded local services, or deterministic API fixtures as appropriate. Capture what the app actually displays and note which services are real or mocked.
- Exercise the issue through the UI before changing code. Use the available browser or desktop skill for visible interaction and the project's browser runner for repeatable flows. Playwright is suitable when it is available and the app is built for browser testing.
- Save a screenshot of the state that demonstrates the problem and a short recording of the interaction that leads to it. Keep each clip focused on one flow and leave enough time to see the outcome. Use test data and keep sign-in, credentials, private records, and unrelated tabs out of the captures.
- If the baseline cannot be reproduced, record the attempted steps and the specific limitation. Continue with the fix and any useful tests supported by the evidence.

## 3. Write the fix and test it

- Make the smallest complete change through the normal frontend entry points. Reuse the project's components and state conventions. Add targeted regression coverage that would catch a return of the bug.
- Repeat the baseline steps on the patched build with comparable inputs and viewport. Assert the user-visible outcome and, when relevant, verify that the underlying request or displayed data agrees with the controls. Exercise any additional scenarios needed by the change.
- If the requirement concerns isolation between browser tabs, exercise two pages in the same browser context and origin. Give each a different state, alternate interactions, and verify both states after returning.
- Save matching after screenshots and short recordings. Open the screenshots and play the clips to check that they show the intended steps and outcomes.
- Run the project's relevant tests, typecheck, build, and any required lint checks. Record the exact commands, revisions, browser, results, and limits. If the development server is blocked, try the project's production build and preview or another supported test setup.
- Commit and push the fix and its regression tests when authorized for the feature branch. Verify the final revision and keep the HTML, screenshots, and recordings outside the product commit. Open a pull request only when requested.

## 4. Write and verify the HTML report

- Save an uncommitted HTML report with the user problem, reproducible steps, observed baseline behavior, fix, and test outcomes. Include the base and patched revisions, meaningful screenshot captions, and playback controls for the clips. Mark failures, skipped checks, and fixture-backed tests accurately.
- Make the page readable on phones with a viewport declaration, a layout that stacks at narrow widths, and media that fits its container. Use descriptive alt text, video posters, and short clips. Prefer separately served H.264 MP4 video with fast start for the hosted copy when conversion is available.
- Load the HTML through a supported browser preview when available. Check that screenshots load, captions match the evidence, and recordings play. Check a phone-sized viewport if the browser tools support it, and report any verification limit.

## 5. Publish on ChatGPT Sites

- Read and follow the current Sites skill. Create a separate buildless Site with the report as `dist/index.html` and its referenced assets under `dist/`. Use the same Site ID throughout registration, source packaging, publication, and recovery. Use the Site's own source repository and keep the product report uncommitted.
- Publish privately by default for the signed-in requester. Preserve the audience of an existing Site and follow any explicit sharing instructions. Keep source credentials out of shell arguments, saved files, and output.
- Verify that the exact packaged source revision was saved and deployed. Poll a pending deployment to a terminal state and return the actual deployed URL. Check the live report when permitted. If it opens at the ChatGPT sign-in screen, give the requester the Site URL for the same account and describe the level of verification accurately.
- If Sites or publication is unavailable, complete the local report and include the actual blocker. Preserve the draft Site and deployment state for recovery when applicable.

Finish with the new branch and revision, the test results and material limits, the private Site link, and the local report path.
