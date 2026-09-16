# README screenshots

These unmodified PNG screenshots show packaged **Hantek Studio 0.3.0** in an
isolated demo workspace on 16 September 2026. They show the implemented app, not
the ImageGen design concept. All displayed signals and captures are simulated.
No USB device was enumerated or opened for this screenshot session.

| File | View |
| --- | --- |
| `workspace.png` | Screen preview, capture actions and session overview |
| `controls.png` | Relative front-panel controls beside the simulated screen |
| `capture-library.png` | Saved demo capture, name, notes and PNG export |

Original screenshots and the session result remain under the ignored directory
`.local/readme-screenshots/7d28ca11-5127-4bb6-8029-cfcce9653ec2/`. The packaged
app also passed all 16 redesign UI checks; evidence is in
`.local/desktop-redesign-ui-tests/b6410838-8adf-4091-9d34-bc41c91b66e6/`.
Neither run accessed hardware, and neither reported renderer errors.

To refresh these images, launch the current packaged app with `--demo` and
separate absolute `HANTEK_STUDIO_PROFILE` and `HANTEK_STUDIO_DATA_DIR` overrides.
Connect the demo, save a simulated capture, and take screenshots of Workspace,
Controls and Captures. Use full-page screenshots where needed, preserve the
visible Demo labels and keep scope pixels unmodified. Inspect all images before
copying them here and update the version/captions in the main README. See the
[desktop guide](../DESKTOP_APP.md) for isolated profiles and packaged UI checks.

Keep private hardware captures, device identities and operation logs in ignored
local directories. The workspace image shows only the repository's generic
test-storage path; no personal home path or device identity is displayed.
