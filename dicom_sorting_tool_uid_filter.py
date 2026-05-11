#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DICOM Sorting Toolkit — UID-Filtered Variant (v1.6.0)

Same behaviour as dicom_sorting_tool.py, but ONLY processes DICOM files whose
StudyInstanceUID is in --study_uid_filter OR whose SeriesInstanceUID is in
--series_uid_filter. All other files are skipped.

Match semantics:
  * If a file's StudyInstanceUID is in the study filter set → the file is kept
    (so listing a StudyInstanceUID effectively keeps every series of that study).
  * Else, if its SeriesInstanceUID is in the series filter set → the file is kept.
  * Otherwise the file is skipped.

At least one of --study_uid_filter or --series_uid_filter must be provided.

UID list file format (same for both):
  - One UID per line
  - Lines starting with '#' are comments
  - Inline trailing comments after '#' are stripped
  - Blank lines are ignored
"""

import argparse
import multiprocessing
import time
import logging
import os

from dicom_sorting_tool import (
    sort_dicom,
    read_id_correlation,
    read_uid_filter,
    missing_ids,
)


def main():
    parser = argparse.ArgumentParser(
        description=("Sort/anonymize DICOM files, but only those whose "
                     "StudyInstanceUID or SeriesInstanceUID appears in a "
                     "user-supplied list."),
        formatter_class=argparse.RawTextHelpFormatter,
    )

    # I/O
    parser.add_argument('--dicomin', type=str, required=True,
                        help='Path to the input directory containing unsorted DICOM files.')
    parser.add_argument('--dicomout', type=str, required=True,
                        help='Path to the output directory.')

    # UID filters (at least one required)
    parser.add_argument('--study_uid_filter', type=str, default=None,
                        help='Path to a text file listing StudyInstanceUIDs to keep '
                             '(one per line, # for comments).')
    parser.add_argument('--series_uid_filter', type=str, default=None,
                        help='Path to a text file listing SeriesInstanceUIDs to keep '
                             '(one per line, # for comments).')

    # Anonymization & friends (same as the main tool)
    parser.add_argument('--anonymize', action='store_true',
                        help='Anonymize PatientName / PatientID.')
    parser.add_argument('--anonymize_strict', action='store_true',
                        help='Stricter anonymization: removes private tags, etc.')
    parser.add_argument('--ID_correlation', type=str,
                        help='Optional correlation file mapping old PatientIDs to new ones.\n'
                             'Format: oldID,newID per line.')
    parser.add_argument('--decompress', action='store_true',
                        help='Decompress DICOM files during processing.')
    parser.add_argument('--skip_derived', action='store_true',
                        help='Skip derived/secondary images.')
    parser.add_argument('--skip_burned_in_images', action='store_true',
                        help='Skip files with burned-in annotations.')
    parser.add_argument('--id_from_name', action='store_true',
                        help='Read original ID from PatientName instead of PatientID.')
    parser.add_argument('--anonymize_birth_date', action='store_true',
                        help='Anonymize PatientBirthDate to Jan 1st of same year.')
    parser.add_argument('--anonymize_acquisition_date', action='store_true',
                        help='Anonymize AcquisitionDate to Jan 1st of same year.')
    parser.add_argument('--preserve_private_tags', action='store_true',
                        help='Preserve private tags even in strict mode.')
    parser.add_argument('--anonymize_accession', action='store_true',
                        help='Anonymize Accession Number with a random 16-digit number.')
    parser.add_argument('--include_study_uid', action='store_true',
                        help='Use "StudyDate_StudyInstanceUID" instead of just "StudyDate" '
                             'in the folder layout.')
    parser.add_argument('--skip_unmapped', action='store_true',
                        help='Skip files whose PatientID is not present in --ID_correlation '
                             '(requires --ID_correlation).')

    args = parser.parse_args()

    # Validation
    if not args.study_uid_filter and not args.series_uid_filter:
        parser.error("At least one of --study_uid_filter or --series_uid_filter is required.")

    if args.skip_unmapped and not args.ID_correlation:
        parser.error("--skip_unmapped requires --ID_correlation.")

    # Load filter lists
    study_filter = read_uid_filter(args.study_uid_filter) if args.study_uid_filter else None
    series_filter = read_uid_filter(args.series_uid_filter) if args.series_uid_filter else None

    if study_filter is not None and len(study_filter) == 0:
        parser.error(f"Study UID filter file '{args.study_uid_filter}' is empty after parsing.")
    if series_filter is not None and len(series_filter) == 0:
        parser.error(f"Series UID filter file '{args.series_uid_filter}' is empty after parsing.")

    n_study = len(study_filter) if study_filter else 0
    n_series = len(series_filter) if series_filter else 0
    print(f"UID filter loaded: {n_study} StudyInstanceUID(s), {n_series} SeriesInstanceUID(s).")
    logging.info(f"UID filter loaded: {n_study} study UIDs, {n_series} series UIDs.")

    id_map = read_id_correlation(args.ID_correlation) if args.ID_correlation else None

    start_time = time.time()
    sort_dicom(
        args.dicomin, args.dicomout,
        args.anonymize or args.anonymize_strict,
        id_map,
        args.decompress,
        args.anonymize_strict,
        args.skip_derived,
        args.skip_burned_in_images,
        args.id_from_name,
        args.anonymize_birth_date,
        args.anonymize_acquisition_date,
        args.preserve_private_tags,
        args.anonymize_accession,
        include_study_uid=args.include_study_uid,
        skip_missing_id=args.skip_unmapped,
        study_uid_filter=study_filter,
        series_uid_filter=series_filter,
    )
    end_time = time.time()

    print(f"Total processing time: {end_time - start_time:.2f} seconds")
    logging.info(f"Total processing time: {end_time - start_time:.2f} seconds")

    if missing_ids:
        log_file_path = os.path.join(args.dicomout, 'missing_patient_ids.log')
        try:
            with open(log_file_path, 'w') as log_file:
                for mid in missing_ids:
                    log_file.write(f'{mid}\n')
            print(f"Missing PatientIDs logged in '{log_file_path}'.")
        except Exception as e:
            logging.error(f"Failed to write missing patient IDs log: {e}")


if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
