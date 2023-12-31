import configparser
import datetime
import logging
import os
import re

import dateutil.parser
import pandas as pd

from vm.logging import get_logger
from vm.constants import (
    DICT_PRESTAZIONNE,
    QUAS,
    QUAS_PENSIONATI,
    SCADENZA_REGEX,
    PNR_REGEX
)


# Initialize logger
logger = get_logger("../config.ini")

for _ in ("urllib3", "websockets", "pyppeteer", "asyncio", "selenium"):
    logging.getLogger(_).setLevel(logging.CRITICAL)


# TODO use scadenza, handle two PNR on two lines
def check_scadenza():
    pass


def filter_minor_from_df(df_patients: pd.DataFrame) -> pd.DataFrame:
    """
    Filter the DataFrame to include only patients who are 18 years or older.

    Args:
        df (pd.DataFrame): The input DataFrame.

    Returns:
        pd.DataFrame: The filtered DataFrame.
    """
    nb_patient_before = len(df_patients.index)
    df_patients["age"] = (pd.Timestamp("now") - df_patients["Data_Di_Nascita"]).astype(
        "<m8[Y]"
    )
    result = df_patients[df_patients["age"] >= 18]
    nb_patient_after = len(result.index)
    nb_minor = nb_patient_before - nb_patient_after
    if nb_minor > 0:
        logger.debug(
            f"{nb_minor} patients were minor and therefore dropped from the file"
        )
    else:
        logger.debug(f"No minor patient detected")
    return result


def filter_accepted_insurances(
    df_patients: pd.DataFrame, accepted_insurances: tuple[str]
) -> pd.DataFrame:
    """
    Filter the DataFrame to select appointement that matches the accepted insurances.

    Args:
        df (pd.DataFrame): The input DataFrame.
        accepted_insurances (tuple[str]): A tuple of accepted insurances.

    Returns:
        pd.DataFrame: The filtered DataFrame.
    """
    nb_patient_before = len(df_patients.index)
    # We could do with the column "BusinessPartner" that contains
    # an int that seems to be a indentifiant of the insurance
    result = df_patients.loc[
        df_patients["Descrizione_BusinessPartner"].isin(accepted_insurances)
    ]

    nb_patient_after = len(df_patients.index)
    if nb_patient_before != nb_patient_after:
        dropped_patients = nb_patient_before - nb_patient_after
        logger.warning(
            f"{dropped_patients} patients were dropped because"
            " they don't have the correct insurance, this should not happen"
        )
    return result


def add_pnr_to_df(df_patients: pd.DataFrame) -> pd.DataFrame:
    """
    Add the PNR information to the DataFrame.

    Args:
        df (pd.DataFrame): The input DataFrame.

    Returns:
        pd.DataFrame: The DataFrame with the added PNR column.
    """
    nb_patient_before = len(df_patients.index)
    pnr = df_patients["Note"]
    pnr.dropna(inplace=True)
    # filtered_df = pnr[pnr.str.contains("pnr", case=False)]
    df_patients["PNR"] = pnr.str.findall(PNR_REGEX, re.IGNORECASE)

    # print(df_patients)
    # df_patients["PNR"].fillna("").apply(list)

    idx = df_patients["PNR"].isna()
    df_patients.loc[idx, "PNR"] = df_patients.loc[idx, "PNR"].fillna("[]").apply(eval)

    nb_patient_after = len(df_patients.index)
    nb_patient_after = len(df_patients.index)

    if nb_patient_before != nb_patient_after:
        dropped_patients = nb_patient_before - nb_patient_after
        logger.error(
            f"{dropped_patients} patients were dropped because of their ESAME."
            " This REALLY should not happen. DATA WAS LOST ! "
        )
    return df_patients


def add_check_2nd_pnr(
    df_patients: pd.DataFrame, path_file_second_pnr: str
) -> pd.DataFrame:
    """
    Add a column to the DataFrame to indicate if an appointement requires a second PNR.

    Args:
        df (pd.DataFrame): The input DataFrame.
        path_file_second_pnr (str): Path to file with codes that require a second PNR data.

    Returns:
        pd.DataFrame: The DataFrame with the added column.
    """
    xls = pd.ExcelFile(path_file_second_pnr)
    df_2nd_pnr_osr = pd.read_excel(xls, "OSR")
    df_2nd_pnr_srt = pd.read_excel(xls, "SRT")

    list_2nd_pnr_osr = df_2nd_pnr_osr["Prestazione"].to_list()
    list_2nd_pnr_srt = df_2nd_pnr_srt["Prestazione"].to_list()

    df_patients["second_pnr"] = False
    filtered_osr = df_patients[df_patients["Istituto"] == 1]
    filtered_srt = df_patients[df_patients["Istituto"] == 8]
    df_patients.loc[
        filtered_osr[filtered_osr["Esame"].isin(list_2nd_pnr_osr)].index, "second_pnr"
    ] = True
    df_patients.loc[
        filtered_srt[filtered_srt["Esame"].isin(list_2nd_pnr_srt)].index, "second_pnr"
    ] = True

    second_pnr_count = df_patients["second_pnr"].value_counts()
    nb_second_pnr = second_pnr_count.get(True, 0)
    logger.debug(f"{nb_second_pnr} patients need a second pnr")
    return df_patients


def add_cat_code(df_patients: pd.DataFrame, path_cat_code: str) -> pd.DataFrame:
    """
    Add a column to the DataFrame to indicate if an appointement requires a second PNR.

    Args:
        df (pd.DataFrame): The input DataFrame.
        path_cat_code (str): Path to file with cat codes

    Returns:
        pd.DataFrame: The DataFrame with the added cat codes.
    """
    nb_patient_before = len(df_patients.index)
    xls = pd.ExcelFile(path_cat_code)
    df_cat_code = pd.read_excel(xls, "Codice")
    df_cat_code.drop_duplicates(inplace=True)
    join_right = df_cat_code[["Codice Esame SAP", "ID prestazioni"]]
    joined = pd.merge(
        df_patients,
        join_right,
        left_on="Esame",
        right_on="Codice Esame SAP",
        how="left",
    )
    joined["type_prestazioni"] = joined["ID prestazioni"].map(DICT_PRESTAZIONNE)
    nb_patient_after = len(joined.index)
    if nb_patient_before != nb_patient_after:
        dropped_patients = nb_patient_before - nb_patient_after
        logger.error(
            f"{dropped_patients} patients were dropped because of their ESAME."
            " This REALLY should not happen. DATA WAS LOST !"
        )
    return joined


def extract_scadenza_from_df(df_patients: pd.DataFrame) -> pd.DataFrame:
    """
    Extract scadenza information from the DataFrame and update the DataFrame.

    Args:
        df (pd.DataFrame): The input DataFrame.

    Returns:
        pd.DataFrame: The DataFrame with scadenza info.
    """
    nb_patient_before = len(df_patients.index)

    df_patients["scad"] = ""
    scad = pd.Series(df_patients["Note"])
    scad.dropna(inplace=True)
    scad = scad.str.findall(SCADENZA_REGEX).dropna()
    df_patients["scad"] = (
        scad.str[0].dropna().apply(dateutil.parser.parse, dayfirst=True)
    )

    nb_patient_after = len(df_patients.index)

    if nb_patient_before != nb_patient_after:
        dropped_patients = nb_patient_before - nb_patient_after
        logger.error(
            f"{dropped_patients} patients were dropped because of their Scadenza."
            " This REALLY should not happen. DATA WAS LOST ! "
        )
    return df_patients


def create_df_from_excel(
    path_file_excel_next_appointments: str,
    path_file_second_pnr: str,
    path_cat_code: str,
    accepted_insurances: tuple,
    result_file: str,
):
    """
    Main function (temp) to process data and print the resulting DataFrame.

    Args:
        path_file_excel_next_appointments (str): The root directory path to the files patients excel
        accepted_insurances (tuple[str]): A tuple of accepted insurances.

    Returns:
        None
    """
    # Open the file and get the correct header
    xls = pd.ExcelFile(path_file_excel_next_appointments)
    df_patients = pd.read_excel(xls, QUAS, header=None)
    if "Descrizione_BusinessPartner" not in df_patients.columns:
        df_header = pd.read_excel(xls, "Tabella", header=1)
        df_patients.columns = df_header.columns
    nb_patient = len(df_patients.index)
    logger.debug(f"Excel read {nb_patient} detected")

    df_patients = filter_minor_from_df(df_patients)
    df_patients = filter_accepted_insurances(df_patients, accepted_insurances)
    df_patients = add_pnr_to_df(df_patients)
    df_patients = add_check_2nd_pnr(df_patients, path_file_second_pnr)
    df_patients = add_cat_code(df_patients, path_cat_code)
    df_patients = extract_scadenza_from_df(df_patients)
    df_patients.to_csv(result_file)


def main():
    # Load config file
    config = configparser.ConfigParser()
    config.read("config.ini")

    # Setup paths
    date = datetime.datetime.now().date().__str__()
    path_dir_data = os.path.join(config["path"]["path_dir_data"], date)
    os.makedirs(path_dir_data, exist_ok=True)

    create_df_from_excel(
        path_file_excel_next_appointments=os.path.expanduser(
            config["path"]["path_file_input"],
            os.path.join(path_dir_data, config["path"]["filename_input"])
        ),
        path_file_second_pnr=os.path.expanduser(config["path"]["path_file_second_pnr"]),
        path_cat_code=os.path.expanduser(config["path"]["path_cat_code"]),
        accepted_insurances=(QUAS, QUAS_PENSIONATI),
        result_file=os.path.expanduser(
            config["path"]["path_file_output"].format(
                date=datetime.datetime.now().date()
            ),
            os.path.join(path_dir_data, config["path"]["filename_output"])
        ),
    )


if __name__ == "__main__":
    main()
