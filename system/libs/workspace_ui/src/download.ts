/**
 * Start a browser download of ``url`` (on the page's own origin) by loading it in a hidden frame; the server's
 * ``Content-Disposition: attachment`` names the file. If the server answers with something other than a file,
 * ``onFailure`` gets a note saying ``name`` could not be downloaded, with the server's words when it answered in
 * plain text.
 *
 * Not a link with a ``download`` attribute: Imbue Studio frames the workspace from another site, so the workspace's
 * session cookie is partitioned to that framing, and the browser sends a ``download`` link's request without it --
 * the workspace refuses it, and the browser saves the refusal. A frame's load carries the cookie like any page's.
 * A download never finishes a frame's load, so a frame that loads showed the server's answer instead.
 */
export function startDownload(document: Document, url: string, name: string, onFailure: (note: string) => void): void {
  const frame = document.createElement("iframe");
  frame.hidden = true;
  frame.addEventListener("load", () => {
    const answer = frame.contentDocument;
    const words = answer?.contentType === "text/plain" ? (answer.body?.textContent ?? "").trim() : "";
    frame.remove();
    onFailure(words === "" ? `Couldn't download ${name}.` : `Couldn't download ${name}: ${words}`);
  });
  frame.src = url;
  // Left in place once the download starts: the page cannot tell when that is, and removing the frame before its
  // response arrives cancels the download.
  document.body.appendChild(frame);
}
