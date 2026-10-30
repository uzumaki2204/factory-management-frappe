"""A parameterized SELECT-only connection to the reporting source."""

from contextlib import contextmanager

from .model import ReportSourceError


class SqlServer:
    def __init__(self, config):
        if not isinstance(config, dict) or any(not config.get(key) for key in
                                               ("host", "database", "user", "password")):
            raise ReportSourceError("QCBROTHER_SQL_CONFIG_REQUIRED")
        self.config = config

    @contextmanager
    def connect(self):
        connection_string = self._connection_string()
        query_timeout = self._timeout("query_timeout", 60)
        try:
            import mssql_python

            connection = mssql_python.connect(connection_string, autocommit=True,
                                             timeout=self._timeout("connect_timeout", 10))
            connection.timeout = query_timeout
        except Exception:
            raise ReportSourceError("QCBROTHER_SQL_UNAVAILABLE") from None
        try:
            yield SqlReader(connection)
        finally:
            try:
                connection.close()
            except Exception:
                pass

    def _connection_string(self):
        config = self.config
        try:
            port = int(config.get("port", 1433))
            if not 1 <= port <= 65535:
                raise ValueError
        except (TypeError, ValueError):
            raise ReportSourceError("QCBROTHER_SQL_CONFIG_REQUIRED") from None
        values = {
            "SERVER": f"tcp:{config['host']},{port}", "DATABASE": config["database"],
            "UID": config["user"], "PWD": config["password"],
            "Encrypt": "yes", "TrustServerCertificate": "yes" if config.get("trust_server_certificate") else "no",
            "ApplicationIntent": "ReadOnly",
        }
        return ";".join(f"{key}={_quote(value)}" for key, value in values.items()) + ";"

    def _timeout(self, key, default):
        try:
            value = int(self.config.get(key, default))
            if 1 <= value <= 300:
                return value
        except (TypeError, ValueError):
            pass
        raise ReportSourceError("QCBROTHER_SQL_CONFIG_REQUIRED")


class SqlReader:
    def __init__(self, connection):
        self.connection = connection

    def rows(self, sql, parameters=()):
        if not sql.lstrip().upper().startswith("SELECT "):
            raise ReportSourceError("QCBROTHER_SQL_QUERY_INVALID")
        cursor = None
        try:
            cursor = self.connection.cursor()
            cursor.execute(sql, tuple(parameters))
            columns = [column[0] for column in cursor.description]
            while batch := cursor.fetchmany(1000):
                for row in batch:
                    yield dict(zip(columns, row))
        except Exception:
            raise ReportSourceError("QCBROTHER_SQL_UNAVAILABLE") from None
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:
                    pass


def _quote(value):
    return "{" + str(value).replace("}", "}}") + "}"
