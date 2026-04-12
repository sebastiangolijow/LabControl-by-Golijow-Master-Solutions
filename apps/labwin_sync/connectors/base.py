"""
Abstract base class defining the LabWin connector interface.

All connectors (Firebird, mock) must implement this interface.
"""

from abc import ABC, abstractmethod


class LabWinConnector(ABC):
    """Interface for connecting to a LabWin database and fetching data."""

    @abstractmethod
    def connect(self):
        """Establish connection to the LabWin database."""

    @abstractmethod
    def disconnect(self):
        """Close the connection to the LabWin database."""

    @abstractmethod
    def fetch_validated_deters(
        self, since_fecha=None, since_numero=None, batch_size=500
    ):
        """Fetch validated DETERS rows since the given cursor.

        Args:
            since_fecha: YYYYMMDD string, fetch records with FECHA_FLD >= this.
            since_numero: NUMERO_FLD integer, for records on since_fecha, fetch only > this.
            batch_size: Number of rows per batch.

        Yields:
            Lists of dicts, each dict representing a DETERS row with keys:
            NUMERO_FLD, ABREV_FLD, RESULT_FLD, RESULTREP_FLD,
            VALIDADO_FLD, FECHA_FLD, HORA_FLD, ORDEN_FLD, OPERADOR_FLD, SUCURSAL_FLD
        """

    @abstractmethod
    def fetch_pacientes(self, numero_fld_list):
        """Fetch PACIENTES rows for the given order numbers.

        Args:
            numero_fld_list: List of NUMERO_FLD integers.

        Returns:
            Dict mapping NUMERO_FLD -> row dict with keys:
            NUMERO_FLD, NOMBRE_FLD, HCLIN_FLD, SEXO_FLD, FNACIM_FLD,
            MUTUAL_FLD, MEDICO_FLD, NUMMEDICO_FLD, CARNET_FLD,
            TELEFONO_FLD, CELULAR_FLD, DIRECCION_FLD, LOCALIDAD_FLD, EMAIL_FLD
        """

    @abstractmethod
    def fetch_medicos(self, numero_fld_list):
        """Fetch MEDICOS rows for the given doctor numbers.

        Args:
            numero_fld_list: List of NUMERO_FLD integers.

        Returns:
            Dict mapping NUMERO_FLD -> row dict with keys:
            NUMERO_FLD, NOMBRE_FLD, MATNAC_FLD, MATPROV_FLD, ESPECIALIDAD_FLD,
            TELEFONO_FLD, EMAIL_FLD
        """

    @abstractmethod
    def fetch_nomen(self, abrev_fld_list):
        """Fetch NOMEN rows for the given practice abbreviations.

        Args:
            abrev_fld_list: List of ABREV_FLD strings.

        Returns:
            Dict mapping ABREV_FLD -> row dict with keys:
            ABREV_FLD, NOMBRE_FLD, SECCION_FLD, DIASTARDA_FLD, MATERIAL_FLD
        """

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False
