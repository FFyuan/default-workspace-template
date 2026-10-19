The image lightbox's Download works inside Imbue Studio. Before, it asked for the image with a `download` link, whose request went without the workspace's session, so the download failed.

- Download of the workspace's own image goes through the shared `startDownload` helper, and the server serves an image asked for with `?download` as an attachment under its own name.

- A failed download says so in the lightbox's title. An image from another site still opens in a new tab.
