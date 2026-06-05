#!/usr/bin/env python3
"""Backward-compatibility shim — delegates to ``lab_connectors.testing.audit_markers``.

This script exists so workflows that reference ``.github/scripts/audit_test_markers.py``
continue to work.  New code should use the ``audit-test-markers`` CLI command directly
(installed via lab-connectors ``[project.scripts]``).

Remove this shim once all repos have migrated to the CLI command.
"""

from lab_connectors.testing.audit_markers import main

if __name__ == "__main__":
    raise SystemExit(main())
