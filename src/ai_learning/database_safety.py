import psycopg
from psycopg.conninfo import conninfo_to_dict

LOCAL_DATABASE_HOSTS = {"127.0.0.1", "localhost", "::1"}


def is_local_database(database_url: str) -> bool:
    try:
        host = conninfo_to_dict(database_url).get("host")
    except psycopg.ProgrammingError:
        return False
    return host in LOCAL_DATABASE_HOSTS
