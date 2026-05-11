# DICOM Sorting Toolkit

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.13099114.svg)](https://zenodo.org/doi/10.5281/zenodo.13094029)

**Current version: v1.6.0**

This tool provides functionality for sorting and anonymizing DICOM files.

## Features:
- DICOM file sorting with two selectable folder layouts:
  - `PatientID/StudyDate/SeriesNumber_SeriesDescription` (default)
  - `PatientID/StudyDate_StudyInstanceUID/SeriesNumber_SeriesDescription` (one folder per study, useful when a patient has multiple studies on the same day)
- Basic and strict anonymization options
- Optional ID correlation file to map original PatientIDs to new IDs
- Optional "skip unmapped patients" mode: only files whose PatientID appears in the correlation file are transferred. Skipped PatientIDs are written to `skipped_unmapped_patients.txt` in the output folder.
- In-place files transfer syntax decompression
- GUI for easy operation

## What's new in v1.6.0
- **Folder-structure option**: choose between the legacy layout and a new `StudyDate_StudyInstanceUID` layout that gives each study its own folder.
- **Skip patients not in ID correlation file**: when checked, files whose PatientID (or PatientName, with `--id_from_name`) is not in the correlation file are skipped instead of being given an auto-generated ID. Works with all anonymization modes:
  - With **No anonymization**: original PatientIDs are kept; only patients on the list are sorted.
  - With **Basic / Strict** anonymization: anonymization is applied using the correlation file; patients not on the list are skipped.
- The list of skipped (unmapped) PatientIDs is written to `skipped_unmapped_patients.txt` in the output directory.
- GUI updated with a folder-structure dropdown and a "Skip patients not in ID correlation file" checkbox. The GUI blocks execution if skip-unmapped is checked without a correlation file.
- **UID-filtered variant**: a new standalone script `dicom_sorting_tool_uid_filter.py` and a matching GUI panel that only process DICOM files whose `StudyInstanceUID` or `SeriesInstanceUID` is in a user-supplied list (one UID per line, `#` for comments). Listing a `StudyInstanceUID` keeps every series of that study; listing a `SeriesInstanceUID` keeps only that series.

### UID-filtered sorting

```bash
# Keep only specific studies and series
python dicom_sorting_tool_uid_filter.py \
    --dicomin /path/to/unsorted --dicomout /path/to/sorted \
    --study_uid_filter studies.txt \
    --series_uid_filter series.txt
```

At least one of `--study_uid_filter` and `--series_uid_filter` must be provided. The variant supports every flag of the main tool (anonymization, ID correlation, decompression, folder structure, etc.). In the GUI, use the "UID-Filtered Sorting" panel.

UID list file format:
```text
# This is a comment
1.2.840.113619.2.55.3.604688119.868.1234567890.123
1.2.840.113619.2.55.3.604688119.868.1234567890.124  # inline comment ok
```

##  Download:
The executable for this tool is available in the releases section of this repository.

##  Usage:
1. Download the executable from the releases section.
2. Run the executable (it has been tested on a Windows 10 and Windwos 11 machines).
3. Use the GUI to select your input and output directories, and choose your desired options.
4. Click "Execute Sorting" to process your DICOM files.

## Script version usage:

### Environment 
The script requires Python 3 and additional packages: `tqdm`, `pydicom`, and `pathvalidate`. Install these dependencies with:
```pip install tqdm pydicom pathvalidate```


### Commands

Basic usage for sorting DICOM files:

```bash
python dicom_sorting_tool.py --dicomin /path/to/unsorted --dicomout /path/to/sorted
```

To also anonymize DICOM files (removing Patient Name and Date of Birth, but not Patient ID):

```bash
python dicom_sorting_tool.py --dicomin /path/to/unsorted --dicomout /path/to/sorted --anonymize
```

To perform strict anonymization of DICOM files:

```bash
python dicom_sorting_tool.py --dicomin /path/to/unsorted --dicomout /path/to/sorted --anonymize --anonymize_strict
```


To replace PatientID based on a correlation table:

```bash
python dicom_sorting_tool.py --dicomin /path/to/unsorted --dicomout /path/to/sorted --anonymize --ID_correlation /path/to/ID_correlation.txt
```

To use the per-study folder layout (`StudyDate_StudyInstanceUID`):

```bash
python dicom_sorting_tool.py --dicomin /path/to/unsorted --dicomout /path/to/sorted --include_study_uid
```

To only sort patients listed in the correlation file (skip everyone else):

```bash
# Keep original PatientIDs, skip anyone not on the list
python dicom_sorting_tool.py --dicomin /path/to/unsorted --dicomout /path/to/sorted \
    --ID_correlation /path/to/ID_correlation.txt --skip_unmapped

# Anonymize using the list, skip anyone not on the list
python dicom_sorting_tool.py --dicomin /path/to/unsorted --dicomout /path/to/sorted \
    --anonymize --ID_correlation /path/to/ID_correlation.txt --skip_unmapped
```

The list of patients that were present in the source but missing from the correlation file is written to `skipped_unmapped_patients.txt` inside the output directory.

### Arguments

- **`--dicomin`**: Path to the directory containing unsorted DICOM files.
- **`--dicomout`**: Path to the directory where the sorted DICOM files will be stored based on their metadata.
- **`--anonymize`**: (Optional) If specified, anonymizes DICOM tags such as PatientName and PatientBirthDate.
- **`--anonymize_strict`**: (Optional) If specified, performs stricter anonymization, including removal of private tags and anonymizing additional fields.
- **`--decompress`**: (Optional) If specified, decompresses transfer syntax DICOM files during processing.
- **`--ID_correlation`**: (Optional) Path to a correlation file for anonymizing PatientID. The file should contain old and new IDs, separated by a comma, space, or tab.
- **`--skip_derived`**: (Optional) If specified, skips DICOM files that are derived or secondary images.
- **`--skip_burned_in_images`**: (Optional) If specified, skips DICOM files with burned-in annotations.
- **`--include_study_uid`**: (Optional, *new in v1.6.0*) If specified, study folders are named `StudyDate_StudyInstanceUID` instead of just `StudyDate`. Useful when the same patient has multiple studies on the same day.
- **`--skip_unmapped`**: (Optional, *new in v1.6.0*) If specified, files whose PatientID is not present in `--ID_correlation` are skipped (requires `--ID_correlation`). The list of skipped PatientIDs is written to `skipped_unmapped_patients.txt` in the output directory.
  
  
## Note:
This tool is for internal use only. It is not validated with DICOM standards, and we do not guarantee its accuracy or reliability. Use at your own risk.

For any issues or feature requests, please open an issue in this repository."
