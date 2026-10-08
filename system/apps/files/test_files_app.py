"""Files, driven in a real browser over a stand-in for dufs on a temporary folder (see conftest.py).

Every change a test makes goes through the app's own controls and is read back off the disk.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from playwright.sync_api import Locator, Page, expect

pytestmark = [pytest.mark.browser, pytest.mark.timeout(60)]

PHONE = (393, 852)

OpenFilesPage = Callable[..., Page]


def _entry(page: Page, path: str) -> Locator:
    return page.locator(f'[data-entry-path="{path}"]')


def _shown_paths(page: Page) -> list[str]:
    return page.locator("[data-entry-path]").evaluate_all(
        "els => els.map(el => el.dataset.entryPath)"
    )


def test_a_folder_shows_its_entries_as_icons_folders_first_with_system_files_hidden(
    open_files_page: OpenFilesPage,
) -> None:
    page = open_files_page("/")
    expect(page.locator(".files-tile")).to_have_count(4)
    assert _shown_paths(page) == ["/photos/", "/projects/", "/notes.txt", "/README.md"]
    expect(page.locator(".files-status-text")).to_have_text("4 items")

    page.locator('[data-action="options"]').click()
    page.locator('[data-menu-row="show-hidden"]').click()
    expect(page.locator(".files-tile")).to_have_count(5)
    assert "/.env" in _shown_paths(page)


def test_the_list_sorts_by_its_column_headers(open_files_page: OpenFilesPage) -> None:
    page = open_files_page("/")
    page.locator('[data-view-mode="list"]').click()
    expect(page.locator(".files-list-header")).to_be_visible()
    assert _shown_paths(page) == ["/photos/", "/projects/", "/notes.txt", "/README.md"]

    page.locator('[data-sort="name"]').click()
    expect(page.locator('[data-sort="name"]')).to_have_attribute(
        "aria-sort", "descending"
    )
    assert _shown_paths(page) == ["/projects/", "/photos/", "/README.md", "/notes.txt"]

    page.locator('[data-sort="size"]').click()
    assert _shown_paths(page)[2:] == ["/README.md", "/notes.txt"]


def test_columns_open_to_the_right_and_end_in_a_preview_of_the_chosen_file(
    open_files_page: OpenFilesPage,
) -> None:
    page = open_files_page("/")
    page.locator('[data-view-mode="columns"]').click()
    page.locator('.files-column [data-entry-path="/projects/"]').click()
    page.locator('.files-column [data-entry-path="/projects/app/"]').click()
    page.locator('.files-column [data-entry-path="/projects/app/main.py"]').click()

    expect(page.locator(".files-column")).to_have_count(4)
    expect(page.locator(".files-preview-text")).to_have_text('print("hi")\n')
    expect(page).to_have_url(page.url.split("/projects")[0] + "/projects/app/")

    page.keyboard.press("ArrowLeft")
    expect(_entry(page, "/projects/app/")).to_have_attribute("aria-selected", "true")
    expect(page.locator(".files-preview")).to_have_count(0)


def test_double_clicking_a_folder_opens_it_and_back_returns(
    open_files_page: OpenFilesPage,
) -> None:
    page = open_files_page("/")
    _entry(page, "/projects/").dblclick()
    expect(_entry(page, "/projects/app/")).to_be_visible()
    assert page.url.endswith("/projects/")

    page.locator('[data-action="back"]').click()
    expect(_entry(page, "/projects/")).to_be_visible()
    assert page.url.endswith("/")
    page.locator('[data-action="forward"]').click()
    expect(_entry(page, "/projects/app/")).to_be_visible()


def test_f2_renames_an_entry_in_place_and_refuses_a_slash(
    open_files_page: OpenFilesPage, files_root: Path
) -> None:
    page = open_files_page("/")
    _entry(page, "/notes.txt").click()
    page.keyboard.press("F2")
    field = page.locator(".files-rename-field")
    expect(field).to_be_focused()
    page.keyboard.type("a/b")
    page.keyboard.press("Enter")
    expect(page.locator(".files-rename-error")).to_have_text(
        'A name can\'t contain "/".'
    )

    field.fill("journal.txt")
    page.keyboard.press("Enter")
    expect(_entry(page, "/journal.txt")).to_be_visible()
    assert (files_root / "journal.txt").read_text() == "first line\nsecond line\n"
    assert not (files_root / "notes.txt").exists()


def test_delete_from_the_entry_menu_asks_first_and_removes_the_file(
    open_files_page: OpenFilesPage, files_root: Path
) -> None:
    page = open_files_page("/")
    _entry(page, "/README.md").click(button="right")
    page.locator('[data-menu-row="delete"]').click()
    expect(page.locator('[data-dialog="delete"]')).to_contain_text(
        'Delete "README.md"?'
    )
    page.locator('[data-dialog-action="confirm"]').click()

    expect(_entry(page, "/README.md")).to_have_count(0)
    assert not (files_root / "README.md").exists()


def test_add_makes_a_new_folder_and_names_it(
    open_files_page: OpenFilesPage, files_root: Path
) -> None:
    page = open_files_page("/")
    page.locator('[data-action="add"]').click()
    page.locator('[data-menu-row="new-folder"]').click()
    expect(page.locator(".files-rename-field")).to_be_focused()
    page.keyboard.type("Drafts")
    page.keyboard.press("Enter")

    expect(_entry(page, "/Drafts/")).to_be_visible()
    assert (files_root / "Drafts").is_dir()
    assert not (files_root / "untitled folder").exists()


def test_uploads_land_in_the_folder_and_a_taken_name_can_keep_both(
    open_files_page: OpenFilesPage, files_root: Path
) -> None:
    page = open_files_page("/photos/")
    with page.expect_file_chooser() as chooser:
        page.locator('[data-action="add"]').click()
        page.locator('[data-menu-row="upload-files"]').click()
    chooser.value.set_files(
        [{"name": "notes.txt", "mimeType": "text/plain", "buffer": b"uploaded"}]
    )
    expect(_entry(page, "/photos/notes.txt")).to_be_visible()
    expect(page.locator(".files-uploads-summary")).to_have_text("Uploaded 1 item")
    assert (files_root / "photos" / "notes.txt").read_text() == "uploaded"

    with page.expect_file_chooser() as chooser:
        page.locator('[data-action="add"]').click()
        page.locator('[data-menu-row="upload-files"]').click()
    chooser.value.set_files(
        [{"name": "notes.txt", "mimeType": "text/plain", "buffer": b"again"}]
    )
    page.locator('[data-dialog-action="keep-both"]').click()
    expect(_entry(page, "/photos/notes 2.txt")).to_be_visible()
    assert (files_root / "photos" / "notes.txt").read_text() == "uploaded"
    assert (files_root / "photos" / "notes 2.txt").read_text() == "again"


def test_files_dropped_on_a_folder_upload_into_it(
    open_files_page: OpenFilesPage, files_root: Path
) -> None:
    page = open_files_page("/")
    page.evaluate(
        """() => {
          const transfer = new DataTransfer();
          transfer.items.add(new File(["dropped"], "dropped.txt", { type: "text/plain" }));
          const folder = document.querySelector('[data-entry-path="/projects/"]');
          for (const type of ["dragenter", "dragover", "drop"]) {
            folder.dispatchEvent(new DragEvent(type, { bubbles: true, cancelable: true, dataTransfer: transfer }));
          }
        }"""
    )
    expect(page.locator(".files-uploads-summary")).to_have_text("Uploaded 1 item")
    assert (files_root / "projects" / "dropped.txt").read_text() == "dropped"


def test_an_entry_dragged_onto_a_folder_moves_into_it(
    open_files_page: OpenFilesPage, files_root: Path
) -> None:
    page = open_files_page("/")
    _entry(page, "/README.md").drag_to(_entry(page, "/projects/"))
    expect(_entry(page, "/README.md")).to_have_count(0)
    assert (files_root / "projects" / "README.md").read_text() == "# hello\n"


def test_search_lists_matches_from_all_through_the_folder(
    open_files_page: OpenFilesPage,
) -> None:
    page = open_files_page("/")
    page.locator(".files-search-input").fill("main")
    expect(page.locator(".files-search-header")).to_contain_text("Results in Computer")
    expect(page.locator("[data-entry-path]")).to_have_count(1)
    expect(_entry(page, "/projects/app/main.py")).to_contain_text("projects/app")

    page.keyboard.press("Escape")
    expect(page.locator(".files-search-header")).to_have_count(0)


def test_a_path_param_opens_that_folder(open_files_page: OpenFilesPage) -> None:
    page = open_files_page("/?path=/projects/app/")
    expect(_entry(page, "/projects/app/main.py")).to_be_visible()
    assert page.url.endswith("/projects/app/")
    assert page.title() == "app"


def test_a_phone_lists_entries_and_opens_one_with_a_tap(
    open_files_page: OpenFilesPage,
) -> None:
    page = open_files_page("/", *PHONE)
    expect(page.locator(".files-sidebar")).to_be_visible()
    expect(page.locator('.files-sidebar [data-action="back"]')).to_be_visible()
    expect(page.locator('[data-view-mode="columns"]')).to_have_count(0)
    page.locator('[data-view-mode="list"]').click()
    expect(page.locator(".files-entry-menu-button")).to_have_count(4)

    _entry(page, "/projects/").click()
    expect(_entry(page, "/projects/app/")).to_be_visible()
    _entry(page, "/projects/app/").click()
    _entry(page, "/projects/app/main.py").click()
    expect(page).to_have_url(
        page.url.split("/projects")[0] + "/projects/app/main.py?view"
    )


def test_a_text_file_is_edited_and_saved_from_its_page(
    open_files_page: OpenFilesPage, files_root: Path
) -> None:
    page = open_files_page("/notes.txt?view")
    editor = page.locator(".files-editor")
    expect(editor).to_have_value("first line\nsecond line\n")
    expect(editor).to_have_attribute("readonly", "")

    page.locator(".edit-file").click()
    expect(page.locator('[data-action="save"]')).to_be_disabled()
    page.locator(".files-editor").fill("rewritten\n")
    expect(page.locator(".files-file-dirty")).to_have_text("Edited")
    page.locator('[data-action="save"]').click()
    expect(page.locator(".files-file-dirty")).to_have_count(0)
    assert (files_root / "notes.txt").read_text() == "rewritten\n"


def test_an_image_page_draws_the_image(open_files_page: OpenFilesPage) -> None:
    page = open_files_page("/photos/sunset.png?view")
    image = page.locator(".files-file-image")
    expect(image).to_be_visible()
    assert image.evaluate("img => img.naturalWidth") == 1
    expect(page.locator(".edit-file")).to_have_count(0)
