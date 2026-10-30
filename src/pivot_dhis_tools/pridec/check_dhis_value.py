import numpy as np

def check_dhis_value(df):
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


def check_import_value(df, max_threshold: int):
    this_value = df['value']
    
    err_1 = this_value.isna().sum()
    err_2 = (this_value > max_threshold).sum()
    err_3 = (this_value < 0).sum()

    summary = f"numNA: {err_1} | minimum value: {this_value.min()} | maximum value: {this_value.max()} | negative values: {err_3}"

    problems = []
    if err_1 > 0:
        problems.append(f"{err_1} missing (NA) values")
    if err_2 >0:
        problems.append(f"{err_2} orgUnits exceed case threshold of {max_threshold}")
    if err_3 > 0:
        problems.append(f"{err_3} negative values")

    if problems:
        raise ValueError(f"Potential errors in data to be imported: {'; '.join(problems)}. {summary}")

    return(summary)