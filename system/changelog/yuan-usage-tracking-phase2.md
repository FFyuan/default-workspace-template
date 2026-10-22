Locked the routines library's new dependency on `workspace-usage`. Phase 2 of usage tracking needs the mngr commit with the harness writers and the create-time usage context; the mngr pin has to move to it before this ships.

Locked `workspace-usage`'s new dependency on `imbue-mngr-usage`, and updated the library and service lists for the file-based usage design.
