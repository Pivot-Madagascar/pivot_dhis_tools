import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta
import logging

from ..get_dataElements import get_dataElements
from ..create_period_range import create_period_range
from .check_dhis_value import  check_import_value
from ..post_dataElements import post_dataElements


logger = logging.getLogger(__name__)

__all__ = ["import_pivot_com", "import_pivot_csb", "fetch_pivot_com_etlhub", "fetch_pivot_csb_etlhub"]

COM_MAX_THRESHOLD = 100  # maximum cases per fokontany and period
CSB_MAX_THRESHOLD = 500  # maximum cases per CSB and month

COM_ELEMENTS = {
    # target dataElement           : source dx ids in the Pivot instance
    "pridec_historic_COMMalaria":  ["vduU8d1GZbW"],                  # vduU8d1GZbW : RMA_COM_PCIMEc Nombre de cas de fièvre testés avec TDR positif 
    "pridec_historic_COMRespinf":  ["hJ5pa6wO4nJ", "CmDXCmmywrj"],   # hJ5pa6wO4nJ : RMA_COM_PCIMEc Nombre d’enfants présentant de pneumonie, CmDXCmmywrj : RMA_COM_PCIMEc Nombre d’enfants présentant de  toux ou rhume
    "pridec_historic_COMDiarrhea": ["DjsQEzPDAoN", "f4hrhsiz49l"],   #DjsQEzPDAoN : RMA_COM_PCIMEc Nombre d’enfants présentant de diarrhée avec signes de danger, f4hrhsiz49l : RMA_COM_PCIMEc Nombre d’enfants présentant de diarrhée simple
}

# the 21 Ifanadiana CSB orgUnits
CSB_IDS = [
    "D9UWDj19ljP", "U1YeJp3NDNV", "DDR2w1c1GyE", "uWoBok9YyvB",
    "O1wNJut8eci", "FGM6Ric1YnC", "r4U7PhBKR7S", "RRe6ic0AU1Z",
    "okDqhh9n4yT", "z6kDxHwInUT", "h0z1bKoHDrU", "Pi2y9HFBDRj",
    "pczrAub8lnt", "YCvVB1VwWi0", "hXuxS0MOq3b", "mBZLeZ7Irx6",
    "WCqkkkKNJEi", "EE6WwIMgQ0F", "M38BJM8ju1A", "ZPvH8UsgwYv",
    "QHPyq70qulM"
]

CHILD_COC = "co:HIsTqXVmDdV;TJlRzxBqiqG;ncBrGeQ9w2g;YAxDQLsxeT0;fEAWzG9dj98;yprE1T7gBUw;lwrX7wJqjhW;DSaVQguA6v6"

CSB_ELEMENTS = {
    "pridec_historic_CSBMalaria": dict(
        fetches=[dict(dx_query="dx:wuwA8DT9h7c", includeNumDen=True), # wuwA8DT9h7c (Numerator) - RDT + at CSB for 2-11 months
                dict(dx_query="dx:PVu7GgpuJNV", includeNumDen=True)], # PVu7GgpuJNV (Numerator) - RDT + at CSB for 1-5 years
        value_col="numerator"),
    "pridec_historic_CSBRespinf": dict(
        fetches=[dict(dx_query="dx:eHrqdPNZW6m;E4KUPwZuLrG", co_query=CHILD_COC, includeNumDen=False)],
        value_col="value"),
    "pridec_historic_CSBDiarrhea": dict(
        fetches=[dict(dx_query="dx:uw5yUgtSYfQ;kvoIFhX5RMA;NG2mlKX2D6C", co_query=CHILD_COC, includeNumDen=False)],
        value_col="value"),
}


def _check_summary(df, target, *, max_threshold, logger):
    """Run `check_import_value` and return a summary dict instead of raising.

    Returns:
        dict with `text` (summary string, returned whether or not the check passes),
        `flagged` (True if the check raised a ValueError) and `error`
        (the ValueError message or None).
    """
    try:
        check_text = check_import_value(df, max_threshold=max_threshold)
        logger.info("%s has the following characteristics: %s", target, check_text)
        return {"text": check_text, "flagged": False, "error": None}
    except ValueError as e:
        logger.warning("%s failed the import value check: %s", target, e)
        return {"text": getattr(e, "summary", None), "flagged": True, "error": str(e)}


def _check_and_post(df, target, *, max_threshold, dhis_url, dhis_token, dryRun, logger):
    if df.empty:
        logger.warning("Skipping import of %s: no values left to import after removing missing data", target)
        return

    try:
        summary = check_import_value(df, max_threshold=max_threshold)
        logger.info("%s has the following characteristics: %s", target, summary)
    except ValueError as e:
        logger.warning("%s failed the import value check: %s", target, e)
        try:
            answer = input(f"{target} failed the value check. Continue to post step anyway? [y/N] ")
            reason = "not approved at the prompt"
        except EOFError:
            # no interactive terminal available, so treat as not approved
            answer = ""
            reason = "no interactive terminal to approve it"
        if answer.strip().lower() not in ("y", "yes"):
            logger.warning("Skipping import of %s: failed the value check and %s", target, reason)
            return
        logger.info("Continuing to post %s despite failed check", target)

    logger.info("Importing %s into PRIDE-C instance with dryRun = %s", target, dryRun)
    resp = post_dataElements(dhis_url=dhis_url, payload={"dataValues": df.to_dict(orient="records")},
                             token=dhis_token, dryRun=dryRun)
    if resp.ok:
        logger.info("Imported %s", target)
        logger.debug("Response: %s", resp.text)
    else:
        logger.error("Failed to import %s with status code %s", target, resp.status_code)
        logger.error("Response: %s", resp.text)


def _fetch_com_element(target, dx_ids, *, period_list, org_query, full_grid,
                       pivot_url, pivot_token, logger):
    logger.info("Fetching %s", target)
    raw = get_dataElements(dhis_url=pivot_url, token=pivot_token,
                           dx_query="dx:" + ";".join(dx_ids),
                           pe_query=period_list, ou_query=org_query,
                           includeNumDen=False)
    raw = (
        raw
        .rename(columns={'ou': 'orgUnit', 'pe': 'period'})
        .assign(value=lambda x: pd.to_numeric(x['value'], errors='coerce', downcast='integer'))
    )
    n_bad = raw['value'].isna().sum()
    if n_bad > 0:
        logger.warning("%s: %d source rows had a missing or non-numeric value and were ignored", target, n_bad)

    # drop the bad rows before summing: an all-NaN group would otherwise sum to 0 and be
    # imported as a real zero even where no consultations were reported
    df = (
        raw
        .dropna(subset=['value'])
        .groupby(['period', 'orgUnit'], as_index=False)
        .agg(value=('value', 'sum'))
        .merge(full_grid, on=['orgUnit', 'period'], how="outer")
        .assign(value=lambda x: x.apply(lambda r: 0 if pd.notna(r['case_all']) and pd.isna(r['value']) else r['value'], axis=1))
        .loc[:, ['period', 'orgUnit', 'value']]
        .assign(dataElement=target, categoryOptionCombo='pridec_COC_u5')
    )
    n_unreported = df['value'].isna().sum()
    if n_unreported > 0:
        logger.info("%s: %d orgUnit-periods have no value and no consultations, so were not imported",
                    target, n_unreported)
    df = (df.dropna(subset=['value'])
            .assign(value=lambda x: pd.to_numeric(x['value'], errors='coerce', downcast='integer')))
    return df


def _prepare_com(*, pivot_url, pivot_token, prior_months, parent_ou):
    """Build the period list, orgUnit query and orgUnit-period grid shared by the COM functions.

    Total consultations (RMA_COM_PCIMEc, `lq38tLcfEi7`, Nombre d'enfants reçu au site) are
    fetched to tell missing data from zeroes.

    Returns:
        Tuple of (period_list, com_org_query, full_grid).
    """
    period_list = create_period_range(start=(date.today() - relativedelta(months=prior_months)))
    com_org_query = f"ou:LEVEL-6;{';'.join(p.strip() for p in parent_ou.split(',') if p.strip())}"

    com_get = get_dataElements(dhis_url=pivot_url,
                               token=pivot_token,
                               dx_query="dx:lq38tLcfEi7",
                               pe_query=period_list,
                               ou_query=com_org_query,
                               includeNumDen=False)
    com_all = (
        com_get
        .rename(columns={'ou': 'orgUnit', 'pe': 'period', 'value': 'case_all'})
        .assign(case_all=lambda x: pd.to_numeric(x['case_all'], errors='coerce', downcast='integer'))
    )

    full_grid = (
        pd.DataFrame({'orgUnit': com_all['orgUnit'].unique()})
        .merge(pd.DataFrame({'period': com_all['period'].unique()}), how='cross')
        .merge(com_all, on=['orgUnit', 'period'], how="outer")
    )
    return period_list, com_org_query, full_grid


def import_pivot_com(dhis_url: str,
                     dhis_token: str, 
                     pivot_token: str,
                     pivot_url: str,
                     dryRun: bool = True,
                     prior_months: int = 8,
                     parent_ou: str = 'VtP4BdCeXIo'):
    """
    Import community (COM) case counts from the Pivot instance into PRIDE-C.

    Fetches fokontany-level (LEVEL-6) data under `parent_ou` for the last `prior_months`
    months and imports three dataElements: `pridec_historic_COMMalaria`,
    `pridec_historic_COMRespinf` and `pridec_historic_COMDiarrhea`. Where a source
    element has several dx ids they are summed. Total consultations
    (RMA_COM_PCIMEc, `lq38tLcfEi7`) are used to tell missing data from zeroes: an
    orgUnit and period that reported consultations but has no value for a disease
    is imported as 0, and one with no consultations is not imported.

    Each element is checked with `check_import_value` (maximum 100 cases per fokontany
    and period) before posting. If the check fails, you are prompted on the terminal
    whether to post anyway; with no terminal the element is skipped. An element that
    is skipped or fails to post is logged and does not stop the others.

    Args:
        dhis_url: URL of the PRIDE-C DHIS2 instance to import into.
        dhis_token: Personal access token for the PRIDE-C instance.
        pivot_token: Personal access token for the Pivot instance.
        pivot_url: URL of the Pivot DHIS2 instance to read from.
        dryRun: If True (default), the POST is a DHIS2 dry run and nothing is saved.
            Set to False to actually import the data.
        prior_months: Number of months before today to start the period range.
            The range runs up to, but excludes, the current month. Default = 8.
        parent_ou: orgUnit id(s) whose level 6 descendants are imported. Several ids
            can be given separated by commas. Default = 'VtP4BdCeXIo'.

    Returns:
        None. Progress, check summaries and the outcome of each import are written
        to the logger.

    Raises:
        requests.HTTPError: If a request to the Pivot instance fails.
        ValueError: If `pivot_token` is empty, so no authentication is supplied.
        ValueError: If `dhis_token` is empty, so the POST has no authentication.
    """

    if dryRun:
        logger.info("DRY RUN — Data will not be imported into PRIDE-C instance")
    else:
        logger.info("NORMAL RUN - Data will be imported into PRIDE-C instance")

    logger.info("Importing level 6 orgUnits (fokontany) under %s", parent_ou)

    period_list, com_org_query, full_grid = _prepare_com(
        pivot_url=pivot_url, pivot_token=pivot_token, prior_months=prior_months, parent_ou=parent_ou)
    
    for target, dx_ids in COM_ELEMENTS.items():
        fetched_df = _fetch_com_element(target, dx_ids, period_list=period_list, org_query=com_org_query,
                        full_grid=full_grid, pivot_url=pivot_url, pivot_token=pivot_token, logger=logger)
        
        _check_and_post(fetched_df, target, max_threshold=COM_MAX_THRESHOLD, dhis_url=dhis_url, dhis_token=dhis_token,
                   dryRun=dryRun, logger=logger)

def fetch_pivot_com_etlhub(
                     pivot_token: str,
                     pivot_url: str,
                     prior_months: int = 8,
                     parent_ou: str = 'VtP4BdCeXIo'):
    """
    Fetch and check community (COM) case counts from the Pivot instance, without importing.

    Fetches fokontany-level (LEVEL-6) data under `parent_ou` for the last `prior_months`
    months for three dataElements: `pridec_historic_COMMalaria`,
    `pridec_historic_COMRespinf` and `pridec_historic_COMDiarrhea`. Where a source
    element has several dx ids they are summed. Total consultations
    (RMA_COM_PCIMEc, `lq38tLcfEi7`) are used to tell missing data from zeroes: an
    orgUnit and period that reported consultations but has no value for a disease
    is given 0, and one with no consultations is dropped.

    Each element is checked with `check_import_value` (maximum 100 cases per fokontany
    and period). A failed check, including empty data, does not stop the fetch; it is
    recorded in the summary.

    Args:
        pivot_token: Personal access token for the Pivot instance.
        pivot_url: URL of the Pivot DHIS2 instance to read from.
        prior_months: Number of months before today to start the period range.
            The range runs up to, but excludes, the current month. Default = 8.
        parent_ou: orgUnit id(s) whose level 6 descendants are imported. Several ids
            can be given separated by commas. Default = 'VtP4BdCeXIo'.

    Returns:
        List of dicts, one per COM element. Each dict contains:
            - dataElement: the target dataElement name
            - fetched_data: the fetched data as a list of records (dicts)
            - summary: dict with
                - text: the `check_import_value` summary string, returned whether or not the check passes
                - flagged: True if `check_import_value` raised a ValueError
                - error: the ValueError message if flagged, otherwise None
    Raises:
        requests.HTTPError: If a request to the Pivot instance fails.
        ValueError: If `pivot_token` is empty, so no authentication is supplied.
    """
    logger.info("Fetching level 6 orgUnits (fokontany) under %s", parent_ou)
    
    period_list, com_org_query, full_grid = _prepare_com(
        pivot_url=pivot_url, pivot_token=pivot_token, prior_months=prior_months, parent_ou=parent_ou)


    results = []

    for target, dx_ids in COM_ELEMENTS.items():
        fetched_df = _fetch_com_element(target, dx_ids, period_list=period_list, org_query=com_org_query,
                        full_grid=full_grid, pivot_url=pivot_url, pivot_token=pivot_token,
                        logger=logger)

        # run data check; a failed check flags the element but does not stop the fetch
        results.append({
            "dataElement": target,
            "fetched_data": fetched_df.to_dict(orient="records"),
            "summary": _check_summary(fetched_df, target, max_threshold=COM_MAX_THRESHOLD, logger=logger),
        })

    return results


def _fetch_csb_element(target, spec, *, period_list, org_query,
                       pivot_url, pivot_token, logger):
    logger.info("Fetching %s", target)
    raw = pd.concat(
        [get_dataElements(dhis_url=pivot_url, token=pivot_token,
                          pe_query=period_list, ou_query=org_query, **f)
         for f in spec["fetches"]],
        ignore_index=True)
    
    df = (raw.rename(columns={'ou': 'orgUnit', 'pe': 'period'})
             .assign(v=lambda x: pd.to_numeric(x[spec["value_col"]], errors='coerce', downcast='integer'))
             )
    n_bad = df['v'].isna().sum()
    if n_bad > 0:
        logger.warning("%s: %d source rows had a missing or non-numeric value and were skipped", target, n_bad)

    df = (df.dropna(subset=['v'])
             .groupby(['period', 'orgUnit'], as_index=False)
             .agg(value=('v', 'sum'))
             .assign(dataElement=target, categoryOptionCombo='pridec_COC_u5')
             .assign(value=lambda x: pd.to_numeric(x['value'], errors='coerce', downcast='integer')))
    return df


def _prepare_csb(*, prior_months):
    """Build the period list and orgUnit query shared by the CSB functions.

    Returns:
        Tuple of (period_list, csb_org_query).
    """
    period_list = create_period_range(start=(date.today() - relativedelta(months=prior_months)))
    csb_org_query = f"ou:{';'.join(CSB_IDS)}"
    return period_list, csb_org_query


def import_pivot_csb(dhis_url: str,
                     dhis_token: str, 
                     pivot_token: str,
                     pivot_url: str,
                     dryRun: bool = True,
                     prior_months: int = 8):
    """
    Import clinic (CSB) case counts from the Pivot instance into PRIDE-C.

    Fetches data for the 21 Ifanadiana CSB orgUnits (hard coded) for the last
    `prior_months` months and imports three dataElements:
    `pridec_historic_CSBMalaria` , `pridec_historic_CSBRespinf` and
    `pridec_historic_CSBDiarrhea`.
    Values are summed by orgUnit and period. Rows with a missing value are dropped,
    and no zeroes are filled in for missing data.

    Each element is checked with `check_import_value` (maximum 500 cases per CSB/month)
    before posting. If the check fails, you are prompted on the terminal
    whether to post anyway; with no terminal the element is skipped. An element that
    is skipped or fails to post is logged and does not stop the others.

    Args:
        dhis_url: URL of the PRIDE-C DHIS2 instance to import into.
        dhis_token: Personal access token for the PRIDE-C instance.
        pivot_token: Personal access token for the Pivot instance.
        pivot_url: URL of the Pivot DHIS2 instance to read from.
        dryRun: If True (default), the POST is a DHIS2 dry run and nothing is saved.
            Set to False to actually import the data.
        prior_months: Number of months before today to start the period range.
            The range runs up to, but excludes, the current month. Default = 8.

    Returns:
        None. Progress, check summaries and the outcome of each import are written
        to the logger.

    Raises:
        requests.HTTPError: If a request to the Pivot instance fails.
        ValueError: If `pivot_token` is empty, so no authentication is supplied.
        ValueError: If `dhis_token` is empty, so the POST has no authentication.
    """

    if dryRun:
        logger.info("DRY RUN — Data will not be imported into PRIDE-C instance")
    else:
        logger.info("NORMAL RUN - Data will be imported into PRIDE-C instance")

    logger.info("Importing CSB cases for Ifanadiana")

    period_list, csb_org_query = _prepare_csb(prior_months=prior_months)

    for target, spec in CSB_ELEMENTS.items():
        fetched_df = _fetch_csb_element(target, spec, period_list=period_list, org_query=csb_org_query,
                        pivot_url=pivot_url, pivot_token=pivot_token, logger=logger)

        _check_and_post(fetched_df, target, max_threshold=CSB_MAX_THRESHOLD, dhis_url=dhis_url,
                        dhis_token=dhis_token, dryRun=dryRun, logger=logger)


def fetch_pivot_csb_etlhub(
                     pivot_token: str,
                     pivot_url: str,
                     prior_months: int = 8):
    """
    Fetch and check clinic (CSB) case counts from the Pivot instance, without importing.

    Fetches data for the 21 Ifanadiana CSB orgUnits (hard coded) for the last
    `prior_months` months for three dataElements: `pridec_historic_CSBMalaria`,
    `pridec_historic_CSBRespinf` and `pridec_historic_CSBDiarrhea`.
    Values are summed by orgUnit and period. Rows with a missing value are dropped,
    and no zeroes are filled in for missing data.

    Each element is checked with `check_import_value` (maximum 500 cases per CSB/month).
    A failed check, including empty data, does not stop the fetch; it is recorded in
    the summary.

    Args:
        pivot_token: Personal access token for the Pivot instance.
        pivot_url: URL of the Pivot DHIS2 instance to read from.
        prior_months: Number of months before today to start the period range.
            The range runs up to, but excludes, the current month. Default = 8.

    Returns:
        List of dicts, one per CSB element. Each dict contains:
            - dataElement: the target dataElement name
            - fetched_data: the fetched data as a list of records (dicts)
            - summary: dict with
                - text: the `check_import_value` summary string, returned whether or not the check passes
                - flagged: True if `check_import_value` raised a ValueError
                - error: the ValueError message if flagged, otherwise None
    Raises:
        requests.HTTPError: If a request to the Pivot instance fails.
        ValueError: If `pivot_token` is empty, so no authentication is supplied.
    """
    logger.info("Fetching CSB cases for Ifanadiana")

    period_list, csb_org_query = _prepare_csb(prior_months=prior_months)

    results = []

    for target, spec in CSB_ELEMENTS.items():
        fetched_df = _fetch_csb_element(target, spec, period_list=period_list, org_query=csb_org_query,
                        pivot_url=pivot_url, pivot_token=pivot_token, logger=logger)

        # run data check; a failed check flags the element but does not stop the fetch
        results.append({
            "dataElement": target,
            "fetched_data": fetched_df.to_dict(orient="records"),
            "summary": _check_summary(fetched_df, target, max_threshold=CSB_MAX_THRESHOLD, logger=logger),
        })

    return results


