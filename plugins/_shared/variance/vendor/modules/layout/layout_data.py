from modules.layout.memoization import session_memoize_check_params


def collect_lazyframe(df):
    """Collect a Polars ``LazyFrame`` and return a ``DataFrame``."""
    return df.collect()


def collect_and_store_in_session_state(df):
    """Collect a Polars LazyFrame without returning Pandas."""
    return df.collect()


@session_memoize_check_params(check_diff=True)
def collect_base(df, indexCols, paramDict):
    """Collect a Polars ``LazyFrame`` for base data."""
    return collect_lazyframe(df)


@session_memoize_check_params(check_diff=True)
def collect_periods(df, indexColsCopy, nodeDictCopy, valueColsCopy, paramDictCopy):
    """Collect a ``LazyFrame`` for period data."""
    return collect_lazyframe(df)


@session_memoize_check_params(check_diff=True)
def collect_dates(df, indexColsCopy, nodeDictCopy, valueColsCopy, paramDictCopy):
    """Collect a ``LazyFrame`` for date data."""
    return collect_lazyframe(df)


@session_memoize_check_params(check_diff=True)
def collect_all_periods(df, indexCols, valueCols, paramDict):
    """Collect a ``LazyFrame`` containing all periods."""
    return collect_lazyframe(df)


@session_memoize_check_params(check_diff=True)
def collect_session_base(df, indexCols, valueCols, paramDict, chartDict):
    """Collect and store base data in UI session state."""
    return collect_and_store_in_session_state(df)


@session_memoize_check_params(check_diff=True)
def collect_session_periods(df, indexCols, valueCols, paramDict, chartDict):
    """Collect period data and store in session state."""
    return collect_and_store_in_session_state(df)


@session_memoize_check_params(check_diff=True)
def collect_session_dates(df, indexCols, valueCols, paramDict, chartDict):
    """Collect date data and store in session state."""
    return collect_and_store_in_session_state(df)


@session_memoize_check_params(check_diff=True)
def collect_session_all_periods(df, indexCols, valueCols, paramDict):
    """Collect all period data and store in session state."""
    return collect_and_store_in_session_state(df)
