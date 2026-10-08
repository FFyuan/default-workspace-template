# files

Files: the workspace's file browser, the `files` app of the desktop's launcher,
supervised as the `files` program declared in
`system/supervisord.conf.d/files.conf`. There is no Python package here: the
program line registers `app.toml` and the dufs port 8300 through
`system/scripts/forward_port.py`, then runs
`dufs --allow-all --bind 127.0.0.1 --port 8300 --assets system/apps/files/static /`.

The server is [dufs](https://github.com/sigoden/dufs), a single static binary
installed at image build by `system/scripts/install_dufs.sh` (version and
per-arch sha256 pinned there). It serves the container's filesystem root, so a
window opened at the workspace can walk up to anything the workspace user can
read; it is bound to loopback with all operations enabled (browse, preview,
upload, rename, delete): the workspace origin is what gates access, exactly as
for every other registered app.

## The frontend

`frontend/` is a Mithril app on the shared `system/libs/workspace_ui` library,
one package of the npm workspace at `system/package.json`. Its vite build writes
`static/` (gitignored), the directory dufs is handed as `--assets`. dufs serves
that one `index.html` for every folder and every file page, filling in the
page's data (base64 JSON in `#index-data`: a folder's listing, or the facts of
the file a `?view` / `?edit` page is for) and the prefix it serves the bundle
under (`__ASSETS_PREFIX__`). Everything else goes over dufs's HTTP API, which
`frontend/src/models/dufs.ts` wraps: `?json` lists a folder, `?q=` searches
under it, `?zip` archives it, PUT writes, MKCOL makes a folder, MOVE renames,
DELETE removes. dufs serves its assets directory flat and reads `index.html`
once at startup, so the bundle keeps fixed names (`index.js`, `index.css`) and
the page asks for them with a per-build `?v=` stamp.

A folder window has a sidebar, a toolbar (the path, the view switcher, the +
button, and the view options), and the folder. The sidebar lists Shortcuts
(Workspace and Uploads, each shown when it exists) and Connected folders: the
folders Imbue Studio syncs into the workspace from the user's computers, under
`~/synced_folders/<device id>/<path on that computer>` (the file-sharing
skill). Nothing records which folder along that path is the one shared, so
`models/connectedFolders.ts` reads it off the tree: the path runs down through
folders holding a single folder and nothing else, and the shared folder is
where that stops. Its width is dragged from its edge (double-click puts it
back) and kept with the other preferences. Jumping to a sidebar row starts the
column view afresh there; drilling down into a folder that happens to be a
shortcut keeps the columns already open. There are no back and forward
buttons (Cmd/Ctrl+[ and ] still move through the history), and the model can
still search a folder (dufs's `?q=`), but the toolbar offers no search field
for now.

The folder is laid out as icons (image files as thumbnails), a list with
sortable columns, or columns that open to the right as folders are chosen and
end in a preview of the file chosen. The layout, the sort order, and whether
"system files" (dotted names) show are kept in the browser's localStorage and
shared by every window.

- Click selects, Cmd/Ctrl-click toggles, Shift-click extends; a double-click (or
  Enter) opens. F2 renames in place, Delete deletes after a confirmation,
  Cmd/Ctrl+A selects everything, Cmd/Alt+Up goes up a folder, Cmd+[ and Cmd+]
  go back and forward, and typing a name jumps to it.
- Right-click on an entry offers Open, Open in New Window (a folder), Edit (a
  text file), Download (a folder as a zip), Rename, Copy Path, and Delete,
  ahead of the workspace's own element-menu rows; right-click on a folder's
  background offers New Folder, New File, Upload Files, and Upload Folder,
  which the + button offers too.
- Files dragged in from outside upload into the folder under the pointer (a
  folder's tile or row, a column, a shortcut, a path segment) or else the folder
  on show, folders included; entries dragged onto a folder move into it. An
  upload whose name is taken asks whether to replace it or keep both. Uploads
  show their progress in a panel at the bottom right.

Under 700px of the frame's own width the window lays itself out for a phone:
the sidebar floats over the folder from a button at the toolbar's start, there
is no column view, one tap opens, and every
entry carries a "..." button with its menu.

## Opening a folder or a file

The manifest's one launch path is `/home/user/workspace/` with an optional `path`
param (an absolute path, since dufs serves the filesystem root), so a plain launch
opens the workspace folder and the shell opens a Files window at
`/home/user/workspace/?path=<folder>` when asked for one (`layout.py open files
--path /home/user/workspace/data/notes/` is the same thing). The page shows that
folder in place and reports it as its location (`shell:location`,
desktop-interface contracts.md section 7), as it does after every move, so the
window's stored path follows, a reload reopens the folder, and the window is
titled after it.

Framed by the shell, opening a file opens its `?view` page in a Files window of
its own, and Edit its `?edit` page, each through the app contract's `shell:open`
with `ifPresent: "focus"`, so a window already on that page is raised instead of
a second one opening. On a phone, or outside the workspace, the page opens in
place. A view page draws images, video, audio, and PDFs in the browser's own
viewers and text as text; an edit page is a text editor that saves with Save or
Cmd/Ctrl+S. Both lead back to the folder and offer Download, Rename, Copy Path,
and Delete.

`frontend/public/404.html` is Files' own "not found" page, copied into the
build as-is: dufs serves a `404.html` found in its `--assets` directory, with
status 404, for every path that does not exist (it answers a client it takes
for a script, such as curl, with a bare "Not Found" instead). dufs fills in no
placeholders there, so the page reads the path asked for from its own address,
names it, links the nearest folder above it that exists (asking each folder's
`?json` listing, whose `dir_exists` says whether it is there), and posts the
location beacon, titled after the missing name.

When `install_dufs.sh` bumps the pinned dufs version, check the placeholders,
the listing JSON, and the verbs `models/dufs.ts` relies on against the new
release.

## Tests

`system/test_app_manifests.py` checks the manifest against the program line, and
`system/test_supervisord_layout.py` the program block. The frontend's own
vitest suites sit beside its sources (`npm test` at `system/`).
`test_files_app.py` (marked `browser`) serves the build from a stand-in for
dufs (`conftest.py`, over a temporary folder) and drives the app in Chromium:
the three views, selection, rename, delete, new folders, uploads by picker and
by drop, the sidebar's rows and resizing, the phone layout, and the file
pages. The shell's
`test_e2e.py` runs the real dufs, where installed, to check that files open in
workspace windows.
