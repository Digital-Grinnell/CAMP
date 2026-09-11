"""CAMP: CollectionBuilder Azure Metadata Packager."""

import csv
import json
import logging
import mimetypes
import re
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import urlopen

import flet as ft


APP_TITLE = "CAMP"
DATA_DIR = Path.home() / "CAMP-data"
SETTINGS_PATH = DATA_DIR / "settings.json"
OBJECT_URL_REGISTRY_PATH = DATA_DIR / "object-url-registry.json"
COLLECTION_ID_PATTERN = re.compile(r"[a-z_-]+")
AZURE_BLOB_SERVICE_ENDPOINT = "https://digitalgrinnell.blob.core.windows.net/"
AZURE_BLOB_CONTAINERS = {
    "object_location": "objs",
    "image_small": "smalls",
    "image_thumb": "thumbs",
}
OPTIONAL_IMAGE_CONTAINERS = {"smalls", "thumbs"}
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

DATA_DIR.mkdir(parents=True, exist_ok=True)
TEMP_LOG_DIR = DATA_DIR / "logfiles"
TEMP_LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = TEMP_LOG_DIR / f"camp_{datetime.now():%Y%m%d_%H%M%S}.log"
file_handler = logging.FileHandler(LOG_PATH)
file_handler.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.ERROR)
formatter = logging.Formatter(LOG_FORMAT)
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)
logging.basicConfig(
    level=logging.DEBUG,
    handlers=[file_handler, console_handler],
)
logging.getLogger("flet").setLevel(logging.WARNING)
logging.getLogger("flet_core").setLevel(logging.WARNING)
logging.getLogger("flet_desktop").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def setup_working_dir_logging(working_dir: str) -> None:
    global LOG_PATH
    if not working_dir:
        return
    log_dir = Path(working_dir) / "logfiles"
    log_dir.mkdir(parents=True, exist_ok=True)
    new_log_path = log_dir / f"camp_{datetime.now():%Y%m%d_%H%M%S}.log"
    file_handler = logging.FileHandler(new_log_path)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        if isinstance(handler, logging.FileHandler):
            handler.close()
            root_logger.removeHandler(handler)
    root_logger.addHandler(file_handler)
    LOG_PATH = new_log_path
    logger.info("Logging reconfigured to %s", new_log_path)


def load_settings() -> dict[str, str]:
    try:
        return json.loads(SETTINGS_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def save_settings(settings: dict[str, str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2) + "\n")


REGISTRY_URL_FIELDS = {
    "objs": "obj_url",
    "smalls": "smalls_url",
    "thumbs": "thumbs_url",
}


def empty_registry_record(original_objectid: str) -> dict[str, str]:
    return {
        "original_objectid": original_objectid,
        "obj_url": "",
        "smalls_url": "",
        "thumbs_url": "",
        "transcript": "",
    }


def load_object_url_registry() -> dict[str, dict[str, str]]:
    try:
        registry = json.loads(OBJECT_URL_REGISTRY_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    migrated: dict[str, dict[str, str]] = {}
    if isinstance(registry, list):
        for record in registry:
            if not isinstance(record, dict):
                continue
            object_id = record.get("objectid")
            if not isinstance(object_id, str) or not object_id:
                continue
            entry = migrated.setdefault(
                object_id,
                empty_registry_record(record.get("original_objectid", object_id)),
            )
            container = record.get("container")
            url = record.get("url")
            if container in REGISTRY_URL_FIELDS and isinstance(url, str):
                entry[REGISTRY_URL_FIELDS[container]] = url
            if isinstance(record.get("transcript"), str):
                entry["transcript"] = record["transcript"]
        return migrated
    if isinstance(registry, dict):
        for object_id, value in registry.items():
            if not isinstance(object_id, str):
                continue
            if isinstance(value, str):
                migrated[object_id] = empty_registry_record(object_id)
                migrated[object_id]["obj_url"] = value
                continue
            if not isinstance(value, dict):
                continue
            entry = empty_registry_record(
                value.get("original_objectid", object_id)
            )
            for field in REGISTRY_URL_FIELDS.values():
                if isinstance(value.get(field), str):
                    entry[field] = value[field]
            if isinstance(value.get("transcript"), str):
                entry["transcript"] = value["transcript"]
            migrated[object_id] = entry
    return migrated


def save_object_url_registry(registry: dict[str, dict[str, str]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary_path = OBJECT_URL_REGISTRY_PATH.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(registry, indent=2) + "\n")
    temporary_path.replace(OBJECT_URL_REGISTRY_PATH)


def normalized_object_id(object_id: str, collection_id: str) -> str:
    object_id = object_id.strip()
    if object_id.startswith("dg_"):
        return f"{collection_id}_{object_id}"
    return object_id


def add_warning(
    warnings: list[dict[str, object]],
    warning_keys: set[tuple[str, str]],
    warning_type: str,
    value: str,
    message: str,
) -> None:
    warning_key = (warning_type, value)
    if warning_key not in warning_keys:
        warnings.append({"type": warning_type, "value": value, "message": message})
        warning_keys.add(warning_key)


def blob_suffix(source: Path, collection_root: Path) -> str:
    relative_path = source.resolve().relative_to(collection_root.resolve()).as_posix()
    for source_container in AZURE_BLOB_CONTAINERS.values():
        if relative_path.startswith(f"{source_container}/"):
            relative_path = relative_path[len(source_container) + 1 :]
            break
    return relative_path


def resolve_object_path(
    object_location: str, csv_file: Path, collection_root: Path
) -> Path:
    collection_root = collection_root.resolve()
    raw_path = Path(object_location).expanduser()
    candidates = (
        raw_path if raw_path.is_absolute() else collection_root / raw_path,
        csv_file.parent / raw_path,
    )
    for candidate in candidates:
        resolved = candidate.resolve()
        try:
            resolved.relative_to(collection_root)
        except ValueError:
            continue
        if resolved.is_file():
            return resolved
    raise FileNotFoundError(object_location)


def upload_objects(
    csv_file: Path,
    collection_root: Path,
    collection_id: str,
    report_path: Path,
    status_callback,
) -> dict[str, int]:
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient, ContentSettings

    blob_service = BlobServiceClient(
        account_url=AZURE_BLOB_SERVICE_ENDPOINT,
        credential=DefaultAzureCredential(),
    )
    report = {"uploaded": [], "failed": [], "warnings": []}
    object_url_registry = load_object_url_registry()
    save_object_url_registry(object_url_registry)
    registered_object_ids = set(object_url_registry)
    warning_keys = set()
    seen_blob_names = set()
    seen_filenames = set()
    seen_source_urls = set()
    transcript_rows = []

    with csv_file.open(newline="", encoding="utf-8-sig") as source_csv:
        rows = csv.DictReader(source_csv)
        if "objectid" not in (rows.fieldnames or []):
            raise ValueError("The metadata CSV has no objectid column.")
        fieldnames = rows.fieldnames or []

        rows = list(rows)
        transcript_names = {
            (row.get("object_transcript") or "").strip()
            for row in rows
            if (row.get("object_transcript") or "").strip()
        }
        if transcript_names:
            invalid_transcript_names = {
                name
                for name in transcript_names
                if Path(name).name != name
            }
            if invalid_transcript_names:
                raise ValueError(
                    "object_transcript values must be filenames, not paths: "
                    + ", ".join(sorted(invalid_transcript_names))
                )
            transcript_sources = (
                csv_file.parent / "transcripts",
                csv_file.parent.parent / "_data" / "transcripts",
                collection_root / "_data" / "transcripts",
            )
            transcript_source_dir = next(
                (path for path in transcript_sources if path.is_dir()), None
            )
            if transcript_source_dir is None:
                raise FileNotFoundError(
                    "No _data/transcripts directory was found for object_transcript."
                )
            transcript_output_dir = report_path.parent / "_data" / "transcripts"
            shutil.copytree(
                transcript_source_dir,
                transcript_output_dir,
                dirs_exist_ok=True,
            )
            for transcript_name in sorted(transcript_names):
                transcript_path = transcript_source_dir / transcript_name
                if not transcript_path.is_file():
                    report["failed"].append(
                        {
                            "source": str(transcript_path),
                            "error": "Transcript file was not found.",
                        }
                    )
                    continue
                transcript_rows.append(transcript_name)
            logger.info(
                "Copied %s transcript file(s) to %s",
                len(transcript_rows),
                transcript_output_dir,
            )

        for row_number, row in enumerate(rows, start=2):
            object_id = (row.get("objectid") or "").strip()
            if not object_id:
                report["failed"].append(
                    {"row": row_number, "error": "Missing objectid."}
                )
                continue
            normalized_id = normalized_object_id(object_id, collection_id)
            transcript_name = (row.get("object_transcript") or "").strip()
            if transcript_name:
                registry_entry = object_url_registry.setdefault(
                    normalized_id, empty_registry_record(object_id)
                )
                registry_entry["transcript"] = transcript_name
            if normalized_id in registered_object_ids:
                add_warning(
                    report["warnings"],
                    warning_keys,
                    "duplicate_objectid",
                    normalized_id,
                    f"Normalized objectid already exists in the registry: {normalized_id}",
                )
            for source_column, container_name in AZURE_BLOB_CONTAINERS.items():
                source_location = (row.get(source_column) or "").strip()
                if not source_location:
                    continue
                container = blob_service.get_container_client(container_name)
                parsed_location = urlparse(source_location)
                is_remote = parsed_location.scheme in {"http", "https"}
                if is_remote:
                    if source_location in seen_source_urls:
                        add_warning(
                            report["warnings"],
                            warning_keys,
                            "duplicate_url",
                            source_location,
                            f"Source URL appears more than once: {source_location}",
                        )
                    seen_source_urls.add(source_location)
                    filename = Path(unquote(parsed_location.path)).name
                    source = source_location
                else:
                    try:
                        source_path = resolve_object_path(
                            source_location, csv_file, collection_root
                        )
                    except FileNotFoundError:
                        if container_name in OPTIONAL_IMAGE_CONTAINERS:
                            logger.info(
                                "Skipping missing optional image for row %s: %s",
                                row_number,
                                source_location,
                            )
                            continue
                        raise
                    filename = blob_suffix(source_path, collection_root)
                    source = str(source_path)

                filename_key = (container_name, filename)
                if filename_key in seen_filenames:
                    add_warning(
                        report["warnings"],
                        warning_keys,
                        "duplicate_filename",
                        f"{container_name}/{filename}",
                        f"Object filename appears more than once in {container_name}: {filename}",
                    )
                seen_filenames.add(filename_key)
                blob_name = f"{collection_id}/{filename}"
                blob_key = (container_name, blob_name)
                if blob_key in seen_blob_names:
                    continue
                seen_blob_names.add(blob_key)
                content_type = mimetypes.guess_type(filename)[0]
                content_settings = (
                    ContentSettings(content_type=content_type)
                    if content_type
                    else None
                )
                try:
                    blob_client = container.get_blob_client(blob_name)
                    destination = f"{container_name}/{blob_name}"
                    if blob_client.exists():
                        registry_entry = object_url_registry.setdefault(
                            normalized_id, empty_registry_record(object_id)
                        )
                        registry_entry[REGISTRY_URL_FIELDS[container_name]] = (
                            blob_client.url
                        )
                        save_object_url_registry(object_url_registry)
                        add_warning(
                            report["warnings"],
                            warning_keys,
                            "existing_blob",
                            destination,
                            f"Destination blob already exists; skipped: {destination}",
                        )
                        logger.warning("Skipping existing blob %s", destination)
                        continue
                    status_callback(f"Uploading {container_name}/{filename}...")
                    logger.info(
                        "Uploading row %s to %s/%s from %s",
                        row_number,
                        container_name,
                        blob_name,
                        source,
                    )
                    if is_remote:
                        with urlopen(source_location) as remote_file:
                            container.upload_blob(
                                name=blob_name,
                                data=remote_file,
                                overwrite=True,
                                content_settings=content_settings,
                            )
                    else:
                        with source_path.open("rb") as local_file:
                            container.upload_blob(
                                name=blob_name,
                                data=local_file,
                                overwrite=True,
                                content_settings=content_settings,
                            )
                    blob_url = blob_client.url
                    registry_entry = object_url_registry.setdefault(
                        normalized_id, empty_registry_record(object_id)
                    )
                    registry_entry[REGISTRY_URL_FIELDS[container_name]] = blob_url
                    save_object_url_registry(object_url_registry)
                    report["uploaded"].append(
                        {
                            "row": row_number,
                            "source": source,
                            "container": container_name,
                            "blob": blob_name,
                            "objectid": normalized_id,
                            "original_objectid": object_id,
                            "url": blob_url,
                        }
                    )
                    logger.info("Uploaded %s", blob_url)
                except Exception as error:
                    logger.exception(
                        "Upload failed for row %s to %s/%s",
                        row_number,
                        container_name,
                        blob_name,
                    )
                    report["failed"].append(
                        {
                            "row": row_number,
                            "source": source,
                            "container": container_name,
                            "blob": blob_name,
                            "error": str(error),
                        }
                    )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    save_object_url_registry(object_url_registry)
    metadata_path = report_path.parent / f"{collection_id}_metadata.csv"
    with metadata_path.open("w", newline="", encoding="utf-8") as metadata_csv:
        writer = csv.DictWriter(metadata_csv, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            object_id = (row.get("objectid") or "").strip()
            output_row = dict(row)
            if object_id:
                normalized_id = normalized_object_id(object_id, collection_id)
                registry_entry = object_url_registry.get(
                    normalized_id, empty_registry_record(object_id)
                )
                output_row.update(
                    {
                        "objectid": normalized_id,
                        "object_location": registry_entry["obj_url"],
                        "image_small": registry_entry["smalls_url"],
                        "image_thumb": registry_entry["thumbs_url"],
                        "object_transcript": registry_entry["transcript"],
                    }
                )
            writer.writerow(output_row)
    report["metadata_csv"] = str(metadata_path)
    logger.info("Wrote transformed metadata CSV to %s", metadata_path)
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    return {key: len(value) for key, value in report.items()}


def main(page: ft.Page) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    settings = load_settings()
    setup_working_dir_logging(settings.get("output_path", ""))
    logger.info("CAMP application started")

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
        value=settings.get("csv_path", ""),
    )
    collection_path = ft.TextField(
        label="CollectionBuilder files",
        hint_text="Choose the deployment or local collection directory",
        read_only=True,
        expand=True,
        value=settings.get("collection_path", ""),
    )
    output_path = ft.TextField(
        label="Azure package output",
        hint_text="Choose where the prepared package will be written",
        read_only=True,
        expand=True,
        value=settings.get("output_path", str(DATA_DIR)),
    )
    collection_id = ft.TextField(
        label="Collection ID",
        hint_text="4-20 lowercase characters, underscores, or hyphens",
        max_length=20,
        input_filter=ft.InputFilter(regex_string=r"[a-z_-]", allow=True),
        value=settings.get("collection_id", ""),
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
            (
                csv_path.value,
                collection_path.value,
                output_path.value,
                collection_id_is_valid(),
            )
        )
        page.update()

    def collection_id_is_valid() -> bool:
        value = collection_id.value or ""
        return 4 <= len(value) <= 20 and bool(
            COLLECTION_ID_PATTERN.fullmatch(value)
        )

    def validate_collection_id(_: ft.ControlEvent | None = None) -> None:
        value = collection_id.value or ""
        collection_id.error_text = (
            None
            if not value or collection_id_is_valid()
            else "Use 4-20 lowercase letters, underscores, or hyphens."
        )
        persist_inputs()
        update_package_state()

    def persist_inputs() -> None:
        save_settings(
            {
                "csv_path": csv_path.value or "",
                "collection_path": collection_path.value or "",
                "output_path": output_path.value or str(DATA_DIR),
                "collection_id": collection_id.value or "",
            }
        )

    def choose_csv(event: ft.FilePickerResultEvent) -> None:
        if event.files:
            csv_path.value = event.files[0].path
            status.value = "Metadata CSV selected."
            persist_inputs()
        update_package_state()

    def choose_collection(event: ft.FilePickerResultEvent) -> None:
        if event.path:
            collection_path.value = event.path
            status.value = "CollectionBuilder directory selected."
            persist_inputs()
        update_package_state()

    def choose_output(event: ft.FilePickerResultEvent) -> None:
        if event.path:
            output_path.value = event.path
            setup_working_dir_logging(event.path)
            status.value = "Output directory selected."
            persist_inputs()
        update_package_state()

    def prepare_package(_: ft.ControlEvent) -> None:
        try:
            counts = upload_objects(
                csv_file=Path(csv_path.value),
                collection_root=Path(collection_path.value),
                collection_id=collection_id.value,
                report_path=Path(output_path.value) / "camp-upload-report.json",
                status_callback=lambda message: set_status(message),
            )
            status.value = (
                f"Uploaded {counts['uploaded']} object(s); "
                f"{counts['failed']} failed; "
                f"{counts['warnings']} warning(s)."
            )
            status.color = (
                ft.Colors.GREEN_800
                if counts["failed"] == 0 and counts["warnings"] == 0
                else ft.Colors.ORANGE_800
            )
        except Exception as error:
            status.value = f"Upload failed: {error}"
            status.color = ft.Colors.RED_800
        page.update()

    def set_status(message: str) -> None:
        status.value = message
        status.color = ft.Colors.BLUE_GREY_700
        page.update()

    csv_picker = ft.FilePicker(on_result=choose_csv)
    collection_picker = ft.FilePicker(on_result=choose_collection)
    output_picker = ft.FilePicker(on_result=choose_output)
    page.overlay.extend([csv_picker, collection_picker, output_picker])

    package_button.on_click = prepare_package
    collection_id.on_change = validate_collection_id

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
                collection_id,
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
    validate_collection_id()


if __name__ == "__main__":
    ft.app(target=main)
