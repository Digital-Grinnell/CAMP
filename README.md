# CAMP

CAMP is the **CollectionBuilder Azure Metadata Packager**. It is a Flet desktop app for accepting a CollectionBuilder metadata CSV and related collection files, then preparing a deterministic package for Azure and the CB-Digital-Grinnell workflow.

## Current status

The first slice provides the desktop shell and input selection workflow:

- Select one CollectionBuilder metadata CSV.
- Select the CollectionBuilder deployment or local collection directory.
- Select an output directory for the future Azure package, defaulting to `~/CAMP-data`.
- Enter a collection ID using 4-20 lowercase letters, underscores, or hyphens.
- See whether the required inputs are present.
- Reopen CAMP with the previously selected inputs restored from `~/CAMP-data/settings.json`.

The packaging action uploads values from the metadata CSV to parallel Digital Grinnell blob containers under `collection_id/`: `object_location` to `objs`, `image_small` to `smalls`, and `image_thumb` to `thumbs`. Local paths are resolved beneath the selected CollectionBuilder directory; HTTP and HTTPS locations are downloaded and streamed to Azure. An upload report is written to the selected output directory as `camp-upload-report.json`.

Successful uploads are retained in `~/CAMP-data/object-url-registry.json`, keyed by normalized `objectid`. Each value contains `original_objectid`, `obj_url`, `smalls_url`, `thumbs_url`, and `transcript`; URLs for containers that were not uploaded remain empty, and `transcript` contains the original `object_transcript` filename when present. For IDs beginning with `dg_`, the stored key is prefixed with `collection_id` and an underscore; `original_objectid` always preserves the CSV value.

When `object_transcript` is populated, CAMP finds the named CSV files in `_data/transcripts` and copies the complete transcripts directory to `<output>/_data/transcripts`.

CAMP also writes a transformed metadata CSV to `<output>/<collection_id>_metadata.csv`. It preserves the original columns and replaces `objectid`, `object_location`, `image_small`, `image_thumb`, and `object_transcript` with the normalized ID and values from the registry.

The upload report includes warnings when a normalized object ID already exists in the registry, or when an object filename or source URL is repeated in the CSV. Each repeated value is reported only once per run; duplicates remain non-fatal.

Before reading or downloading a source file, CAMP checks whether the destination blob already exists. Existing blobs are skipped and reported as `existing_blob` warnings so repeated runs do not spend resources copying them again.

CAMP writes timestamped DEBUG logs to `~/CAMP-data/logfiles` at startup and reconfigures logging to `<output directory>/logfiles` when an output directory is selected. ERROR-level messages are also sent to the console.

## Quick run

```bash
./run.sh
```

Or, inside an activated virtual environment:

```bash
python -m pip install -r python_requirements.txt
python app.py
```

Before uploading, authenticate with Azure in the environment used to launch CAMP. The default Azure credential chain is used, so an Azure CLI login is sufficient for local use:

```bash
az login
```

## Direction

CAMP should make this workflow repeatable and inspectable:

1. Validate the metadata CSV and collection paths.
2. Map CollectionBuilder fields into the CB-Digital-Grinnell shape.
3. Copy or package the required assets deterministically.
4. Produce a manifest, validation report, and Azure-ready output.
5. Keep logs, recoverable settings, and default saved data in `~/CAMP-data` unless another output directory is selected.

The Azure destination is the `objs` blob container in the `digitalgrinnell` storage account. The folder is virtual, so `collection_id` is created automatically by using blob names such as `collection_id/object.jpg`; the container itself must already exist.
