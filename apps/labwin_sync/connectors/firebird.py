"""
Real Firebird connector for LabWin database.

Uses firebirdsql (pure Python) to connect to the LabWin Firebird server.
Connection parameters come from Django settings (LABWIN_FDB_*).
"""

import logging

from django.conf import settings

from .base import LabWinConnector

logger = logging.getLogger(__name__)

# NOTE on PRV_DELETEDRECORD_FLD: this column is present on DETERS / MEDICOS /
# NOMEN / PACIENTES, but in the live LabWin DB ~80–93% of rows have it NULL
# and the rest are '0' — no row is ever marked deleted (column was designed
# but never used). The connector previously filtered `WHERE PRV_DELETEDRECORD_FLD = '0'`,
# which silently dropped every NULL row — i.e. ~87% of MEDICOS, ~93% of NOMEN,
# ~86% of PACIENTES, ~81% of DETERS. That's why most synced studies ended up
# with `ordered_by=NULL` (the referring doctor's MEDICOS row was filtered out).
# Filter dropped 2026-05-07. If the lab ever starts using this column, switch
# to `(PRV_DELETEDRECORD_FLD IS NULL OR PRV_DELETEDRECORD_FLD <> '1')` and
# verify which value(s) actually denote deletion.

# SQL for fetching DETERS rows. We exclude any NUMERO that has at least one
# practice not fully validated+loaded (VALIDADO_FLD='1' AND CARGADO_FLD='1').
# Done at the SQL level — not in Python — because rows for a single NUMERO
# can split across fetchmany() boundaries, and the per-batch grouping in
# tasks.py would then evaluate the partial-validation gate on a partial
# slice of the protocol. Real failure: LW-257008 had 15 DETERS rows on
# 2026-05-05 (12 validated, 3 not). The 500-row batch boundary fell inside
# the protocol, so 3 of the validated rows were grouped alone, the
# is_protocol_fully_validated() gate saw only validated rows, and the
# protocol was imported with 3 StudyPractices despite the lab not having
# finished it (and not exporting a PDF for it). The NOT IN guard below
# ensures the connector never yields any row of a partial NUMERO, no
# matter where fetchmany() splits.
_PARTIAL_NUMERO_FILTER = (
    "NUMERO_FLD NOT IN ("
    "SELECT DISTINCT NUMERO_FLD FROM DETERS "
    "WHERE VALIDADO_FLD IS NULL OR VALIDADO_FLD <> '1' "
    "OR CARGADO_FLD IS NULL OR CARGADO_FLD <> '1'"
    ")"
)

DETERS_QUERY = f"""
    SELECT NUMERO_FLD, ABREV_FLD, RESULT_FLD, RESULTREP_FLD,
           VALIDADO_FLD, CARGADO_FLD,
           FECHA_FLD, HORA_FLD, ORDEN_FLD, OPERADOR_FLD, SUCURSAL_FLD
    FROM DETERS
    WHERE (FECHA_FLD > ? OR (FECHA_FLD = ? AND NUMERO_FLD > ?))
      AND {_PARTIAL_NUMERO_FILTER}
    ORDER BY FECHA_FLD, NUMERO_FLD
"""

DETERS_QUERY_FULL = f"""
    SELECT NUMERO_FLD, ABREV_FLD, RESULT_FLD, RESULTREP_FLD,
           VALIDADO_FLD, CARGADO_FLD,
           FECHA_FLD, HORA_FLD, ORDEN_FLD, OPERADOR_FLD, SUCURSAL_FLD
    FROM DETERS
    WHERE {_PARTIAL_NUMERO_FILTER}
    ORDER BY FECHA_FLD, NUMERO_FLD
"""

PACIENTES_QUERY = """
    SELECT NUMERO_FLD, NOMBRE_FLD, HCLIN_FLD, SEXO_FLD, FNACIM_FLD,
           MUTUAL_FLD, MEDICO_FLD, NUMMEDICO_FLD, CARNET_FLD,
           TELEFONO_FLD, CELULAR_FLD, DIRECCION_FLD, LOCALIDAD_FLD, EMAIL_FLD,
           DEBEBONO_FLD
    FROM PACIENTES
    WHERE NUMERO_FLD IN ({placeholders})
"""

MEDICOS_QUERY = """
    SELECT NUMERO_FLD, NOMBRE_FLD, MATNAC_FLD, MATPROV_FLD, ESPECIALIDAD_FLD,
           TELEFONO_FLD, EMAIL_FLD
    FROM MEDICOS
    WHERE NUMERO_FLD IN ({placeholders})
"""

NOMEN_QUERY = """
    SELECT ABREV_FLD, NOMBRE_FLD, SECCION_FLD, DIASTARDA_FLD, MATERIAL_FLD
    FROM NOMEN
    WHERE ABREV_FLD IN ({placeholders})
"""

DETERS_COLUMNS = [
    "NUMERO_FLD",
    "ABREV_FLD",
    "RESULT_FLD",
    "RESULTREP_FLD",
    "VALIDADO_FLD",
    "CARGADO_FLD",
    "FECHA_FLD",
    "HORA_FLD",
    "ORDEN_FLD",
    "OPERADOR_FLD",
    "SUCURSAL_FLD",
]

PACIENTES_COLUMNS = [
    "NUMERO_FLD",
    "NOMBRE_FLD",
    "HCLIN_FLD",
    "SEXO_FLD",
    "FNACIM_FLD",
    "MUTUAL_FLD",
    "MEDICO_FLD",
    "NUMMEDICO_FLD",
    "CARNET_FLD",
    "TELEFONO_FLD",
    "CELULAR_FLD",
    "DIRECCION_FLD",
    "LOCALIDAD_FLD",
    "EMAIL_FLD",
    "DEBEBONO_FLD",  # paid/owes-bono flag → maps to Study.is_paid
]

MEDICOS_COLUMNS = [
    "NUMERO_FLD",
    "NOMBRE_FLD",
    "MATNAC_FLD",
    "MATPROV_FLD",
    "ESPECIALIDAD_FLD",
    "TELEFONO_FLD",
    "EMAIL_FLD",
]

NOMEN_COLUMNS = [
    "ABREV_FLD",
    "NOMBRE_FLD",
    "SECCION_FLD",
    "DIASTARDA_FLD",
    "MATERIAL_FLD",
]


# RESULTS — per-position practice metadata. See
# apps/labwin_sync/services/practice_layout.py for how this is consumed.
RESULTS_QUERY_ALL = """
    SELECT ABREV_FLD, POSICION_FLD, INRESUL_FLD, UNIDADES_FLD, FORMATO_FLD,
           DECIMALES_FLD, FACTOR_FLD,
           LIMINFIM_FLD, LIMINFMB_FLD, LIMINFBA_FLD,
           LIMSUPAL_FLD, LIMSUPMA_FLD, LIMSUPIM_FLD,
           PRV_TIMESTAMP_FLD
    FROM RESULTS
"""

RESULTS_QUERY_FILTERED = RESULTS_QUERY_ALL + " WHERE ABREV_FLD IN ({placeholders})"

RESULTS_COLUMNS = [
    "ABREV_FLD",
    "POSICION_FLD",
    "INRESUL_FLD",
    "UNIDADES_FLD",
    "FORMATO_FLD",
    "DECIMALES_FLD",
    "FACTOR_FLD",
    "LIMINFIM_FLD",
    "LIMINFMB_FLD",
    "LIMINFBA_FLD",
    "LIMSUPAL_FLD",
    "LIMSUPMA_FLD",
    "LIMSUPIM_FLD",
    "PRV_TIMESTAMP_FLD",
]


# VALNOR — reference ranges, sex/age stratified.
VALNOR_QUERY_ALL = """
    SELECT ABREV_FLD, POSICION_FLD, SEXO_FLD,
           EDADINFV_FLD, EDADINFL_FLD, EDADSUPV_FLD, EDADSUPL_FLD,
           TEXTO_FLD
    FROM VALNOR
"""

VALNOR_QUERY_FILTERED = VALNOR_QUERY_ALL + " WHERE ABREV_FLD IN ({placeholders})"

VALNOR_COLUMNS = [
    "ABREV_FLD",
    "POSICION_FLD",
    "SEXO_FLD",
    "EDADINFV_FLD",
    "EDADINFL_FLD",
    "EDADSUPV_FLD",
    "EDADSUPL_FLD",
    "TEXTO_FLD",
]


def _rows_to_dicts(rows, columns):
    """Convert list of tuples to list of dicts using column names."""
    return [
        {
            col: (val.strip() if isinstance(val, str) else val)
            for col, val in zip(columns, row)
        }
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
        logger.info(
            "Connected to LabWin Firebird database at %s", settings.LABWIN_FDB_HOST
        )

    def disconnect(self):
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.info("Disconnected from LabWin Firebird database")

    def fetch_validated_deters(
        self, since_fecha=None, since_numero=None, batch_size=500
    ):
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

    def fetch_results_metadata(self, abrev_fld_list=None):
        return self._fetch_grouped_chunked(
            abrev_fld_list,
            query_all=RESULTS_QUERY_ALL,
            query_filtered=RESULTS_QUERY_FILTERED,
            columns=RESULTS_COLUMNS,
        )

    def fetch_valnor(self, abrev_fld_list=None):
        return self._fetch_grouped_chunked(
            abrev_fld_list,
            query_all=VALNOR_QUERY_ALL,
            query_filtered=VALNOR_QUERY_FILTERED,
            columns=VALNOR_COLUMNS,
        )

    # Firebird's IN-list limit is 1500 — exceeded easily by our 2174 practices.
    # We have two limitations:
    #   1. IN-list of 1500 elements max
    #   2. ISO8859_1 charset can't encode unicode replacement characters
    #      (�) sometimes present in practice codes
    # When the filter list is large (more practical to fetch all + filter
    # client-side) OR contains non-latin1 chars, we just pull everything and
    # filter in Python. RESULTS is 5,345 rows total and VALNOR is 1,913 rows,
    # so the over-fetch is cheap.
    _FB_IN_LIST_LIMIT = 500  # conservative below the 1500 hard limit
    _FETCH_ALL_THRESHOLD = 500  # filter list size at which we fetch all

    def _fetch_grouped_chunked(
        self, abrev_fld_list, *, query_all, query_filtered, columns
    ):
        cursor = self.connection.cursor()
        try:
            grouped: dict[str, list[dict]] = {}

            # Fetch all when no filter, when the filter is too big, OR when
            # any code has chars that can't be encoded in latin-1.
            fetch_all = (
                not abrev_fld_list or len(abrev_fld_list) > self._FETCH_ALL_THRESHOLD
            )
            if not fetch_all:
                try:
                    "".join(abrev_fld_list).encode("latin-1")
                except UnicodeEncodeError:
                    fetch_all = True

            if fetch_all:
                cursor.execute(query_all)
                rows = _rows_to_dicts(cursor.fetchall(), columns)
                if abrev_fld_list:
                    wanted = set(abrev_fld_list)
                    rows = [d for d in rows if d["ABREV_FLD"] in wanted]
                for d in rows:
                    grouped.setdefault(d["ABREV_FLD"], []).append(d)
                return grouped

            # Small filter list, all latin-1 safe — chunk through IN-list
            for i in range(0, len(abrev_fld_list), self._FB_IN_LIST_LIMIT):
                chunk = abrev_fld_list[i : i + self._FB_IN_LIST_LIMIT]
                placeholders = ",".join("?" * len(chunk))
                cursor.execute(query_filtered.format(placeholders=placeholders), chunk)
                for d in _rows_to_dicts(cursor.fetchall(), columns):
                    grouped.setdefault(d["ABREV_FLD"], []).append(d)
            return grouped
        finally:
            cursor.close()
