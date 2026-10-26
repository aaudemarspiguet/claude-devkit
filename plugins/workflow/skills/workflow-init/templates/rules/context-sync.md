---
name: context-sync
description: Keep the context hierarchy (nested CLAUDE.md files) from going stale as source changes
{{PATHS}}---

# Keep the Context Hierarchy in Sync

After any change to a file under a directory that has its own `CLAUDE.md` (or `README.md`, if
your team built the hierarchy that way), check whether that file still accurately describes the
directory — then say so and offer to update it, rather than waiting to be asked. A parent
directory's context file only needs revisiting if the change affects what a reader would be
told from the top down (a new module, a changed responsibility) — not for every line-level edit.

Never regenerate a context file by re-reading the whole directory's source from scratch — read
the existing file first and edit only what's actually stale.
