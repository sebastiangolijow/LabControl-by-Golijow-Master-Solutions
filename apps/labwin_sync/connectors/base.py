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
        """Fetch DETERS rows since the given cursor.

        Note: despite the historical name "fetch_validated_deters", this
        method now returns ALL DETERS rows in the date window — both
        validated and not. The sync layer decides whether each protocol
        (NUMERO_FLD) is fully validated based on the union of its rows.
        See is_protocol_fully_validated() in mappers.py.

        Args:
            since_fecha: YYYYMMDD string, fetch records with FECHA_FLD >= this.
            since_numero: NUMERO_FLD integer, for records on since_fecha, fetch only > this.
            batch_size: Number of rows per batch.

        Yields:
            Lists of dicts, each dict representing a DETERS row with keys:
            NUMERO_FLD, ABREV_FLD, RESULT_FLD, RESULTREP_FLD,
            VALIDADO_FLD, CARGADO_FLD,
            FECHA_FLD, HORA_FLD, ORDEN_FLD, OPERADOR_FLD, SUCURSAL_FLD
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

    @abstractmethod
    def fetch_one_protocol(self, numero):
        """Fetch a single protocol's full row set, identified by NUMERO_FLD.

        Used by the on-demand import flow (admin types a NUMERO into the
        UI, we look it up in Firebird and run it through the sync
        helpers). Distinct from fetch_validated_deters in two ways:

          1. No date-window filter — old protocols (<90 days ago) are
             reachable. The local Firebird container holds the full lab
             DB since 2011.
          2. No partial-validation NOT IN guard — the task layer needs
             to *see* a partial protocol to report it back to the admin
             ("the lab still has GLU-Bi pending"), not silently get
             zero rows.

        Args:
            numero: NUMERO_FLD integer (the LabWin protocol number).

        Returns:
            None if no DETERS rows exist for this NUMERO (typo / never
            existed). Otherwise a dict:

                {
                    "deters":   [<DETERS row dicts>],         # 1+ rows
                    "paciente": <PACIENTES row dict | None>,
                    "medico":   <MEDICOS row dict | None>,
                    "nomens":   {ABREV_FLD: <NOMEN row dict>},
                }
        """

    # The following two methods are not @abstractmethod because they are only
    # used by the standalone `sync_practice_layouts` management command, not
    # by the regular nightly sync. The mock connector raises NotImplementedError.

    def fetch_results_metadata(self, abrev_fld_list=None):
        """Fetch RESULTS rows (per-position practice metadata).

        Args:
            abrev_fld_list: Optional list of ABREV_FLD to filter. None = all.

        Returns:
            Dict mapping ABREV_FLD -> list of row dicts. See
            apps/labwin_sync/services/practice_layout.build_layout for schema.
        """
        raise NotImplementedError

    def fetch_valnor(self, abrev_fld_list=None):
        """Fetch VALNOR rows (reference ranges, sex/age stratified).

        Args:
            abrev_fld_list: Optional list of ABREV_FLD to filter. None = all.

        Returns:
            Dict mapping ABREV_FLD -> list of row dicts.
        """
        raise NotImplementedError

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False
