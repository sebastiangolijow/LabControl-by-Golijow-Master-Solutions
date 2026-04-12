"""
Real Firebird connector for LabWin database.

Uses firebirdsql (pure Python) to connect to the LabWin Firebird server.
Connection parameters come from Django settings (LABWIN_FDB_*).
"""

import logging

from django.conf import settings

from .base import LabWinConnector

logger = logging.getLogger(__name__)

# SQL for fetching validated DETERS rows incrementally
DETERS_QUERY = """
    SELECT NUMERO_FLD, ABREV_FLD, RESULT_FLD, RESULTREP_FLD,
           VALIDADO_FLD, FECHA_FLD, HORA_FLD, ORDEN_FLD, OPERADOR_FLD, SUCURSAL_FLD
    FROM DETERS
    WHERE VALIDADO_FLD = '1'
      AND CARGADO_FLD = '1'
      AND PRV_DELETEDRECORD_FLD = '0'
      AND (FECHA_FLD > ? OR (FECHA_FLD = ? AND NUMERO_FLD > ?))
    ORDER BY FECHA_FLD, NUMERO_FLD
"""

DETERS_QUERY_FULL = """
    SELECT NUMERO_FLD, ABREV_FLD, RESULT_FLD, RESULTREP_FLD,
           VALIDADO_FLD, FECHA_FLD, HORA_FLD, ORDEN_FLD, OPERADOR_FLD, SUCURSAL_FLD
    FROM DETERS
    WHERE VALIDADO_FLD = '1'
      AND CARGADO_FLD = '1'
      AND PRV_DELETEDRECORD_FLD = '0'
    ORDER BY FECHA_FLD, NUMERO_FLD
"""

PACIENTES_QUERY = """
    SELECT NUMERO_FLD, NOMBRE_FLD, HCLIN_FLD, SEXO_FLD, FNACIM_FLD,
           MUTUAL_FLD, MEDICO_FLD, NUMMEDICO_FLD, CARNET_FLD,
           TELEFONO_FLD, CELULAR_FLD, DIRECCION_FLD, LOCALIDAD_FLD, EMAIL_FLD
    FROM PACIENTES
    WHERE NUMERO_FLD IN ({placeholders})
      AND PRV_DELETEDRECORD_FLD = '0'
"""

MEDICOS_QUERY = """
    SELECT NUMERO_FLD, NOMBRE_FLD, MATNAC_FLD, MATPROV_FLD, ESPECIALIDAD_FLD,
           TELEFONO_FLD, EMAIL_FLD
    FROM MEDICOS
    WHERE NUMERO_FLD IN ({placeholders})
      AND PRV_DELETEDRECORD_FLD = '0'
"""

NOMEN_QUERY = """
    SELECT ABREV_FLD, NOMBRE_FLD, SECCION_FLD, DIASTARDA_FLD, MATERIAL_FLD
    FROM NOMEN
    WHERE ABREV_FLD IN ({placeholders})
      AND PRV_DELETEDRECORD_FLD = '0'
"""

DETERS_COLUMNS = [
    "NUMERO_FLD", "ABREV_FLD", "RESULT_FLD", "RESULTREP_FLD",
    "VALIDADO_FLD", "FECHA_FLD", "HORA_FLD", "ORDEN_FLD", "OPERADOR_FLD", "SUCURSAL_FLD",
]

PACIENTES_COLUMNS = [
    "NUMERO_FLD", "NOMBRE_FLD", "HCLIN_FLD", "SEXO_FLD", "FNACIM_FLD",
    "MUTUAL_FLD", "MEDICO_FLD", "NUMMEDICO_FLD", "CARNET_FLD",
    "TELEFONO_FLD", "CELULAR_FLD", "DIRECCION_FLD", "LOCALIDAD_FLD", "EMAIL_FLD",
]

MEDICOS_COLUMNS = [
    "NUMERO_FLD", "NOMBRE_FLD", "MATNAC_FLD", "MATPROV_FLD", "ESPECIALIDAD_FLD",
    "TELEFONO_FLD", "EMAIL_FLD",
]

NOMEN_COLUMNS = [
    "ABREV_FLD", "NOMBRE_FLD", "SECCION_FLD", "DIASTARDA_FLD", "MATERIAL_FLD",
]


def _rows_to_dicts(rows, columns):
    """Convert list of tuples to list of dicts using column names."""
    return [
        {col: (val.strip() if isinstance(val, str) else val) for col, val in zip(columns, row)}
        for row in rows
    ]


class FirebirdLabWinConnector(LabWinConnector):
    """Connects to the real LabWin Firebird database server."""

    def __init__(self):
        self.connection = None

    def connect(self):
        import firebirdsql

        self.connection = firebirdsql.connect(
            host=settings.LABWIN_FDB_HOST,
            port=settings.LABWIN_FDB_PORT,
            database=settings.LABWIN_FDB_DATABASE,
            user=settings.LABWIN_FDB_USER,
            password=settings.LABWIN_FDB_PASSWORD,
            charset=settings.LABWIN_FDB_CHARSET,
        )
        logger.info("Connected to LabWin Firebird database at %s", settings.LABWIN_FDB_HOST)

    def disconnect(self):
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.info("Disconnected from LabWin Firebird database")

    def fetch_validated_deters(self, since_fecha=None, since_numero=None, batch_size=500):
        cursor = self.connection.cursor()
        try:
            if since_fecha and since_numero is not None:
                cursor.execute(DETERS_QUERY, (since_fecha, since_fecha, since_numero))
            else:
                cursor.execute(DETERS_QUERY_FULL)

            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                yield _rows_to_dicts(rows, DETERS_COLUMNS)
        finally:
            cursor.close()

    def fetch_pacientes(self, numero_fld_list):
        if not numero_fld_list:
            return {}
        cursor = self.connection.cursor()
        try:
            placeholders = ",".join("?" * len(numero_fld_list))
            query = PACIENTES_QUERY.format(placeholders=placeholders)
            cursor.execute(query, numero_fld_list)
            rows = cursor.fetchall()
            dicts = _rows_to_dicts(rows, PACIENTES_COLUMNS)
            return {d["NUMERO_FLD"]: d for d in dicts}
        finally:
            cursor.close()

    def fetch_medicos(self, numero_fld_list):
        if not numero_fld_list:
            return {}
        cursor = self.connection.cursor()
        try:
            placeholders = ",".join("?" * len(numero_fld_list))
            query = MEDICOS_QUERY.format(placeholders=placeholders)
            cursor.execute(query, numero_fld_list)
            rows = cursor.fetchall()
            dicts = _rows_to_dicts(rows, MEDICOS_COLUMNS)
            return {d["NUMERO_FLD"]: d for d in dicts}
        finally:
            cursor.close()

    def fetch_nomen(self, abrev_fld_list):
        if not abrev_fld_list:
            return {}
        cursor = self.connection.cursor()
        try:
            placeholders = ",".join("?" * len(abrev_fld_list))
            query = NOMEN_QUERY.format(placeholders=placeholders)
            cursor.execute(query, abrev_fld_list)
            rows = cursor.fetchall()
            dicts = _rows_to_dicts(rows, NOMEN_COLUMNS)
            return {d["ABREV_FLD"]: d for d in dicts}
        finally:
            cursor.close()
