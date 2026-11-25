import pandas as pd

def check_dhis_value(df: pd.DataFrame) -> str:
    """Check that a DataFrame of values has no missing or negative values.

    Args:
        df: Data with a ``value`` column of numbers.

    Returns:
        A one-line summary: number of missing values, minimum, maximum and
        number of negative values. Empty data passes, with a NaN minimum
        and maximum.

    Raises:
        ValueError: If any value is missing (NaN/None) or negative.
        KeyError: If `df` has no ``value`` column.
    """
    this_value = df['value']
    
    err_1 = this_value.isna().sum()
    # print(f"numNA: {err_1}")
    
    # print("minimum value:", this_value.min())
    # print("maximum value:", this_value.max())
    
    err_3 = (this_value < 0).sum()
    # print(f"negative values: {err_3}")

    
    if (err_1 + err_3) > 0:
        raise ValueError("Incorrectly formatted data.")
    
    return(f"numNA: {err_1} | minimum value: {this_value.min()} | maximum value: {this_value.max()} | negative values: {err_3}")


def check_import_value(df: pd.DataFrame, max_threshold: int) -> str:
    """Check values before they are imported into DHIS2.

    Fails if the data is empty, or has missing, negative, or implausibly
    large values. All problems found are listed in one error.

    Args:
        df: Data with a ``value`` column of numbers.
        max_threshold: Largest value allowed; values strictly above it fail.

    Returns:
        A one-line summary: number of missing values, minimum, maximum,
        number of negative values and number of values.

    Raises:
        ValueError: If the data is empty or any value is missing, negative or
            above `max_threshold`. The summary is appended to the message
            and also set as the error's ``summary`` attribute.
        KeyError: If `df` has no ``value`` column.
    """
    this_value = df['value']

    is_empty = this_value.empty
    err_1 = this_value.isna().sum()
    err_2 = (this_value > max_threshold).sum()
    err_3 = (this_value < 0).sum()

    summary = f"numNA: {err_1} | minimum value: {this_value.min()} | maximum value: {this_value.max()} | negative values: {err_3} | number of values: {len(this_value)}"

    problems = []
    if is_empty:
        problems.append("no values to import (data is empty)")
    if err_1 > 0:
        problems.append(f"{err_1} missing (NA) values")
    if err_2 > 0:
        problems.append(f"{err_2} orgUnits exceed case threshold of {max_threshold}")
    if err_3 > 0:
        problems.append(f"{err_3} negative values")

    if problems:
        err = ValueError(f"Potential errors in data to be imported: {'; '.join(problems)}. {summary}")
        err.summary = summary  # lets callers keep the summary text when the check fails
        raise err

    return(summary)