# CAMP

CAMP is the **CollectionBuilder Azure Metadata Packager**. It is a Flet desktop app for accepting a CollectionBuilder metadata CSV and related collection files, then preparing a deterministic package for Azure and the CB-Digital-Grinnell workflow.

## Current status

The first slice provides the desktop shell and input selection workflow:

- Select one CollectionBuilder metadata CSV.
- Select the CollectionBuilder deployment or local collection directory.
- Select an output directory for the future Azure package.
- See whether the required inputs are present.

The metadata mapping and Azure packaging engine are intentionally not connected yet. The next design step is to define the output manifest and mapping rules against a representative CollectionBuilder CSV.

## Quick run

```bash
./run.sh
```

Or, inside an activated virtual environment:

```bash
python -m pip install -r python_requirements.txt
python app.py
```

## Direction

CAMP should make this workflow repeatable and inspectable:

1. Validate the metadata CSV and collection paths.
2. Map CollectionBuilder fields into the CB-Digital-Grinnell shape.
3. Copy or package the required assets deterministically.
4. Produce a manifest, validation report, and Azure-ready output.
5. Keep logs and recoverable settings with the selected work directory.
