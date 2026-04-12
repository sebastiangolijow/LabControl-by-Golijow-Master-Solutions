"""
Mock connector for development and testing.

Provides hardcoded sample data that matches the LabWin database schema.
No external dependencies required for unit tests.
"""

import logging

from .base import LabWinConnector

logger = logging.getLogger(__name__)


# Sample data matching real LabWin schema
SAMPLE_PACIENTES = {
    100001: {
        "NUMERO_FLD": 100001,
        "NOMBRE_FLD": "Garcia, Maria",
        "HCLIN_FLD": "30123456",
        "SEXO_FLD": 2,
        "FNACIM_FLD": "19850315",
        "MUTUAL_FLD": 1,
        "MEDICO_FLD": "Lopez, Juan",
        "NUMMEDICO_FLD": 501,
        "CARNET_FLD": "ABC123",
        "TELEFONO_FLD": "011-4555-1234",
        "CELULAR_FLD": "11-2345-6789",
        "DIRECCION_FLD": "Av. Corrientes 1234",
        "LOCALIDAD_FLD": "CABA",
        "EMAIL_FLD": "maria.garcia@test.com",
    },
    100002: {
        "NUMERO_FLD": 100002,
        "NOMBRE_FLD": "Rodriguez Pedro",
        "HCLIN_FLD": "28987654",
        "SEXO_FLD": 1,
        "FNACIM_FLD": "19780620",
        "MUTUAL_FLD": 2,
        "MEDICO_FLD": "Lopez, Juan",
        "NUMMEDICO_FLD": 501,
        "CARNET_FLD": "DEF456",
        "TELEFONO_FLD": "",
        "CELULAR_FLD": "11-9876-5432",
        "DIRECCION_FLD": "San Martin 567",
        "LOCALIDAD_FLD": "La Plata",
        "EMAIL_FLD": "",
    },
    100003: {
        "NUMERO_FLD": 100003,
        "NOMBRE_FLD": "Fernandez Ana",
        "HCLIN_FLD": "35456789",
        "SEXO_FLD": 2,
        "FNACIM_FLD": "19920101",
        "MUTUAL_FLD": 1,
        "MEDICO_FLD": "Martinez, Carlos",
        "NUMMEDICO_FLD": 502,
        "CARNET_FLD": "GHI789",
        "TELEFONO_FLD": "",
        "CELULAR_FLD": "",
        "DIRECCION_FLD": "",
        "LOCALIDAD_FLD": "Rosario",
        "EMAIL_FLD": "ana.fernandez@test.com",
    },
}

SAMPLE_MEDICOS = {
    501: {
        "NUMERO_FLD": 501,
        "NOMBRE_FLD": "Lopez, Juan",
        "MATNAC_FLD": "MN12345",
        "MATPROV_FLD": "MP67890",
        "ESPECIALIDAD_FLD": "Clinica Medica",
        "TELEFONO_FLD": "011-4555-9999",
        "EMAIL_FLD": "dr.lopez@test.com",
    },
    502: {
        "NUMERO_FLD": 502,
        "NOMBRE_FLD": "Martinez, Carlos",
        "MATNAC_FLD": "MN54321",
        "MATPROV_FLD": "",
        "ESPECIALIDAD_FLD": "Endocrinologia",
        "TELEFONO_FLD": "",
        "EMAIL_FLD": "",
    },
}

SAMPLE_NOMEN = {
    "GLU-Bi": {
        "ABREV_FLD": "GLU-Bi",
        "NOMBRE_FLD": "Glucemia Basal",
        "SECCION_FLD": 1,
        "DIASTARDA_FLD": 1,
        "MATERIAL_FLD": 1,
    },
    "HEMC": {
        "ABREV_FLD": "HEMC",
        "NOMBRE_FLD": "Hemograma Completo",
        "SECCION_FLD": 2,
        "DIASTARDA_FLD": 1,
        "MATERIAL_FLD": 1,
    },
    "TSH": {
        "ABREV_FLD": "TSH",
        "NOMBRE_FLD": "Tirotrofina",
        "SECCION_FLD": 3,
        "DIASTARDA_FLD": 2,
        "MATERIAL_FLD": 1,
    },
    "URE": {
        "ABREV_FLD": "URE",
        "NOMBRE_FLD": "Uremia",
        "SECCION_FLD": 1,
        "DIASTARDA_FLD": 1,
        "MATERIAL_FLD": 1,
    },
    "CRE-Bi": {
        "ABREV_FLD": "CRE-Bi",
        "NOMBRE_FLD": "Creatinina",
        "SECCION_FLD": 1,
        "DIASTARDA_FLD": 1,
        "MATERIAL_FLD": 1,
    },
}

SAMPLE_DETERS = [
    # Order 100001 - patient Garcia, Maria
    {
        "NUMERO_FLD": 100001,
        "ABREV_FLD": "GLU-Bi",
        "RESULT_FLD": "92",
        "RESULTREP_FLD": "",
        "VALIDADO_FLD": "1",
        "FECHA_FLD": "20251028",
        "HORA_FLD": "08:30",
        "ORDEN_FLD": 1,
        "OPERADOR_FLD": 174,
        "SUCURSAL_FLD": 0,
    },
    {
        "NUMERO_FLD": 100001,
        "ABREV_FLD": "HEMC",
        "RESULT_FLD": "79|4790|137|39|242000|81|29|35|61|2|1|31|5|02",
        "RESULTREP_FLD": "",
        "VALIDADO_FLD": "1",
        "FECHA_FLD": "20251028",
        "HORA_FLD": "08:30",
        "ORDEN_FLD": 2,
        "OPERADOR_FLD": 174,
        "SUCURSAL_FLD": 0,
    },
    {
        "NUMERO_FLD": 100001,
        "ABREV_FLD": "TSH",
        "RESULT_FLD": "364|-11",
        "RESULTREP_FLD": "",
        "VALIDADO_FLD": "1",
        "FECHA_FLD": "20251028",
        "HORA_FLD": "08:30",
        "ORDEN_FLD": 3,
        "OPERADOR_FLD": 174,
        "SUCURSAL_FLD": 0,
    },
    # Order 100002 - patient Rodriguez Pedro
    {
        "NUMERO_FLD": 100002,
        "ABREV_FLD": "GLU-Bi",
        "RESULT_FLD": "105",
        "RESULTREP_FLD": "",
        "VALIDADO_FLD": "1",
        "FECHA_FLD": "20251029",
        "HORA_FLD": "09:15",
        "ORDEN_FLD": 1,
        "OPERADOR_FLD": 61,
        "SUCURSAL_FLD": 0,
    },
    {
        "NUMERO_FLD": 100002,
        "ABREV_FLD": "URE",
        "RESULT_FLD": "35",
        "RESULTREP_FLD": "",
        "VALIDADO_FLD": "1",
        "FECHA_FLD": "20251029",
        "HORA_FLD": "09:15",
        "ORDEN_FLD": 2,
        "OPERADOR_FLD": 61,
        "SUCURSAL_FLD": 0,
    },
    {
        "NUMERO_FLD": 100002,
        "ABREV_FLD": "CRE-Bi",
        "RESULT_FLD": "0.9",
        "RESULTREP_FLD": "",
        "VALIDADO_FLD": "1",
        "FECHA_FLD": "20251029",
        "HORA_FLD": "09:15",
        "ORDEN_FLD": 3,
        "OPERADOR_FLD": 61,
        "SUCURSAL_FLD": 0,
    },
    # Order 100003 - patient Fernandez Ana
    {
        "NUMERO_FLD": 100003,
        "ABREV_FLD": "TSH",
        "RESULT_FLD": "250|-11",
        "RESULTREP_FLD": "",
        "VALIDADO_FLD": "1",
        "FECHA_FLD": "20251030",
        "HORA_FLD": "10:00",
        "ORDEN_FLD": 1,
        "OPERADOR_FLD": 180,
        "SUCURSAL_FLD": 0,
    },
    # Not yet validated - should be excluded from sync
    {
        "NUMERO_FLD": 100003,
        "ABREV_FLD": "GLU-Bi",
        "RESULT_FLD": "88",
        "RESULTREP_FLD": "",
        "VALIDADO_FLD": "0",
        "FECHA_FLD": "20251030",
        "HORA_FLD": "10:00",
        "ORDEN_FLD": 2,
        "OPERADOR_FLD": 180,
        "SUCURSAL_FLD": 0,
    },
]


class MockLabWinConnector(LabWinConnector):
    """Mock connector returning hardcoded sample data for dev/testing."""

    def __init__(self):
        self._connected = False

    def connect(self):
        self._connected = True
        logger.info("MockLabWinConnector connected (using in-memory sample data)")

    def disconnect(self):
        self._connected = False
        logger.info("MockLabWinConnector disconnected")

    def fetch_validated_deters(
        self, since_fecha=None, since_numero=None, batch_size=500
    ):
        # Only return validated rows, matching real Firebird connector behavior
        data = [row for row in SAMPLE_DETERS if row.get("VALIDADO_FLD") == "1"]

        if since_fecha and since_numero is not None:
            data = [
                row
                for row in data
                if (row["FECHA_FLD"] > since_fecha)
                or (
                    row["FECHA_FLD"] == since_fecha and row["NUMERO_FLD"] > since_numero
                )
            ]

        # Yield in batches
        for i in range(0, len(data), batch_size):
            yield data[i : i + batch_size]

    def fetch_pacientes(self, numero_fld_list):
        return {
            num: SAMPLE_PACIENTES[num]
            for num in numero_fld_list
            if num in SAMPLE_PACIENTES
        }

    def fetch_medicos(self, numero_fld_list):
        return {
            num: SAMPLE_MEDICOS[num] for num in numero_fld_list if num in SAMPLE_MEDICOS
        }

    def fetch_nomen(self, abrev_fld_list):
        return {
            abrev: SAMPLE_NOMEN[abrev]
            for abrev in abrev_fld_list
            if abrev in SAMPLE_NOMEN
        }
