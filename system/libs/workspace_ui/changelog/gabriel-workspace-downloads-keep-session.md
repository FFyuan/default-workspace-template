New `startDownload` helper, which every workspace page now uses to download a file of its own.

- It loads the file in a hidden frame instead of clicking a link with a `download` attribute. Inside Imbue Studio, the browser sends a `download` link's request without the workspace's session cookie, so the workspace refused it. The browser then offered to save the refusal, named `download.txt` (or the file's own name with `.txt` in place of its extension).

- If the server answers with something other than the file, the helper hands the page a note, "Couldn't download <name>", with the server's own words when it sent plain text.
