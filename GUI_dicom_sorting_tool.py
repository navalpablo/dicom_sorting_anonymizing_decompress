#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DICOM Sorting Toolkit GUI

Adds:
• In-place decompression panel
• Explicit-VR-Little-Endian conversion panel driven by pure-Python walk()
"""

# --------------------------------------------------
# imports
# --------------------------------------------------
import sys, os, logging, multiprocessing
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QRadioButton, QButtonGroup, QMessageBox,
    QGroupBox, QCheckBox, QProgressDialog, QComboBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

import pydicom
from dicom_sorting_tool import (
    sort_dicom, decompress_dataset, read_id_correlation, read_uid_filter
)
from to_explicit_pydicom import walk        # <-- pure-Python converter (no DCMTK)

# --------------------------------------------------
# worker threads
# --------------------------------------------------
class DecompressionThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal()
    error    = pyqtSignal(str)

    def __init__(self, input_dir: str):
        super().__init__()
        self.input_dir = input_dir

    def run(self):
        try:
            total_files = sum(len(fs) for _, _, fs in os.walk(self.input_dir))
            processed = decompressed = skipped = 0

            for root, _, files in os.walk(self.input_dir):
                for f in files:
                    path = os.path.join(root, f)
                    try:
                        ds = pydicom.dcmread(path)
                        if ds.file_meta.TransferSyntaxUID.is_compressed:
                            ds = decompress_dataset(ds)
                            ds.save_as(path)
                            decompressed += 1
                        else:
                            skipped += 1
                    except pydicom.errors.InvalidDicomError:
                        skipped += 1
                    except Exception as e:
                        self.error.emit(f"Error processing {path} — {e}")
                        skipped += 1
                    processed += 1
                    self.progress.emit(int(processed / total_files * 100))

            logging.info(f"Decompression done — ok:{decompressed}  skipped:{skipped}")
            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))


class SortingThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal()
    error    = pyqtSignal(str)

    def __init__(self, *a):
        super().__init__()
        (self.input_dir, self.output_dir, self.anonymize, self.id_map,
         self.decompress, self.strict_anonymize, self.skip_derived,
         self.skip_burned, self.id_from_name, self.anonymize_birth_date,
         self.anonymize_acquisition_date, self.preserve_private_tags,
         self.anonymize_accession, self.include_study_uid,
         self.skip_missing_id) = a
        # Optional UID filters (set via set_uid_filters)
        self.study_uid_filter = None
        self.series_uid_filter = None
        self.cancel_flag = multiprocessing.Value('b', False)

    def set_uid_filters(self, study_uid_filter=None, series_uid_filter=None):
        self.study_uid_filter = study_uid_filter
        self.series_uid_filter = series_uid_filter

    def run(self):
        try:
            sort_dicom(
                self.input_dir, self.output_dir, self.anonymize, self.id_map,
                self.decompress, self.strict_anonymize, self.skip_derived,
                self.skip_burned, self.id_from_name, self.anonymize_birth_date,
                self.anonymize_acquisition_date, self.preserve_private_tags,
                self.anonymize_accession,
                include_study_uid=self.include_study_uid,
                skip_missing_id=self.skip_missing_id,
                study_uid_filter=self.study_uid_filter,
                series_uid_filter=self.series_uid_filter,
                progress_callback=self.progress.emit,
                cancel_flag=self.cancel_flag
            )
            if not self.cancel_flag.value:
                self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

    def cancel(self):
        self.cancel_flag.value = True


class ExplicitThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal()
    error    = pyqtSignal(str)

    def __init__(self, input_dir: str):
        super().__init__()
        self.input_dir = input_dir

    def run(self):
        try:
            # Collect all file paths
            files = [os.path.join(r, f)
                     for r, _, fs in os.walk(self.input_dir) for f in fs]
            total = len(files)
            for i, path in enumerate(files, start=1):
                try:
                    ds = pydicom.dcmread(path, force=True)
                    if ds.file_meta.TransferSyntaxUID.is_compressed:
                        ds.decompress()
                    from pydicom.uid import ExplicitVRLittleEndian
                    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
                    ds.is_little_endian = True
                    ds.is_implicit_VR = False
                    ds.save_as(path, write_like_original=False)
                except (AttributeError, TypeError, ValueError):
                    # Do nothing; skip problematic files silently
                    continue
                except Exception:
                    # Log unexpected exceptions, but still continue
                    logging.debug(f"Explicit conversion skipped for {path}", exc_info=True)
                    continue

                self.progress.emit(int(i / total * 100))

            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

# --------------------------------------------------
# GUI
# --------------------------------------------------
class DicomSortingGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.sorting_thread   = None
        self.decomp_thread    = None
        self.exp_thread       = None
        self.progress_dialog  = None
        self.initUI()

        logging.basicConfig(filename='dicom_sorting_gui.log',
                            level=logging.DEBUG,
                            format='%(asctime)s %(levelname)s %(message)s')

    # ---------- UI layout ----------
    def initUI(self):
        layout = QVBoxLayout()

        # ==============================================================
        # 1. SORTING PANEL
        # ==============================================================
        sorting_group = QGroupBox("DICOM Sorting")
        sorting_layout = QVBoxLayout()

        # input / output directories
        self.input_edit  = self._dir_row("Input Directory:", sorting_layout)
        self.output_edit = self._dir_row("Output Directory:", sorting_layout)

        # folder structure dropdown
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(QLabel("Folder structure:"))
        self.folder_struct_combo = QComboBox()
        # Each entry stores its include_study_uid flag as user data
        self.folder_struct_combo.addItem(
            "PatientID / StudyDate / SeriesNumber_Description", False)
        self.folder_struct_combo.addItem(
            "PatientID / StudyDate_StudyInstanceUID / SeriesNumber_Description", True)
        folder_layout.addWidget(self.folder_struct_combo, 1)
        folder_info = QPushButton("?")
        folder_info.clicked.connect(self.show_folder_info)
        folder_layout.addWidget(folder_info)
        sorting_layout.addLayout(folder_layout)

        # anonymisation radio buttons
        anon_layout = QHBoxLayout()
        self.anon_group = QButtonGroup()
        self.no_anon_radio    = QRadioButton("No anonymization")
        self.basic_anon_radio = QRadioButton("Basic")
        self.strict_anon_radio= QRadioButton("Strict")
        for rb in (self.no_anon_radio, self.basic_anon_radio, self.strict_anon_radio):
            self.anon_group.addButton(rb)
            anon_layout.addWidget(rb)
        self.no_anon_radio.setChecked(True)
        anon_info = QPushButton("?"); anon_info.clicked.connect(self.show_anon_info)
        anon_layout.addWidget(anon_info)
        sorting_layout.addLayout(anon_layout)

        # ID correlation file
        self.id_edit = self._file_row("ID Correlation File:", sorting_layout, self.show_id_info)

        # checkboxes
        self.skip_unmapped_check         = self._add_cb(
            "Skip patients not in ID correlation file", sorting_layout)
        self.id_from_name_check          = self._add_cb("Read original ID from PatientName", sorting_layout)
        self.decompress_check            = self._add_cb("Decompress", sorting_layout)
        self.skip_derived_check          = self._add_cb("Skip Secondary/Derived images", sorting_layout)
        self.skip_burned_check           = self._add_cb("Skip Burned-in images", sorting_layout)
        self.preserve_private_tags_check = self._add_cb("Preserve Private Tags (strict mode)", sorting_layout)
        self.anonymize_birth_date_check  = self._add_cb("Anonymize Birth Date to 01-Jan", sorting_layout)
        self.anonymize_acquisition_date_check = self._add_cb("Anonymize Acquisition Date to 01-Jan", sorting_layout)
        self.anonymize_accession_check   = self._add_cb("Anonymize Accession Number", sorting_layout)

        # execute sorting
        sort_btn = QPushButton("Execute Sorting")
        sort_btn.clicked.connect(self.execute_sorting)
        sorting_layout.addWidget(sort_btn)

        sorting_group.setLayout(sorting_layout)
        layout.addWidget(sorting_group)

        # ==============================================================
        # 1b. UID-FILTERED SORTING PANEL
        # ==============================================================
        uid_group = QGroupBox("UID-Filtered Sorting (only files matching listed Study/Series UIDs)")
        uid_layout = QVBoxLayout()

        # input / output
        self.uid_input_edit  = self._dir_row("Input Directory:", uid_layout)
        self.uid_output_edit = self._dir_row("Output Directory:", uid_layout)

        # UID filter files
        self.uid_study_edit  = self._file_row(
            "Study UIDs file:", uid_layout, self.show_uid_filter_info)
        self.uid_series_edit = self._file_row(
            "Series UIDs file:", uid_layout, self.show_uid_filter_info)

        # folder structure dropdown
        uid_folder_layout = QHBoxLayout()
        uid_folder_layout.addWidget(QLabel("Folder structure:"))
        self.uid_folder_struct_combo = QComboBox()
        self.uid_folder_struct_combo.addItem(
            "PatientID / StudyDate / SeriesNumber_Description", False)
        self.uid_folder_struct_combo.addItem(
            "PatientID / StudyDate_StudyInstanceUID / SeriesNumber_Description", True)
        uid_folder_layout.addWidget(self.uid_folder_struct_combo, 1)
        uid_layout.addLayout(uid_folder_layout)

        # anonymisation radios
        uid_anon_layout = QHBoxLayout()
        self.uid_anon_group = QButtonGroup()
        self.uid_no_anon_radio    = QRadioButton("No anonymization")
        self.uid_basic_anon_radio = QRadioButton("Basic")
        self.uid_strict_anon_radio= QRadioButton("Strict")
        for rb in (self.uid_no_anon_radio, self.uid_basic_anon_radio, self.uid_strict_anon_radio):
            self.uid_anon_group.addButton(rb)
            uid_anon_layout.addWidget(rb)
        self.uid_no_anon_radio.setChecked(True)
        uid_layout.addLayout(uid_anon_layout)

        # ID correlation file
        self.uid_id_edit = self._file_row("ID Correlation File:", uid_layout, self.show_id_info)

        # checkboxes
        self.uid_skip_unmapped_check    = self._add_cb(
            "Skip patients not in ID correlation file", uid_layout)
        self.uid_id_from_name_check     = self._add_cb(
            "Read original ID from PatientName", uid_layout)
        self.uid_decompress_check       = self._add_cb("Decompress", uid_layout)
        self.uid_skip_derived_check     = self._add_cb(
            "Skip Secondary/Derived images", uid_layout)
        self.uid_skip_burned_check      = self._add_cb("Skip Burned-in images", uid_layout)
        self.uid_preserve_private_check = self._add_cb(
            "Preserve Private Tags (strict mode)", uid_layout)
        self.uid_anon_birth_check       = self._add_cb(
            "Anonymize Birth Date to 01-Jan", uid_layout)
        self.uid_anon_acq_check         = self._add_cb(
            "Anonymize Acquisition Date to 01-Jan", uid_layout)
        self.uid_anon_accession_check   = self._add_cb(
            "Anonymize Accession Number", uid_layout)

        uid_btn = QPushButton("Execute UID-Filtered Sorting")
        uid_btn.clicked.connect(self.execute_uid_sorting)
        uid_layout.addWidget(uid_btn)

        uid_group.setLayout(uid_layout)
        layout.addWidget(uid_group)

        # ==============================================================
        # 2. IN-PLACE DECOMPRESSION PANEL
        # ==============================================================
        decomp_group = QGroupBox("In-place Decompression")
        decomp_layout = QVBoxLayout()
        self.decomp_input_edit = self._dir_row("Input Directory:", decomp_layout)
        decomp_btn = QPushButton("Execute Decompression")
        decomp_btn.clicked.connect(self.execute_decompression)
        decomp_layout.addWidget(decomp_btn)
        decomp_group.setLayout(decomp_layout)
        layout.addWidget(decomp_group)

        # ==============================================================
        # 3. EXPLICIT-VR-LE CONVERSION PANEL
        # ==============================================================
        explicit_group = QGroupBox("Convert to Explicit VR Little Endian  (SLOW!)")
        explicit_layout = QVBoxLayout()
        self.exp_input_edit = self._dir_row("Input Directory:", explicit_layout)
        exp_btn = QPushButton("Execute Conversion")
        exp_btn.clicked.connect(self.execute_explicit)
        explicit_layout.addWidget(exp_btn)
        explicit_group.setLayout(explicit_layout)
        layout.addWidget(explicit_group)

        # --------------------------------------------------
        # footer
        # --------------------------------------------------
        help_btn = QPushButton("Help"); help_btn.clicked.connect(self.show_help)
        layout.addWidget(help_btn)

        info = QLabel("© 2025 Pablo Naval Baudin")
        info.setAlignment(Qt.AlignCenter); layout.addWidget(info)

        disclaimer = QLabel("Internal tool. Not validated against DICOM standard. Use at your own risk.")
        disclaimer.setAlignment(Qt.AlignCenter); disclaimer.setWordWrap(True)
        layout.addWidget(disclaimer)

        self.setLayout(layout)
        self.setWindowTitle("DICOM Sorting Toolkit v1.6.0")
        self.show()

    # ---------- convenience layout helpers ----------
    def _dir_row(self, label, parent_layout):
        lay = QHBoxLayout()
        lay.addWidget(QLabel(label))
        edit = QLineEdit(); lay.addWidget(edit)
        btn  = QPushButton("Browse"); btn.clicked.connect(lambda: self.browse_directory(edit))
        lay.addWidget(btn)
        parent_layout.addLayout(lay)
        return edit

    def _file_row(self, label, parent_layout, info_slot=None):
        lay = QHBoxLayout()
        lay.addWidget(QLabel(label))
        edit = QLineEdit(); lay.addWidget(edit)
        btn  = QPushButton("Browse"); btn.clicked.connect(lambda: self.browse_file(edit))
        lay.addWidget(btn)
        if info_slot:
            i_btn = QPushButton("?"); i_btn.clicked.connect(info_slot)
            lay.addWidget(i_btn)
        parent_layout.addLayout(lay)
        return edit

    def _add_cb(self, text, parent_layout):
        cb = QCheckBox(text); parent_layout.addWidget(cb); return cb

    # ---------- common browse helpers ----------
    def browse_directory(self, line_edit):
        d = QFileDialog.getExistingDirectory(self, "Select Directory")
        if d: line_edit.setText(d)

    def browse_file(self, line_edit):
        f, _ = QFileDialog.getOpenFileName(self, "Select File")
        if f: line_edit.setText(f)

# ───────────────────────────────────────────────────────────────────────────────
#  Replace every   def …(): ...    placeholder with the real implementation
# ───────────────────────────────────────────────────────────────────────────────

    # ---------- information pop-ups ----------
    def show_anon_info(self):
        QMessageBox.information(self, "Anonymization Info",
            "No Anonymization: No changes to patient information.\n"
            "  Combine with 'Skip patients not in ID correlation file'\n"
            "  to keep original PatientIDs but only sort patients on the list.\n\n"
            "Basic Anonymization:\n"
            "- Anonymizes: PatientName, PatientID\n"
            "- If no ID correlation file is provided, a random 8-character ID is used\n"
            "  (unless 'Skip patients not in ID correlation file' is checked, in which\n"
            "  case unmapped patients are skipped instead).\n\n"
            "Strict Anonymization (adds to Basic):\n"
            "- Anonymizes all Patient-* tags, removes private tags,\n"
            "- Creates dummy UIDs, etc.\n\n"
            "Extras: toggle birth/acquisition date, accession number, preserve private tags.")

    def show_id_info(self):
        QMessageBox.information(self, "ID Correlation File",
            "Tab-separated or CSV with two columns:\n"
            "   oldID    newID\n"
            "Used to map original PatientIDs (or PatientNames) to new IDs.")

    def show_folder_info(self):
        QMessageBox.information(self, "Folder Structure",
            "Choose how output folders are organised:\n\n"
            "1) PatientID / StudyDate / SeriesNumber_Description\n"
            "   Default. Studies on the same date for the same patient share a folder.\n\n"
            "2) PatientID / StudyDate_StudyInstanceUID / SeriesNumber_Description\n"
            "   Each study gets its own folder, even if performed on the same date.\n"
            "   Useful when a patient has multiple studies on the same day.")

    def show_uid_filter_info(self):
        QMessageBox.information(self, "UID Filter Files",
            "Provide one or both files (at least one is required):\n\n"
            "  • Study UIDs file: list of StudyInstanceUIDs to keep.\n"
            "    Listing a StudyInstanceUID keeps EVERY series of that study.\n\n"
            "  • Series UIDs file: list of SeriesInstanceUIDs to keep.\n"
            "    Only the listed series will be kept.\n\n"
            "File format (same for both):\n"
            "  - One UID per line.\n"
            "  - Lines starting with '#' are comments.\n"
            "  - Inline trailing comments after '#' are stripped.\n"
            "  - Blank lines are ignored.\n\n"
            "A file is kept if its StudyInstanceUID is in the study list\n"
            "OR its SeriesInstanceUID is in the series list. Everything else\n"
            "is skipped.")

    def show_help(self):
        QMessageBox.information(self, "Help",
            "1. **Sorting** – choose input & output, anonymization level, options.\n"
            "2. **In-place Decompression** – pick a folder, all DICOMs are decompressed.\n"
            "3. **Explicit VR Conversion** – pick a folder, every DICOM is rewritten\n"
            "   as Explicit VR Little Endian (slow & grows files).\n\n"
            "See the GitHub repo for details.")

    # ---------- sorting ----------
    def execute_sorting(self):
        inp  = self.input_edit.text()
        outp = self.output_edit.text()
        if not inp or not outp:
            QMessageBox.warning(self, "Error", "Select both input and output directories.")
            return

        basic  = self.basic_anon_radio.isChecked()
        strict = self.strict_anon_radio.isChecked()
        skip_unmapped = self.skip_unmapped_check.isChecked()
        id_path = self.id_edit.text().strip()

        # Validate: skip-unmapped requires a correlation file
        if skip_unmapped and not id_path:
            QMessageBox.warning(self, "Error",
                "'Skip patients not in ID correlation file' is checked, but no\n"
                "ID correlation file was provided. Please select a correlation file\n"
                "or uncheck the option.")
            return

        id_map = read_id_correlation(id_path) if id_path else None
        include_study_uid = bool(self.folder_struct_combo.currentData())

        self.progress_dialog = QProgressDialog("Sorting …", "Cancel", 0, 100, self)
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setAutoClose(False)
        self.progress_dialog.canceled.connect(self.cancel_sorting)
        self.progress_dialog.show()

        self.sorting_thread = SortingThread(
            inp, outp,
            basic or strict,
            id_map,
            self.decompress_check.isChecked(),
            strict,
            self.skip_derived_check.isChecked(),
            self.skip_burned_check.isChecked(),
            self.id_from_name_check.isChecked(),
            self.anonymize_birth_date_check.isChecked(),
            self.anonymize_acquisition_date_check.isChecked(),
            self.preserve_private_tags_check.isChecked(),
            self.anonymize_accession_check.isChecked(),
            include_study_uid,
            skip_unmapped
        )
        self.sorting_thread.progress.connect(self.update_sorting_progress)
        self.sorting_thread.finished.connect(self.sorting_finished)
        self.sorting_thread.error.connect(self.sorting_error)
        self.sorting_thread.start()

    def cancel_sorting(self):
        if self.sorting_thread and self.sorting_thread.isRunning():
            self.sorting_thread.cancel()
            self.sorting_thread.wait()
        if self.progress_dialog:
            self.progress_dialog.close()

    # ---------- UID-filtered sorting ----------
    def execute_uid_sorting(self):
        inp  = self.uid_input_edit.text()
        outp = self.uid_output_edit.text()
        if not inp or not outp:
            QMessageBox.warning(self, "Error", "Select both input and output directories.")
            return

        study_path  = self.uid_study_edit.text().strip()
        series_path = self.uid_series_edit.text().strip()
        if not study_path and not series_path:
            QMessageBox.warning(self, "Error",
                "Provide at least one UID filter file (Study UIDs or Series UIDs).")
            return

        try:
            study_set  = read_uid_filter(study_path)  if study_path  else None
            series_set = read_uid_filter(series_path) if series_path else None
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read UID filter file:\n{e}")
            return

        if (study_set is not None and len(study_set) == 0) and \
           (series_set is None or len(series_set) == 0):
            QMessageBox.warning(self, "Error",
                "The UID filter files are empty. Nothing would be processed.")
            return

        basic  = self.uid_basic_anon_radio.isChecked()
        strict = self.uid_strict_anon_radio.isChecked()
        skip_unmapped = self.uid_skip_unmapped_check.isChecked()
        id_path = self.uid_id_edit.text().strip()

        if skip_unmapped and not id_path:
            QMessageBox.warning(self, "Error",
                "'Skip patients not in ID correlation file' is checked, but no\n"
                "ID correlation file was provided.")
            return

        id_map = read_id_correlation(id_path) if id_path else None
        include_study_uid = bool(self.uid_folder_struct_combo.currentData())

        n_study = len(study_set) if study_set else 0
        n_series = len(series_set) if series_set else 0

        self.progress_dialog = QProgressDialog(
            f"UID-Filtered Sorting (study={n_study}, series={n_series}) …",
            "Cancel", 0, 100, self)
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setAutoClose(False)
        self.progress_dialog.canceled.connect(self.cancel_sorting)
        self.progress_dialog.show()

        self.sorting_thread = SortingThread(
            inp, outp,
            basic or strict,
            id_map,
            self.uid_decompress_check.isChecked(),
            strict,
            self.uid_skip_derived_check.isChecked(),
            self.uid_skip_burned_check.isChecked(),
            self.uid_id_from_name_check.isChecked(),
            self.uid_anon_birth_check.isChecked(),
            self.uid_anon_acq_check.isChecked(),
            self.uid_preserve_private_check.isChecked(),
            self.uid_anon_accession_check.isChecked(),
            include_study_uid,
            skip_unmapped
        )
        self.sorting_thread.set_uid_filters(study_set, series_set)
        self.sorting_thread.progress.connect(self.update_sorting_progress)
        self.sorting_thread.finished.connect(self.sorting_finished)
        self.sorting_thread.error.connect(self.sorting_error)
        self.sorting_thread.start()

    def update_sorting_progress(self, v):
        if self.progress_dialog and not self.progress_dialog.wasCanceled():
            self.progress_dialog.setValue(v)

    def sorting_finished(self):
        if self.progress_dialog: self.progress_dialog.close()
        QMessageBox.information(self, "Success", "Sorting completed.")
        self.sorting_thread = self.progress_dialog = None

    def sorting_error(self, msg):
        if self.progress_dialog: self.progress_dialog.close()
        QMessageBox.critical(self, "Error", f"Sorting failed:\n{msg}")
        self.sorting_thread = self.progress_dialog = None

    # ---------- decompression ----------
    def execute_decompression(self):
        d = self.decomp_input_edit.text()
        if not d:
            QMessageBox.warning(self, "Error", "Select an input directory.")
            return

        self.decomp_thread = DecompressionThread(d)
        self.decomp_thread.progress.connect(self.update_progress)
        self.decomp_thread.finished.connect(self.decompression_finished)
        self.decomp_thread.error.connect(self.decompression_error)
        self.decomp_thread.start()

        self.progress_dialog = QProgressDialog("Decompressing …", "Cancel", 0, 100, self)
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.canceled.connect(self.decomp_thread.terminate)
        self.progress_dialog.show()

    def update_progress(self, v):
        if self.progress_dialog:
            self.progress_dialog.setValue(v)

    def decompression_finished(self):
        if self.progress_dialog: self.progress_dialog.close()
        QMessageBox.information(self, "Success", "Decompression completed.")
        self.decomp_thread = self.progress_dialog = None

    def decompression_error(self, msg):
        if self.progress_dialog: self.progress_dialog.close()
        QMessageBox.critical(self, "Error", f"Decompression failed:\n{msg}")
        self.decomp_thread = self.progress_dialog = None



    # ---------- explicit VR conversion ----------

    def execute_explicit(self):
        d = self.exp_input_edit.text()
        if not d:
            QMessageBox.warning(self, "Error", "Please select an input directory.")
            return
        if QMessageBox.question(self, "Confirm – slow operation",
                                "Conversion can be slow and will increase file size.\nProceed?",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return

        self.exp_thread = ExplicitThread(d)
        self.exp_thread.progress.connect(self.update_sorting_progress)  # reuse existing progress slot
        self.exp_thread.finished.connect(self.explicit_finished)
        self.exp_thread.error.connect(self.explicit_error)
        self.exp_thread.start()

        self.progress_dialog = QProgressDialog("Converting …", "Cancel", 0, 100, self)
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.canceled.connect(self.exp_thread.terminate)
        self.progress_dialog.show()


    def explicit_finished(self):
        if self.progress_dialog: self.progress_dialog.close()
        QMessageBox.information(self, "Success", "Conversion completed.")
        self.exp_thread = self.progress_dialog = None

    def explicit_error(self, msg):
        if self.progress_dialog: self.progress_dialog.close()
        QMessageBox.critical(self, "Error", f"Conversion failed:\n{msg}")
        self.exp_thread = self.progress_dialog = None


# --------------------------------------------------
# main
# --------------------------------------------------
if __name__ == '__main__':
    multiprocessing.freeze_support()
    app = QApplication(sys.argv)
    gui = DicomSortingGUI()
    sys.exit(app.exec_())
