"""CAMP: CollectionBuilder Azure Metadata Packager."""

from pathlib import Path

import flet as ft


APP_TITLE = "CAMP"


def main(page: ft.Page) -> None:
    page.title = f"{APP_TITLE} | CollectionBuilder Azure Metadata Packager"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 28
    page.window_width = 980
    page.window_height = 760
    page.bgcolor = ft.Colors.BLUE_GREY_50

    csv_path = ft.TextField(
        label="Metadata CSV",
        hint_text="Choose the CollectionBuilder metadata CSV",
        read_only=True,
        expand=True,
    )
    collection_path = ft.TextField(
        label="CollectionBuilder files",
        hint_text="Choose the deployment or local collection directory",
        read_only=True,
        expand=True,
    )
    output_path = ft.TextField(
        label="Azure package output",
        hint_text="Choose where the prepared package will be written",
        read_only=True,
        expand=True,
    )
    status = ft.Text("Ready for input", color=ft.Colors.BLUE_GREY_700)
    package_button = ft.FilledButton(
        "Prepare Azure package",
        icon=ft.Icons.INVENTORY_2_OUTLINED,
        disabled=True,
    )

    def update_package_state() -> None:
        package_button.disabled = not all(
            (csv_path.value, collection_path.value, output_path.value)
        )
        page.update()

    def choose_csv(event: ft.FilePickerResultEvent) -> None:
        if event.files:
            csv_path.value = event.files[0].path
            status.value = "Metadata CSV selected."
        update_package_state()

    def choose_collection(event: ft.FilePickerResultEvent) -> None:
        if event.path:
            collection_path.value = event.path
            status.value = "CollectionBuilder directory selected."
        update_package_state()

    def choose_output(event: ft.FilePickerResultEvent) -> None:
        if event.path:
            output_path.value = event.path
            status.value = "Output directory selected."
        update_package_state()

    def prepare_package(_: ft.ControlEvent) -> None:
        status.value = (
            "Packaging engine not connected yet. Inputs are ready for the next step."
        )
        status.color = ft.Colors.ORANGE_800
        page.update()

    csv_picker = ft.FilePicker(on_result=choose_csv)
    collection_picker = ft.FilePicker(on_result=choose_collection)
    output_picker = ft.FilePicker(on_result=choose_output)
    page.overlay.extend([csv_picker, collection_picker, output_picker])

    package_button.on_click = prepare_package

    def pick_csv(_: ft.ControlEvent) -> None:
        csv_picker.pick_files(
            allow_multiple=False,
            allowed_extensions=["csv"],
        )

    def pick_collection(_: ft.ControlEvent) -> None:
        collection_picker.get_directory_path()

    def pick_output(_: ft.ControlEvent) -> None:
        output_picker.get_directory_path()

    page.add(
        ft.Column(
            [
                ft.Text(APP_TITLE, size=34, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "CollectionBuilder Azure Metadata Packager",
                    size=18,
                    color=ft.Colors.BLUE_GREY_700,
                ),
                ft.Divider(height=26),
                ft.Text(
                    "Prepare the source material for a Digital Grinnell collection.",
                    size=16,
                ),
                ft.Row(
                    [csv_path, ft.OutlinedButton("Browse", icon=ft.Icons.UPLOAD_FILE, on_click=pick_csv)],
                    spacing=12,
                ),
                ft.Row(
                    [
                        collection_path,
                        ft.OutlinedButton("Browse", icon=ft.Icons.FOLDER_OPEN, on_click=pick_collection),
                    ],
                    spacing=12,
                ),
                ft.Row(
                    [
                        output_path,
                        ft.OutlinedButton("Browse", icon=ft.Icons.CREATE_NEW_FOLDER, on_click=pick_output),
                    ],
                    spacing=12,
                ),
                ft.Container(height=12),
                ft.Row(
                    [package_button],
                    alignment=ft.MainAxisAlignment.END,
                ),
                ft.Container(
                    content=ft.Row(
                        [ft.Icon(ft.Icons.INFO_OUTLINE), status],
                        spacing=10,
                    ),
                    padding=ft.padding.symmetric(vertical=14, horizontal=16),
                    bgcolor=ft.Colors.WHITE,
                    border_radius=8,
                ),
                ft.Container(expand=True),
                ft.Text(
                    f"CAMP workspace: {Path.home() / 'CAMP-data'}",
                    size=12,
                    color=ft.Colors.BLUE_GREY_500,
                ),
            ],
            expand=True,
            spacing=18,
        )
    )


if __name__ == "__main__":
    ft.app(target=main)
