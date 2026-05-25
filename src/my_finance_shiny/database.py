from ..my_finance_shared.database import connect_with_retry


def db_conn():
    return connect_with_retry(read_only=True)
