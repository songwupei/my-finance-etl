"""Data ingestion pipeline for Excel files."""
import pandas as pd
from kedro.pipeline import Pipeline, node

from ..parser import FinanceExcelParser


def parse_single_excel(excel_data: dict, metadata: dict) -> dict:
    """Parse a single Excel file and return both base info and report data."""
    parser = FinanceExcelParser()

    base_info_records = []
    report_data_records = []

    for sheet_name, df in excel_data.items():
        sheet_type, override = parser.identify_sheet_type(sheet_name)

        if sheet_type == "base_info":
            base_info = parser.parse_base_info_sheet(df, override)
            # Add metadata
            base_info.update({
                "sheet_name": sheet_name,
                **metadata,
            })
            base_info_records.append(base_info)
        elif sheet_type == "report_data":
            report_df = parser.parse_report_sheet(df, sheet_name, override, metadata)
            report_data_records.append(report_df)

    # Combine results
    base_info_df = pd.DataFrame(base_info_records) if base_info_records else pd.DataFrame()
    report_data_df = pd.concat(report_data_records, ignore_index=True) if report_data_records else pd.DataFrame()

    return {
        "base_info": base_info_df,
        "report_data": report_data_df,
    }


def batch_parse_excel_files(catalog) -> dict:
    """Batch parse all Excel files in the catalog."""
    all_base_info = []
    all_report_data = []

    # Find all raw Excel datasets (those starting with 'raw_' and are ExcelDataset type)
    raw_datasets = {}
    for dataset_name, dataset_obj in catalog._datasets.items():
        if dataset_name.startswith("raw_"):
            try:
                # Load the Excel data
                excel_data = dataset_obj.load()
                raw_datasets[dataset_name] = excel_data
            except Exception as e:
                print(f"Warning: Failed to load dataset {dataset_name}: {e}")
                continue

    for dataset_name, excel_data in raw_datasets.items():
        # Extract metadata from dataset object
        dataset_obj = catalog._datasets[dataset_name]
        metadata = getattr(dataset_obj, "metadata", {})
        if not metadata:
            metadata = {"dataset_name": dataset_name}

        result = parse_single_excel(excel_data, metadata)

        if not result["base_info"].empty:
            all_base_info.append(result["base_info"])
        if not result["report_data"].empty:
            all_report_data.append(result["report_data"])

    # Combine all results
    parsed_base_info = pd.concat(all_base_info, ignore_index=True) if all_base_info else pd.DataFrame()
    parsed_report_data = pd.concat(all_report_data, ignore_index=True) if all_report_data else pd.DataFrame()

    return parsed_base_info, parsed_report_data


def create_pipeline(**kwargs) -> Pipeline:
    """Create the data ingestion pipeline."""
    return Pipeline(
        [
            node(
                func=batch_parse_excel_files,
                inputs=["catalog"],
                outputs=["parsed_base_info", "parsed_report_data"],
                name="parse_excel_files",
            ),
        ]
    )