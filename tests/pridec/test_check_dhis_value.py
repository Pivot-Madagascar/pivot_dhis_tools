"""
Tests for the data-quality guards in pridec/check_dhis_value.py:
    - check_dhis_value: rejects NA or negative values
    - check_import_value: rejects empty data, NA, negative values, and values
      above a case threshold; attaches the summary string to the raised error
"""
import numpy as np
import pandas as pd
import pytest

from pivot_dhis_tools.pridec.check_dhis_value import check_dhis_value, check_import_value


def make_df(values):
    return pd.DataFrame({"orgUnit": [f"ou{i}" for i in range(len(values))], "value": values})


# ---------------------------------------------------------------------------
# check_dhis_value
# ---------------------------------------------------------------------------
class TestCheckDhisValue:
    def test_valid_data_returns_summary(self):
        result = check_dhis_value(make_df([0, 3, 10]))
        assert result == "numNA: 0 | minimum value: 0 | maximum value: 10 | negative values: 0"

    def test_zero_is_allowed(self):
        assert "negative values: 0" in check_dhis_value(make_df([0, 0, 0]))

    def test_float_values(self):
        result = check_dhis_value(make_df([0.5, 2.25]))
        assert "minimum value: 0.5" in result
        assert "maximum value: 2.25" in result

    def test_na_raises(self):
        with pytest.raises(ValueError, match="Incorrectly formatted data"):
            check_dhis_value(make_df([1, np.nan, 3]))

    def test_none_raises(self):
        with pytest.raises(ValueError, match="Incorrectly formatted data"):
            check_dhis_value(make_df([1, None, 3]))

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="Incorrectly formatted data"):
            check_dhis_value(make_df([1, -1, 3]))

    def test_na_and_negative_raises(self):
        with pytest.raises(ValueError):
            check_dhis_value(make_df([np.nan, -2]))

    def test_missing_value_column_raises_keyerror(self):
        with pytest.raises(KeyError):
            check_dhis_value(pd.DataFrame({"orgUnit": ["a"], "count": [1]}))

    def test_empty_data_passes(self):
        # Current behaviour: empty input is not treated as an error here
        # (unlike check_import_value). min/max are NaN.
        result = check_dhis_value(make_df([]))
        assert result.startswith("numNA: 0 | minimum value: nan | maximum value: nan")


# ---------------------------------------------------------------------------
# check_import_value
# ---------------------------------------------------------------------------
class TestCheckImportValue:
    def test_valid_data_returns_summary(self):
        result = check_import_value(make_df([0, 5, 20]), max_threshold=100)
        assert result == (
            "numNA: 0 | minimum value: 0 | maximum value: 20 | "
            "negative values: 0 | number of values: 3"
        )

    def test_value_equal_to_threshold_passes(self):
        # threshold check is strictly greater-than
        result = check_import_value(make_df([1, 100]), max_threshold=100)
        assert "maximum value: 100" in result

    def test_value_above_threshold_raises(self):
        with pytest.raises(ValueError, match="2 orgUnits exceed case threshold of 100"):
            check_import_value(make_df([1, 101, 500]), max_threshold=100)

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="no values to import"):
            check_import_value(make_df([]), max_threshold=100)

    def test_na_raises(self):
        with pytest.raises(ValueError, match="1 missing \\(NA\\) values"):
            check_import_value(make_df([1, np.nan]), max_threshold=100)

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="2 negative values"):
            check_import_value(make_df([-1, -5, 3]), max_threshold=100)

    def test_multiple_problems_reported_together(self):
        with pytest.raises(ValueError) as exc:
            check_import_value(make_df([np.nan, -1, 200]), max_threshold=100)
        msg = str(exc.value)
        assert msg.startswith("Potential errors in data to be imported:")
        assert "1 missing (NA) values; 1 orgUnits exceed case threshold of 100; 1 negative values" in msg

    def test_error_carries_summary_attribute(self):
        with pytest.raises(ValueError) as exc:
            check_import_value(make_df([-1, 4]), max_threshold=100)
        assert exc.value.summary == (
            "numNA: 0 | minimum value: -1 | maximum value: 4 | "
            "negative values: 1 | number of values: 2"
        )
        # summary is also appended to the message
        assert str(exc.value).endswith(exc.value.summary)

    def test_number_of_values_counts_na(self):
        with pytest.raises(ValueError) as exc:
            check_import_value(make_df([1, np.nan, np.nan]), max_threshold=100)
        assert "number of values: 3" in exc.value.summary
        assert "numNA: 2" in exc.value.summary

    def test_missing_value_column_raises_keyerror(self):
        with pytest.raises(KeyError):
            check_import_value(pd.DataFrame({"orgUnit": ["a"]}), max_threshold=100)
